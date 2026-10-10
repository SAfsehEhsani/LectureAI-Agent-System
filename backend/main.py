import sys, os, asyncio, logging, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch PyAV 14+ / 19+ metadata_errors issue in faster-whisper
try:
    import av
    if hasattr(av, "open"):
        _orig_av_open = av.open
        def _safe_av_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _orig_av_open(*args, **kwargs)
        av.open = _safe_av_open
    try:
        import faster_whisper.audio
        faster_whisper.audio.av.open = _safe_av_open
    except Exception:
        pass
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from pipeline import (
    process_youtube, process_uploaded_video, process_transcript,
    export_markdown, export_pdf, render_one_clip, cut_youtube_clip
)
from backend.storage import save_pack, list_packs, get_pack, delete_pack, get_proof_certificate

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lecturelens")

app = FastAPI(title="LectureLens AI")

# Allow env-configured origins for deployment; fallback to localhost for dev
_origins_env = os.getenv("CORS_ORIGINS", "")
ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_CLIPS = int(os.getenv("MAX_CLIPS", 3))


async def _run(fn, *args):
    """Run blocking pipeline function in a thread so FastAPI stays responsive."""
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn, *args)
    except Exception as e:
        log.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "groq_key_configured": bool(os.getenv("GROQ_API_KEY", "")),
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    }


@app.get("/sample")
async def get_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_lecture.srt")
    if os.path.exists(sample_path):
        with open(sample_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filename": "sample_lecture.srt", "content": content}
    return {"filename": "sample_lecture.srt", "content": ""}


@app.post("/generate/youtube")
async def gen_youtube(url: str = Form(...)):
    res = await _run(process_youtube, url, MAX_CLIPS)
    try:
        save_pack(res, "youtube")
    except Exception as e:
        log.warning(f"Failed to persist pack: {e}")
    return res


@app.post("/generate/upload")
async def gen_upload(file: UploadFile = File(...)):
    suffix = "." + file.filename.rsplit(".", 1)[-1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        # Stream write to avoid loading entire video into memory
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
        tmp.close()
        res = await _run(process_uploaded_video, tmp.name, file.filename, MAX_CLIPS)
        try:
            save_pack(res, "upload")
        except Exception as e:
            log.warning(f"Failed to persist pack: {e}")
        return res
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Upload error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/transcript")
async def gen_transcript(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    res = await _run(process_transcript, raw, file.filename, MAX_CLIPS)
    try:
        save_pack(res, "transcript")
    except Exception as e:
        log.warning(f"Failed to persist pack: {e}")
    return res


@app.get("/history")
async def get_history():
    return list_packs()


@app.get("/history/{pack_id}")
async def get_history_item(pack_id: str):
    pack = get_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Learning pack not found")
    return pack


@app.delete("/history/{pack_id}")
async def del_history_item(pack_id: str):
    delete_pack(pack_id)
    return {"status": "deleted", "id": pack_id}


@app.get("/history/{pack_id}/proof")
async def get_pack_proof(pack_id: str):
    cert = get_proof_certificate(pack_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Learning pack not found")
    return Response(
        content=cert,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={pack_id}_proof_audit.txt"}
    )


@app.post("/clips/render")
async def clip_render(
    video_path: str = Form(None),
    source_url: str = Form(None),
    start: float = Form(...),
    end: float = Form(...),
    title: str = Form("clip"),
    segments_json: str = Form(None)
):
    try:
        segments = json.loads(segments_json) if segments_json else None
    except Exception:
        segments = None

    try:
        if video_path and os.path.exists(video_path):
            clip_path = await _run(render_one_clip, video_path, start, end, segments, title)
        elif source_url and ("youtube.com" in source_url or "youtu.be" in source_url):
            clip_path = await _run(cut_youtube_clip, source_url, start, end, segments, title)
        else:
            raise HTTPException(status_code=400, detail="Source video is not available on server for clipping.")

        safe_name = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_") or "clip"
        return FileResponse(clip_path, media_type="video/mp4", filename=f"{safe_name}.mp4")
    except Exception as e:
        log.exception("Clip cutting error")
        raise HTTPException(status_code=500, detail=f"FFmpeg clip cutting failed: {e}")


@app.post("/export/markdown")
async def exp_markdown(data: dict):
    md = export_markdown(data)
    return Response(
        content=md, media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=learning_pack.md"},
    )


@app.post("/export/pdf")
async def exp_pdf(data: dict):
    loop = asyncio.get_event_loop()
    pdf = await loop.run_in_executor(None, export_pdf, data)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=learning_pack.pdf"},
    )


@app.post("/export/json")
async def exp_json(data: dict):
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=learning_pack.json"},
    )
