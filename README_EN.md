# 📖 Novel Translator — AI-Powered Novel Translation

**[Tiếng Việt](README.md) | [English](README_EN.md)**

<div align="center">

**A web application that automatically translates novels from web pages into Vietnamese**  
**with lightweight Qwen3-0.6B, NiuTrans, and Google Translate support**

`FastAPI` · `PyTorch CUDA` · `Qwen3` · `NiuTrans` · `SSE Streaming` · `EPUB Export`

</div>

---

## ✨ Features

### 🔍 Smart Content Extraction

- Automatically detects chapter structures on popular novel websites.
- Supports Witch Cult Translations, Syosetu (Narou), Kakuyomu, Royal Road, and generic HTML pages.
- Removes advertisements, navigation elements, and donation banners while preserving the story content.

### 🤖 Local AI Translation

- Runs on NVIDIA GPUs in `float16`, with optional 4-bit quantization for low-VRAM cards.
- Supports `NiuTrans/LMT-60-1.7B` and `Qwen/Qwen3-0.6B` (approximately 1.4 GB).
- Lets you select a model from the web interface or CLI.
- Accepts story context to improve character gender, world-building terms, and writing style.
- Translates paragraph by paragraph while preserving the original layout.
- Uses batch translation, skips separator lines, and caches repeated paragraphs.
- Supports pause, resume, and cancel operations.
- Automatically reduces the batch size after an out-of-memory error.

### 🌐 Translation Without a GPU

- Includes Google Translate through `deep-translator`.
- Runs with the lightweight dependency set without PyTorch, CUDA, or a local model.
- Supports English, Japanese, Chinese, and Korean to Vietnamese translation.
- Still applies glossary terms to translated output.

> Google Translate mode requires an internet connection and sends the content to Google's translation service.

### 📚 Glossary Management

- Create, edit, and delete terms or proper names, such as `Sword Saint → Kiếm Thánh`.
- Injects relevant terms into CausalLM prompts or uses placeholders with Seq2Seq models.
- Imports and exports glossary files in JSON or TXT format.

### 🖥️ Modern Web Interface

- Dark glassmorphism design.
- Live side-by-side original and translated text panes.
- Real-time progress, translation speed, and ETA through SSE.
- Inline editing for every translated paragraph.

### 📦 Export Formats

| Format | Description |
|---|---|
| Markdown (`.md`) | YAML frontmatter; suitable for Obsidian and Notion |
| EPUB (`.epub`) | Cover, table of contents, and reader-friendly CSS for Kindle, Kobo, and Boox |
| Text (`.txt`) | Simple plain-text output |

Vietnamese filenames are supported. EPUB output is normalized to Unicode NFC, encoded as UTF-8, and cleaned of invalid XML characters.

---

## 🚀 Installation and Usage

### Quick Setup on Windows

Double-click `setup_and_run.bat`. The menu provides these main options:

- `[1]` Install Google Translate mode — lightweight and GPU-free.
- `[2]` Install local AI mode — install dependencies and select a model to download.
- `[3]` Run the application and open `http://localhost:8000`.
- `[5]` Uninstall selected models or dependencies.

The script creates a project-local `.venv`, installs the selected dependency group, and reuses already downloaded packages and Hugging Face model files. If PyTorch or Transformers is unavailable, the application still starts and automatically selects Google Translate.

> Keep `setup_and_run.bat` with Windows `CRLF` line endings. The repository enforces this through `.gitattributes` so that its `goto` commands work correctly in `cmd.exe`.

### Google Translate Only

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-library.txt
python app.py
```

Open `http://localhost:8000`, then select **Google Translate — no GPU required**.

### Local AI Requirements

- Python 3.14 or later.
- An NVIDIA GPU with CUDA support.
- A compatible NVIDIA driver/CUDA 12.x environment.
- Approximately 4 GB of disk space for the first model download.

#### VRAM Recommendations

