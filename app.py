"""
app.py — FastAPI Server cho Web App Dịch Truyện Tự Động
Mount static files, API endpoints, SSE streaming.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from scraper import scrape_chapter, parse_direct_text, ChapterData
from glossary_manager import GlossaryManager
from translate_engine import (
    TranslationEngine,
    TaskStatus,
    DEFAULT_MODEL,
    DEEP_TRANSLATOR_GOOGLE,
    AI_RUNTIME_AVAILABLE,
    DEEP_TRANSLATOR_AVAILABLE,
    MAX_STORY_CONTEXT_CHARS,
    LIGHTWEIGHT_MODEL,
    get_downloaded_ai_models,
)
from exporter import export_markdown, export_epub, export_txt


from fastapi.middleware.cors import CORSMiddleware

# ──────────────────────────────────────────────
#  App Setup
# ──────────────────────────────────────────────
app = FastAPI(title="Novel Translator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tạo thư mục storage nếu chưa có
Path("storage").mkdir(exist_ok=True)

# Khởi tạo services
glossary = GlossaryManager()
engine = TranslationEngine(glossary=glossary)


# ──────────────────────────────────────────────
#  Request/Response Models
# ──────────────────────────────────────────────
class ScrapeRequest(BaseModel):
    url: str

class DirectTextRequest(BaseModel):
    text: str
    title: str = "Direct Input"
    lang: str = "en"

class TranslateStartRequest(BaseModel):
    task_id: Optional[str] = None  # Dùng lại task_id nếu đã scrape
    title: str = ""
    paragraphs: list[str] = []
    source_url: str = ""
    source_lang: str = "en"
    model_name: str = DEFAULT_MODEL
    story_context: str = ""

class GlossaryAddRequest(BaseModel):
    source: str
    target: str
    case_sensitive: bool = False
    notes: str = ""

class GlossaryRemoveRequest(BaseModel):
    source: str

class EditTranslationRequest(BaseModel):
    index: int
    text: str

class ExportRequest(BaseModel):
    bilingual: bool = False


# ──────────────────────────────────────────────
#  Scraper API
# ──────────────────────────────────────────────
@app.post("/api/scrape")
async def api_scrape(req: ScrapeRequest):
    """Trích xuất nội dung chương từ URL."""
    try:
        chapter = await asyncio.get_event_loop().run_in_executor(
            None, scrape_chapter, req.url
        )
        # Tạo task luôn để giữ dữ liệu
        task_id = engine.create_task(
            title=chapter.title,
            paragraphs=chapter.paragraphs,
            source_url=chapter.source_url,
            source_lang=chapter.source_lang,
        )
        return {
            "task_id": task_id,
            "title": chapter.title,
            "paragraphs": chapter.paragraphs,
            "total": len(chapter.paragraphs),
            "source_lang": chapter.source_lang,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/parse-text")
async def api_parse_text(req: DirectTextRequest):
    """Tạo task từ văn bản trực tiếp."""
    chapter = parse_direct_text(req.text, req.title, req.lang)
    task_id = engine.create_task(
        title=chapter.title,
        paragraphs=chapter.paragraphs,
        source_url="",
        source_lang=chapter.source_lang,
    )
    return {
        "task_id": task_id,
        "title": chapter.title,
        "paragraphs": chapter.paragraphs,
        "total": len(chapter.paragraphs),
        "source_lang": chapter.source_lang,
    }


# ──────────────────────────────────────────────
#  Translation API
# ──────────────────────────────────────────────
@app.get("/api/config")
async def api_config():
    """Cho frontend biết provider nào đã được cài và provider mặc định."""
    requested_default = os.getenv("DEFAULT_TRANSLATION_PROVIDER", "")
    downloaded_models = get_downloaded_ai_models()
    if requested_default == DEEP_TRANSLATOR_GOOGLE and DEEP_TRANSLATOR_AVAILABLE:
        default_provider = DEEP_TRANSLATOR_GOOGLE
    elif AI_RUNTIME_AVAILABLE:
        if LIGHTWEIGHT_MODEL in downloaded_models or not downloaded_models:
            default_provider = LIGHTWEIGHT_MODEL
        else:
            default_provider = downloaded_models[0]
    elif DEEP_TRANSLATOR_AVAILABLE:
        default_provider = DEEP_TRANSLATOR_GOOGLE
    else:
        default_provider = DEFAULT_MODEL

    return {
        "default_provider": default_provider,
        "ai_available": AI_RUNTIME_AVAILABLE,
        "deep_translator_available": DEEP_TRANSLATOR_AVAILABLE,
        "downloaded_ai_models": downloaded_models,
    }


@app.post("/api/translate/start")
async def api_translate_start(req: TranslateStartRequest):
    """Đánh dấu task sẵn sàng dịch. Client phải gọi /api/translate/stream để bắt đầu."""
    task_id = req.task_id

    if not task_id:
        if not req.paragraphs:
            raise HTTPException(400, "No paragraphs or task_id provided")
        task_id = engine.create_task(
            title=req.title,
            paragraphs=req.paragraphs,
            source_url=req.source_url,
            source_lang=req.source_lang,
            model_name=req.model_name,
            story_context=req.story_context,
        )

    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    task.model_name = req.model_name
    task.story_context = req.story_context.strip()[:MAX_STORY_CONTEXT_CHARS]

    return {"task_id": task_id, "status": "ready"}


@app.get("/api/translate/stream/{task_id}")
async def api_translate_stream(task_id: str):
    """SSE stream: vừa chạy dịch vừa stream tiến độ real-time."""
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    async def event_generator():
        async for progress in engine.translate_task(task_id):
            data = {
                "task_id": progress.task_id,
                "status": progress.status.value,
                "total": progress.total_paragraphs,
                "completed": progress.completed_paragraphs,
                "percentage": round(progress.percentage, 1),
                "index": progress.current_paragraph_index,
                "original": progress.current_original,
                "translated": progress.current_translated,
                "speed": progress.speed,
                "eta": progress.eta_seconds,
                "error": progress.error_message,
                "message": progress.message,
            }
            yield {"event": "progress", "data": json.dumps(data, ensure_ascii=False)}

        yield {"event": "done", "data": json.dumps({"task_id": task_id, "status": "completed"})}

    return EventSourceResponse(event_generator())


@app.post("/api/translate/pause/{task_id}")
async def api_translate_pause(task_id: str):
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.pause()
    return {"task_id": task_id, "status": "paused"}


@app.post("/api/translate/resume/{task_id}")
async def api_translate_resume(task_id: str):
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.resume()
    return {"task_id": task_id, "status": "resumed"}


@app.post("/api/translate/cancel/{task_id}")
async def api_translate_cancel(task_id: str):
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.cancel()
    return {"task_id": task_id, "status": "cancelled"}


@app.get("/api/translate/status/{task_id}")
async def api_translate_status(task_id: str):
    """Lấy trạng thái hiện tại của task."""
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    completed = len(task.paragraphs_translated)
    total = len(task.paragraphs_original)

    return {
        "task_id": task_id,
        "status": task.status.value,
        "title": task.title,
        "total": total,
        "completed": completed,
        "percentage": round((completed / total * 100) if total > 0 else 0, 1),
        "paragraphs_original": task.paragraphs_original,
        "paragraphs_translated": engine.get_translated_paragraphs(task_id),
    }


# ──────────────────────────────────────────────
#  Edit Translation
# ──────────────────────────────────────────────
@app.post("/api/translate/edit/{task_id}")
async def api_edit_translation(task_id: str, req: EditTranslationRequest):
    """Chỉnh sửa bản dịch tại vị trí index."""
    success = engine.update_translation(task_id, req.index, req.text)
    if not success:
        raise HTTPException(400, "Invalid task_id or index")
    return {"ok": True}


# ──────────────────────────────────────────────
#  Export API
# ──────────────────────────────────────────────
@app.get("/api/export/{task_id}/{fmt}")
async def api_export(
    task_id: str,
    fmt: str,
    bilingual: bool = False,
    filename: Optional[str] = None,
):
    """Xuất file dịch. fmt: md, epub, txt"""
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    translated = engine.get_translated_paragraphs(task_id)

    if fmt == "md":
        path = export_markdown(
            title=task.title,
            paragraphs_original=task.paragraphs_original,
            paragraphs_translated=translated,
            source_url=task.source_url,
            source_lang=task.source_lang,
            bilingual=bilingual,
            filename=filename,
        )
    elif fmt == "epub":
        path = export_epub(
            title=task.title,
            paragraphs_original=task.paragraphs_original,
            paragraphs_translated=translated,
            source_url=task.source_url,
            source_lang=task.source_lang,
            bilingual=bilingual,
            filename=filename,
        )
    elif fmt == "txt":
        path = export_txt(
            title=task.title,
            paragraphs_translated=translated,
            source_url=task.source_url,
            filename=filename,
        )
    else:
        raise HTTPException(400, f"Unsupported format: {fmt}")

    filename = path.name
    media_type = {
        "md": "text/markdown",
        "epub": "application/epub+zip",
        "txt": "text/plain",
    }.get(fmt, "application/octet-stream")

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type=media_type,
    )


# ──────────────────────────────────────────────
#  Glossary API
# ──────────────────────────────────────────────
@app.get("/api/glossary")
async def api_glossary_list():
    return {"entries": glossary.get_all(), "count": glossary.count()}


@app.post("/api/glossary")
async def api_glossary_add(req: GlossaryAddRequest):
    entry = glossary.add(req.source, req.target, req.case_sensitive, req.notes)
    return {
        "ok": True,
        "entry": {"source": entry.source, "target": entry.target},
        "count": glossary.count(),
    }


@app.delete("/api/glossary")
async def api_glossary_remove(req: GlossaryRemoveRequest):
    removed = glossary.remove(req.source)
    return {"ok": removed, "count": glossary.count()}


@app.delete("/api/glossary/all")
async def api_glossary_clear():
    glossary.clear()
    return {"ok": True, "count": 0}


@app.post("/api/glossary/import")
async def api_glossary_import(
    file: UploadFile = File(...),
):
    """Import glossary từ file JSON hoặc TXT."""
    content = (await file.read()).decode("utf-8")

    if file.filename and file.filename.endswith(".json"):
        count = glossary.import_json(content)
    else:
        count = glossary.import_txt(content)

    return {"ok": True, "imported": count, "total": glossary.count()}


@app.get("/api/glossary/export/{fmt}")
async def api_glossary_export(fmt: str):
    """Export glossary ra file JSON hoặc TXT."""
    if fmt == "json":
        content = glossary.export_json()
        media_type = "application/json"
        filename = "glossary.json"
    elif fmt == "txt":
        content = glossary.export_txt()
        media_type = "text/plain"
        filename = "glossary.txt"
    else:
        raise HTTPException(400, "Format must be json or txt")

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ──────────────────────────────────────────────
#  Static Files & Root
# ──────────────────────────────────────────────
# Mount static files LAST (after API routes)
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ──────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
