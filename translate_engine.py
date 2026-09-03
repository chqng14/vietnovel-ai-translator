"""
translate_engine.py — Động cơ Dịch thuật
Quản lý model AI hoặc dịch vụ Google qua deep-translator, dịch theo batch,
hỗ trợ Pause/Resume/Cancel, cache, và stream tiến độ.

Tối ưu hiệu năng chính:
  1. Bật KV cache (config gốc của LMT-60 để use_cache=false → sinh token O(n²)).
  2. Tắt thinking mode của Qwen3 (mỗi đoạn sinh cả khối <think> dài vô ích).
  3. Greedy decoding + max_new_tokens động thay vì sampling + 1024 token cố định.
  4. Dịch theo batch thay vì từng đoạn một.
  5. Bỏ qua đoạn phân cách, cache đoạn trùng lặp.
  6. Tự lùi batch size khi hết VRAM thay vì crash.
"""

import asyncio
import importlib.util
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Optional

try:
    import torch
    from transformers import (
        AutoConfig,
        AutoTokenizer,
        AutoModelForCausalLM,
        AutoModelForSeq2SeqLM,
    )
except ImportError:
    # Chế độ deep-translator không cần PyTorch/Transformers.
    torch = None
    AutoConfig = AutoTokenizer = None
    AutoModelForCausalLM = AutoModelForSeq2SeqLM = None

AI_RUNTIME_AVAILABLE = torch is not None and AutoConfig is not None
DEEP_TRANSLATOR_AVAILABLE = importlib.util.find_spec("deep_translator") is not None

from glossary_manager import GlossaryManager


# ──────────────────────────────────────────────
#  Cấu hình
# ──────────────────────────────────────────────
DEFAULT_MODEL = "NiuTrans/LMT-60-1.7B"
DEEP_TRANSLATOR_GOOGLE = "deep-translator/google"

DEEP_TRANSLATOR_SOURCE_LANGS = {
    "en": "en",
    "ja": "ja",
    "zh": "zh-CN",
    "ko": "ko",
}

# Số token tối đa cho phần input của một đoạn
MAX_INPUT_TOKENS = 768
# Trần cứng cho số token sinh ra mỗi đoạn (chống sinh lan man vô hạn)
MAX_NEW_TOKENS_CAP = 512
# Hệ số ước lượng: bản dịch tiếng Việt dài hơn bản gốc bao nhiêu lần
OUTPUT_LENGTH_RATIO = 2.0

# Tên ngôn ngữ tiếng Anh — dùng cho prompt phẳng của model Seq2Seq
LANGUAGE_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
}

# Tên ngôn ngữ tiếng Việt — dùng cho prompt hội thoại của model CausalLM.
# Đo trên 5 câu tiếng Nhật: prompt tiếng Anh chỉ đạt 1/5 (model diễn giải lại
# sang tiếng Nhật thay vì dịch), prompt tiếng Việt + mồi sẵn đạt 5/5.
LANGUAGE_NAMES_VI = {
    "en": "tiếng Anh",
    "ja": "tiếng Nhật",
    "zh": "tiếng Trung",
    "ko": "tiếng Hàn",
}

SYSTEM_PROMPT = (
    "Bạn là một dịch giả văn học chuyên nghiệp. Nhiệm vụ của bạn là dịch "
    "văn bản sang TIẾNG VIỆT. Chỉ xuất ra bản dịch tiếng Việt, không giải "
    "thích, không lặp lại nguyên tác, không phiên âm."
)

# Mồi sẵn phần trả lời của model. Không có nó, model hay trả lời bằng đúng
# ngôn ngữ nguồn (rõ nhất với tiếng Nhật). Phần mồi nằm trong prompt nên
# không lọt vào kết quả — sinh ra bao nhiêu thì cắt từ sau prompt bấy nhiêu.
ASSISTANT_PREFILL = "Bản dịch tiếng Việt: "

# Đoạn chỉ gồm ký tự phân cách (***, ---, ===, ◇◇◇ …) thì giữ nguyên, không cần gọi model
_SEPARATOR_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