`NiuTrans/LMT-60-1.7B` uses approximately 3.8 GB of VRAM in `float16`. For a smaller and faster option, use `Qwen/Qwen3-0.6B`, whose weights are approximately 1.4 GB.

| GPU VRAM | Recommendation |
|---|---|
| Less than 6 GB | Install `bitsandbytes` and use automatic 4-bit quantization |
| 6–8 GB | Use regular fp16 inference |
| 8 GB or more | Use fp16 with a larger batch size |

On Windows, insufficient VRAM may silently spill into system RAM through PCIe instead of immediately raising an error. Translation can therefore become extremely slow even while the process remains active.

### 1. Install CUDA-Enabled PyTorch

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

PyTorch is intentionally excluded from `requirements.txt` to prevent pip from replacing the CUDA build with a CPU-only build from PyPI.

### 2. Install the Remaining Dependencies

```bash
pip install -r requirements.txt
```

### 3. Optional: Enable 4-Bit Quantization

Recommended for GPUs with less than 6 GB of VRAM:

```bash
pip install bitsandbytes
```

### 4. Start the Web Application

```bash
python app.py
```

Open **http://localhost:8000**. The first translation can take several minutes while the selected model is downloaded and loaded.

### 5. Optional CLI Usage

```bash
# Translate a URL to Markdown with the default model
python translate.py --url "https://witchculttranslation.com/..." --format md

# Use the lightweight model with story context
python translate.py --file chapter.txt --model "Qwen/Qwen3-0.6B" \
  --context "Medieval fantasy; keep a formal narrative tone" --format epub

# Translate direct text to TXT
python translate.py --text "Hello world" --format txt

# Use Google Translate without a GPU
python translate.py --text "Hello world" --model "deep-translator/google" --format txt

# Translate a file and create bilingual output
python translate.py --file chapter.txt --lang en --format epub --bilingual
```

---

## 🩺 Troubleshooting

| Symptom | Cause and solution |
|---|---|
| Translation takes several minutes per paragraph | VRAM has spilled into system RAM. Install `bitsandbytes`, use a smaller model, or close GPU-heavy applications. |
| The interface appears frozen after starting | The model is loading. Check the terminal for `[Engine] Loading …` and `Model loaded in …s`. |
| `CUDA out of memory` | The engine reduces the batch size automatically. If batch size 1 still fails, use 4-bit quantization or a smaller model. |
| The application uses the CPU despite an NVIDIA GPU | Verify with `python -c "import torch; print(torch.cuda.is_available())"`. Reinstall CUDA-enabled PyTorch if it prints `False`. |
| Output contains source text or explanations | Small models may drift on long passages. The engine removes `<think>` blocks and common translation prefixes, but manual review may still be needed. |
| `/api/*` returns 404 or 405 | You opened the frontend with VS Code Live Server. Run `python app.py` and use port `8000`. |
| Every request remains pending on Windows | The terminal may be paused by QuickEdit Mode. Press `Esc`, then disable QuickEdit Mode in the console properties. |
| Model download fails or times out | Configure an `HF_ENDPOINT` mirror or download the model into the Hugging Face cache manually. |

---

## 📂 Project Structure

```text
vietnovel-ai-translator/
├── app.py                    # FastAPI server, API routes, and SSE streaming
├── translate_engine.py       # Translation, batching, model loading, and task control
├── scraper.py                # Domain-specific and generic web scrapers
├── glossary_manager.py       # Glossary persistence and processing
├── exporter.py               # Markdown, EPUB, and TXT generation
├── translate.py              # Command-line interface
├── requirements.txt          # Local AI dependencies (PyTorch excluded)
├── requirements-library.txt  # Lightweight Google Translate dependencies
├── setup_and_run.bat         # Windows setup and launcher menu
├── static/
│   ├── index.html            # Single-page web interface
│   ├── style.css             # Glassmorphism design system
│   └── app.js                # SSE, editor, glossary, and UI logic
└── storage/                  # Generated files and glossary data
    └── glossary.json         # Created automatically at runtime
```

---

## 🔌 API Endpoints

### Scraping and Input

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/scrape` | Extract a chapter from a URL |
| `POST` | `/api/parse-text` | Create a task from pasted text |

### Translation

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/translate/start` | Prepare a task with `model_name` and `story_context` |
| `GET` | `/api/translate/stream/{task_id}` | Run translation and stream real-time SSE progress |
| `POST` | `/api/translate/pause/{task_id}` | Pause a task |
| `POST` | `/api/translate/resume/{task_id}` | Resume a task |
| `POST` | `/api/translate/cancel/{task_id}` | Cancel a task |
| `GET` | `/api/translate/status/{task_id}` | Get the current status and results |
| `POST` | `/api/translate/edit/{task_id}` | Edit a translated paragraph |

### Export and Glossary

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/export/{task_id}/{fmt}` | Download `md`, `epub`, or `txt`; supports `bilingual` and `filename` query parameters |
| `GET` | `/api/glossary` | List glossary terms |
| `POST` | `/api/glossary` | Add or update a term |
| `DELETE` | `/api/glossary` | Delete a term |
| `DELETE` | `/api/glossary/all` | Delete every term |
| `POST` | `/api/glossary/import` | Import a glossary file |
| `GET` | `/api/glossary/export/{fmt}` | Export the glossary as JSON or TXT |

An SSE `progress` event includes the task state, completion counts, percentage, current paragraph, speed, ETA, and error information. A completed stream ends with a `done` event.

---

## 📝 Glossary Format

### JSON

```json
[
  { "source": "Sword Saint", "target": "Kiếm Thánh" },
  { "source": "Witch Factor", "target": "Nhân tố Phù thủy" },
  { "source": "Subaru", "target": "Subaru", "case_sensitive": true }
]
```

### TXT

```text
Sword Saint = Kiếm Thánh
Witch Factor = Nhân tố Phù thủy
Subaru = Subaru
```

The TXT importer accepts `=`, `:`, or a tab as the separator. Lines beginning with `#` are ignored.

Causal language models receive only the relevant glossary terms in their prompt. Seq2Seq models use placeholders that are restored after translation. Glossary entries are instructions rather than absolute constraints for CausalLM models, so important proper names should still be reviewed.

---

## 🔒 Security Notes

This application is intended to run locally. Its default configuration:

- Binds to `0.0.0.0:8000`, making it reachable from the local network.
- Allows all CORS origins.
- Does not provide authentication.
- Accepts arbitrary URLs in `/api/scrape`, which can introduce SSRF risk.

Do not expose the default server directly to the internet. On an untrusted network, change the server host in `app.py` to `127.0.0.1`. A public deployment should also restrict CORS, add authentication, and validate outbound scrape URLs.

---

## ⚠️ Current Limitations

- Tasks are stored in memory and are lost when the server stops.
- The application translates one chapter at a time and does not yet provide a multi-chapter queue.
- Translation quality depends on the selected model; small models can omit or reinterpret complex passages.
- CausalLM glossary terms are prompt instructions and are not guaranteed to be applied perfectly.
- Japanese literary prose can be harder than English and may require additional review.

---

## 🤝 Contributing

Read [AGENTS.md](AGENTS.md) before changing the source code. It documents the project structure, coding conventions, testing expectations, and pull request requirements.

Suggested workflow:

1. Create a dedicated branch and keep each commit focused on one change.
2. Follow PEP 8 for Python and preserve the existing HTML, CSS, and JavaScript conventions.
3. Run the syntax check:

   ```bash
   python -m compileall app.py exporter.py glossary_manager.py scraper.py translate.py translate_engine.py
   ```

4. Manually test all affected flows, including URL/text input, SSE progress, pause/resume/cancel, glossary operations, and exports.
5. Describe user-visible changes and verification steps in the pull request. Include screenshots for changes under `static/`.

Do not commit model caches, secrets, `__pycache__/`, personal `storage/glossary.json`, or generated translation files.

---

## 📄 License

This project is distributed under the terms of the [LICENSE](LICENSE) file.