# ──────────────────────────────────────────────
#  Enums & Data Classes
# ──────────────────────────────────────────────
class TaskStatus(str, Enum):
    PENDING = "pending"
    LOADING = "loading"      # đang nạp model vào GPU
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class TranslationProgress:
    """Tiến độ dịch của một task."""
    task_id: str
    status: TaskStatus
    total_paragraphs: int
    completed_paragraphs: int
    current_paragraph_index: int
    current_original: str = ""
    current_translated: str = ""
    speed: float = 0.0           # đoạn/giây
    eta_seconds: float = 0.0     # thời gian còn lại (giây)
    error_message: str = ""
    message: str = ""            # thông báo trạng thái (VD: "Đang nạp model...")

    @property
    def percentage(self) -> float:
        if self.total_paragraphs == 0:
            return 0.0
        return (self.completed_paragraphs / self.total_paragraphs) * 100


@dataclass
class TranslationTask:
    """Một task dịch đang hoạt động."""
    task_id: str
    title: str
    source_url: str
    source_lang: str
    paragraphs_original: list[str]
    paragraphs_translated: dict[int, str] = field(default_factory=dict)
    model_name: str = DEFAULT_MODEL
    status: TaskStatus = TaskStatus.PENDING
    error_message: str = ""
    # Control flags
    _pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    _cancel_flag: bool = False

    def __post_init__(self):
        self._pause_event.set()  # Không bị pause mặc định

    def pause(self):
        self.status = TaskStatus.PAUSED
        self._pause_event.clear()

    def resume(self):
        self.status = TaskStatus.RUNNING
        self._pause_event.set()

    def cancel(self):
        self._cancel_flag = True
        self.status = TaskStatus.CANCELLED
        self._pause_event.set()  # Unblock nếu đang pause

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_flag

    async def wait_if_paused(self):
        await self._pause_event.wait()


# ──────────────────────────────────────────────
#  Translation Engine
# ──────────────────────────────────────────────
class TranslationEngine:
    """Engine hỗ trợ model AI và Google Translate qua deep-translator."""

    def __init__(
        self,
        glossary: Optional[GlossaryManager] = None,
        batch_size: Optional[int] = None,
        load_in_4bit: Optional[bool] = None,
    ):
        self.glossary = glossary or GlossaryManager()
        self.tasks: dict[str, TranslationTask] = {}
        self.model = None
        self.tokenizer = None
        self._model_loaded = False
        self.current_model_name: Optional[str] = None
        self.is_causal = False
        self._supports_thinking_flag = False
        self._load_lock = threading.Lock()

        self._device = "cuda" if torch and torch.cuda.is_available() else "cpu"
        self._dtype = (
            torch.float16 if torch and self._device == "cuda"
            else torch.float32 if torch
            else None
        )

        # batch_size=None → tự chọn theo VRAM còn trống sau khi nạp model
        self._batch_size_override = batch_size
        self.batch_size = batch_size or 1

        # Ép 4-bit hoặc để None cho engine tự quyết theo dung lượng VRAM
        self._load_in_4bit_override = load_in_4bit

        if torch is None:
            print("[Engine] Chế độ thư viện sẵn sàng; AI model chưa được cài đặt.")
        elif self._device == "cpu":
            print("[Engine] ⚠️  Không tìm thấy GPU CUDA — AI model sẽ chạy rất chậm.")
        else:
            name = torch.cuda.get_device_name(0)
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[Engine] GPU: {name} ({total:.1f} GB VRAM)")

    # ──────────────────────────────
    #  Nạp model
    # ──────────────────────────────
    @staticmethod
    def is_library_provider(model_name: str) -> bool:
        return model_name == DEEP_TRANSLATOR_GOOGLE

    def _should_quantize(self) -> bool:
        """Quyết định có nén 4-bit không (model 1.7B fp16 ~3.8GB không vừa card 4GB)."""
        if self._load_in_4bit_override is not None:
            return self._load_in_4bit_override
        if not torch or self._device != "cuda":
            return False
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return total_gb < 6.0

    def _build_quant_config(self):
        """Trả về BitsAndBytesConfig nếu có thể nén 4-bit, ngược lại None."""
        if not self._should_quantize():
            return None
        try:
            from transformers import BitsAndBytesConfig
            import bitsandbytes  # noqa: F401  (chỉ để kiểm tra đã cài chưa)
        except ImportError:
            total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(
                f"[Engine] ⚠️  VRAM chỉ {total_gb:.1f} GB — model fp16 nhiều khả năng "
                "tràn sang RAM hệ thống và chạy rất chậm.\n"
                "         Cài `pip install bitsandbytes` để engine tự nén 4-bit "
                "(~1.4 GB, nhanh hơn nhiều lần)."
            )
            return None

        print("[Engine] Nén model 4-bit (NF4) để vừa VRAM...")
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=self._dtype,
            bnb_4bit_use_double_quant=True,
        )

    def _unload(self):
        if not self._model_loaded:
            return
        print(f"[Engine] Unloading {self.current_model_name}...")
        self.model = None
        self.tokenizer = None
        if torch and torch.cuda.is_available():
            torch.cuda.empty_cache()
        self._model_loaded = False
        self.current_model_name = None

    def _load_model(self, model_name: str):
        """Tải model vào GPU/CPU. Thread-safe. Unload model cũ nếu đổi model."""
        with self._load_lock:
            if self._model_loaded and self.current_model_name == model_name:
                return
            self._unload()

            if self.is_library_provider(model_name):
                try:
                    from deep_translator import GoogleTranslator  # noqa: F401
                except ImportError as exc:
                    raise RuntimeError(
                        "Chưa cài deep-translator. Chạy: pip install deep-translator"
                    ) from exc

                self.current_model_name = model_name
                self._model_loaded = True
                self.is_causal = False
                # Gửi từng đoạn để dễ pause/cancel và hạn chế lỗi rate limit.
                self.batch_size = 1
                print("[Engine] Google Translate qua deep-translator đã sẵn sàng.")
                return

            if torch is None or AutoConfig is None:
                raise RuntimeError(
                    "Chế độ AI cần PyTorch và Transformers. "
                    "Hãy chạy setup_and_run.bat và chọn cài đặt đầy đủ."
                )

            print(f"[Engine] Loading {model_name} on {self._device} ({self._dtype})...")
            start = time.time()

            config = AutoConfig.from_pretrained(model_name, trust_remote_code=True)

            # ── FIX QUAN TRỌNG ──
            # config.json của NiuTrans/LMT-60-1.7B đặt use_cache=false. Khi generate,
            # điều đó tắt KV cache: mỗi token mới phải tính lại toàn bộ prefix
            # (O(n²) thay vì O(n)) → chậm hàng chục lần.
            config.use_cache = True

            architectures = getattr(config, "architectures", None) or []
            is_causal = any("CausalLM" in arch for arch in architectures)

            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                # Batch generation với decoder-only bắt buộc pad bên trái,
                # nếu không phần sinh ra sẽ lệch khỏi prompt.
                padding_side="left" if is_causal else "right",
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            load_kwargs = {
                "config": config,
                "dtype": self._dtype,
                "trust_remote_code": True,
                "low_cpu_mem_usage": True,
            }
            quant_config = self._build_quant_config()
            if quant_config is not None:
                load_kwargs["quantization_config"] = quant_config
                load_kwargs["device_map"] = {"": 0}

            model_cls = AutoModelForCausalLM if is_causal else AutoModelForSeq2SeqLM
            self.model = model_cls.from_pretrained(model_name, **load_kwargs)

            # Model đã lượng tử hoá được accelerate đặt lên GPU sẵn, không .to() lại
            if quant_config is None:
                self.model = self.model.to(self._device)

            self.model.eval()
            # generation_config được nạp riêng từ generation_config.json nên phải
            # bật cache ở đây nữa, không thì lệnh generate vẫn chạy chậm.
            self.model.generation_config.use_cache = True

            self.is_causal = is_causal
            # Template Qwen3 chỉ bỏ qua thinking khi enable_thinking được truyền false
            template = getattr(self.tokenizer, "chat_template", None) or ""
            self._supports_thinking_flag = "enable_thinking" in template

            self.current_model_name = model_name
            self._model_loaded = True

            self.batch_size = self._batch_size_override or self._auto_batch_size()

            elapsed = time.time() - start
            print(
                f"[Engine] Model loaded in {elapsed:.1f}s "
                f"({'causal' if is_causal else 'seq2seq'}, batch={self.batch_size})"
            )
            self._report_vram()

    def _report_vram(self):
        if self._device != "cuda":
            return
        free, total = torch.cuda.mem_get_info()
        free_gb, total_gb = free / 1024**3, total / 1024**3
        print(f"[Engine] VRAM: {total_gb - free_gb:.2f} GB đã dùng / {total_gb:.2f} GB")
        if free_gb < 0.4:
            print(
                "[Engine] ⚠️  VRAM còn rất ít. Trên Windows, driver sẽ tràn sang RAM "
                "hệ thống thay vì báo lỗi — đó là lý do dịch bị 'đơ'.\n"
                "         Khắc phục: `pip install bitsandbytes` (nén 4-bit), "
                "hoặc dùng model nhỏ hơn."
            )

    def _auto_batch_size(self) -> int:
        """Chọn batch size theo VRAM còn trống sau khi đã nạp model."""
        if self._device != "cuda":
            return 1
        free_gb = torch.cuda.mem_get_info()[0] / 1024**3
        if free_gb < 0.8:
            return 1
        if free_gb < 2.0:
            return 2
        if free_gb < 5.0:
            return 4
        return 8

    # ──────────────────────────────
    #  Dựng prompt
    # ──────────────────────────────
    def _build_prompt(
        self,
        text: str,
        source_lang: str,
        terms: Optional[list[tuple[str, str]]] = None,
    ) -> str:
        if not self.is_causal:
            lang = LANGUAGE_NAMES.get(source_lang, source_lang.upper())
            return f"Translate {lang} to Vietnamese: {text}"

        lang_vi = LANGUAGE_NAMES_VI.get(source_lang, source_lang.upper())

        parts: list[str] = []
        if terms:
            # Model instruct nuốt mất placeholder chèn giữa câu, nên thuật ngữ
            # được nêu thành danh sách ngay trong prompt.
            parts.append("Thuật ngữ bắt buộc dùng đúng:")
            parts.extend(f"- {src} => {dst}" for src, dst in terms)
            parts.append("")
        parts.append(f"Dịch đoạn {lang_vi} sau sang tiếng Việt:")
        parts.append("")
        parts.append(text)
        user_content = "\n".join(parts)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        if getattr(self.tokenizer, "chat_template", None):
            kwargs = {"tokenize": False, "add_generation_prompt": True}
            if self._supports_thinking_flag:
                # ── FIX QUAN TRỌNG ──
                # Qwen3 mặc định bật thinking: mỗi đoạn sẽ sinh khối <think>…</think>
                # dài gấp nhiều lần bản dịch trước khi trả kết quả.
                kwargs["enable_thinking"] = False
            rendered = self.tokenizer.apply_chat_template(messages, **kwargs)
        else:
            rendered = (
                f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
                f"<|im_start|>user\n{user_content}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

        return rendered + ASSISTANT_PREFILL

    @staticmethod
    def _clean_output(text: str) -> str:
        """Bỏ khối reasoning và các tiền tố thừa model hay thêm vào."""
        text = _THINK_BLOCK_RE.sub("", text)
        if "</think>" in text:                      # khối think bị cắt cụt
            text = text.split("</think>")[-1]
        text = text.strip()
        # Model đôi khi mở đầu bằng "Bản dịch:" / "Translation:"
        text = re.sub(
            r"^(bản dịch tiếng việt|bản dịch|translation|vietnamese|tiếng việt)\s*[:：]\s*",
            "", text, flags=re.I,
        )
        return text.strip()

    # ──────────────────────────────
    #  Dịch
    # ──────────────────────────────
    @staticmethod
    def _needs_translation(text: str) -> bool:
        """Đoạn rỗng hoặc chỉ gồm ký tự phân cách thì giữ nguyên."""
        stripped = text.strip()
        return bool(stripped) and not _SEPARATOR_RE.match(stripped)

    def _generate(self, prompts: list[str]) -> list[str]:
        """Chạy generate cho một batch prompt đã dựng sẵn."""
        inputs = self.tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_INPUT_TOKENS,
        ).to(self._device)

        input_len = inputs["input_ids"].shape[1]
        # max_new_tokens động: bản dịch dài xấp xỉ bản gốc, không cần 1024 token cố định
        max_new = min(MAX_NEW_TOKENS_CAP, int(input_len * OUTPUT_LENGTH_RATIO) + 32)

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new,
                do_sample=False,          # dịch thuật cần ổn định, không sampling
                num_beams=1,              # beam search 4 → chậm gấp 4 lần, lợi không đáng
                repetition_penalty=1.05,
                use_cache=True,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        if self.is_causal:
            # Pad bên trái nên mọi dòng đều bắt đầu phần sinh tại cùng vị trí
            outputs = outputs[:, input_len:]

        decoded = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        return [self._clean_output(d) for d in decoded]

    def _generate_with_oom_retry(self, prompts: list[str]) -> list[str]:
        """Chạy batch, tự chia đôi khi hết VRAM thay vì làm hỏng cả task."""
        try:
            return self._generate(prompts)
        except torch.cuda.OutOfMemoryError:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if len(prompts) == 1:
                raise
            half = max(1, len(prompts) // 2)
            self.batch_size = half
            print(f"[Engine] ⚠️  Hết VRAM — giảm batch size xuống {half}")
            return (
                self._generate_with_oom_retry(prompts[:half])
                + self._generate_with_oom_retry(prompts[half:])
            )

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "en",
        model_name: str = DEFAULT_MODEL,
    ) -> list[str]:
        """Dịch một nhóm đoạn văn. Trả về danh sách cùng thứ tự với đầu vào."""
        if not texts:
            return []
        self._load_model(model_name)

        if self.is_library_provider(model_name):
            from deep_translator import GoogleTranslator

            source = DEEP_TRANSLATOR_SOURCE_LANGS.get(source_lang, source_lang)
            translator = GoogleTranslator(source=source, target="vi")
            translated: list[str] = []
            for text in texts:
                processed, mapping = self.glossary.pre_process(text)
                result = translator.translate(processed)
                if not result:
                    raise RuntimeError("Google Translate không trả về nội dung.")
                translated.append(
                    self.glossary.post_process(result, mapping).strip()
                )
            return translated

        if self.is_causal:
            # Model sinh ngôn ngữ nuốt mất placeholder giữa câu, nên thuật ngữ
            # được đưa thẳng vào prompt thay vì thay thế trong text.
            prompts = [
                self._build_prompt(t, source_lang, self.glossary.find_terms(t))
                for t in texts
            ]
            return [r.strip() for r in self._generate_with_oom_retry(prompts)]

        # Model dịch máy Seq2Seq bảo toàn được placeholder nên vẫn dùng cách cũ
        processed, mappings = [], []
        for text in texts:
            proc, mapping = self.glossary.pre_process(text)
            processed.append(proc)
            mappings.append(mapping)

        prompts = [self._build_prompt(p, source_lang) for p in processed]
        results = self._generate_with_oom_retry(prompts)

        return [
            self.glossary.post_process(res, mapping).strip()
            for res, mapping in zip(results, mappings)
        ]

    def _translate_single(
        self,
        text: str,
        source_lang: str = "en",
        model_name: str = DEFAULT_MODEL,
    ) -> str:
        """Dịch một đoạn. Giữ lại cho CLI (translate.py)."""
        if not self._needs_translation(text):
            return text
        return self.translate_batch([text], source_lang, model_name)[0]

    # ──────────────────────────────
    #  Quản lý task
    # ──────────────────────────────
    def create_task(
        self,
        title: str,
        paragraphs: list[str],
        source_url: str = "",
        source_lang: str = "en",
        model_name: str = DEFAULT_MODEL,
    ) -> str:
        """Tạo task dịch mới. Trả về task_id."""
        task_id = str(uuid.uuid4())[:8]
        task = TranslationTask(
            task_id=task_id,
            title=title,
            source_url=source_url,
            source_lang=source_lang,
            paragraphs_original=paragraphs,
            model_name=model_name,
        )
        self.tasks[task_id] = task
        return task_id

    async def translate_task(
        self, task_id: str
    ) -> AsyncGenerator[TranslationProgress, None]:
        """
        Dịch toàn bộ paragraphs của một task.
        Yield tiến độ sau mỗi đoạn — dùng cho SSE stream.
        """
        task = self.tasks.get(task_id)
        if not task:
            yield TranslationProgress(
                task_id=task_id,
                status=TaskStatus.ERROR,
                total_paragraphs=0,
                completed_paragraphs=0,
                current_paragraph_index=0,
                error_message="Task not found",
            )
            return

        total = len(task.paragraphs_original)
        loop = asyncio.get_running_loop()

        def progress(status: TaskStatus, **kwargs) -> TranslationProgress:
            return TranslationProgress(
                task_id=task_id,
                status=status,
                total_paragraphs=total,
                completed_paragraphs=len(task.paragraphs_translated),
                current_paragraph_index=kwargs.pop("index", 0),
                **kwargs,
            )

        # ── Chuẩn bị provider/model ──
        if not (self._model_loaded and self.current_model_name == task.model_name):
            task.status = TaskStatus.LOADING
            if self.is_library_provider(task.model_name):
                loading_message = "Đang kết nối Google Translate..."
            else:
                loading_message = f"Đang nạp model {task.model_name} vào GPU..."
            yield progress(
                TaskStatus.LOADING,
                message=loading_message,
            )

        try:
            # Nạp trong thread pool để không chặn event loop (nếu không, mọi
            # request khác — kể cả nút Huỷ — sẽ treo trong lúc nạp model.
            await loop.run_in_executor(None, self._load_model, task.model_name)
        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error_message = str(e)
            yield progress(TaskStatus.ERROR, error_message=f"Failed to load model: {e}")
            return

        task.status = TaskStatus.RUNNING
        start_time = time.time()

        # ── Gom các đoạn cần dịch ──
        pending: list[int] = []
        for idx, original in enumerate(task.paragraphs_original):
            if idx in task.paragraphs_translated:
                continue
            if not self._needs_translation(original):
                # Dòng phân cách "***", "---" … giữ nguyên, không tốn một lượt generate
                task.paragraphs_translated[idx] = original
                continue
            pending.append(idx)

        done_count = 0
        # Truyện thoại lặp lại nhiều ("...", "Ha ha") — dịch một lần rồi dùng lại
        seen: dict[str, str] = {}

        cursor = 0
        while cursor < len(pending):
            if task.is_cancelled:
                yield progress(TaskStatus.CANCELLED, index=pending[cursor])
                return

            await task.wait_if_paused()
            if task.is_cancelled:
                yield progress(TaskStatus.CANCELLED, index=pending[cursor])
                return

            # Đọc batch_size ngay tại đây, không chốt từ trước: khi gặp OOM,
            # _generate_with_oom_retry đã giảm nó ở vòng lặp trước.
            step = max(1, self.batch_size)
            batch_idx = pending[cursor: cursor + step]
            cursor += len(batch_idx)
            originals = [task.paragraphs_original[i] for i in batch_idx]

            # Chỉ gửi lên GPU đoạn chưa từng gặp — kể cả trùng trong cùng batch
            todo: list[str] = []
            for text in originals:
                if text not in seen and text not in todo:
                    todo.append(text)

            try:
                if todo:
                    results = await loop.run_in_executor(
                        None,
                        self.translate_batch,
                        todo,
                        task.source_lang,
                        task.model_name,
                    )
                    seen.update(zip(todo, results))

                for idx, original in zip(batch_idx, originals):
                    task.paragraphs_translated[idx] = seen.get(original, "")
                    done_count += 1

                    elapsed = time.time() - start_time
                    speed = done_count / elapsed if elapsed > 0 else 0
                    remaining = len(pending) - done_count
                    eta = remaining / speed if speed > 0 else 0

                    yield progress(
                        TaskStatus.RUNNING,
                        index=idx,
                        current_original=original,
                        current_translated=task.paragraphs_translated[idx],
                        speed=round(speed, 2),
                        eta_seconds=round(eta, 1),
                    )

            except Exception as e:
                # Lỗi cả batch — đánh dấu từng đoạn rồi đi tiếp
                for idx, original in zip(batch_idx, originals):
                    task.paragraphs_translated[idx] = f"[ERROR: {e}] {original}"
                    done_count += 1
                    yield progress(
                        TaskStatus.RUNNING,
                        index=idx,
                        current_original=original,
                        current_translated=f"[ERROR] {e}",
                        error_message=str(e),
                    )

            await asyncio.sleep(0)  # nhường event loop xử lý pause/cancel

        task.status = TaskStatus.COMPLETED
        yield progress(
            TaskStatus.COMPLETED,
            index=max(0, total - 1),
        )

    def get_task(self, task_id: str) -> Optional[TranslationTask]:
        return self.tasks.get(task_id)

    def get_translated_paragraphs(self, task_id: str) -> list[str]:
        """Lấy danh sách đoạn đã dịch (theo thứ tự)."""
        task = self.tasks.get(task_id)
        if not task:
            return []
        return [
            task.paragraphs_translated.get(i, "")
            for i in range(len(task.paragraphs_original))
        ]

    def update_translation(self, task_id: str, index: int, text: str) -> bool:
        """Cập nhật bản dịch tại vị trí index (cho tính năng inline edit)."""
        task = self.tasks.get(task_id)
        if not task or index < 0 or index >= len(task.paragraphs_original):
            return False
        task.paragraphs_translated[index] = text
        return True
