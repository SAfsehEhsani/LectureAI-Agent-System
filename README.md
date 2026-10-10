# 🎓 LectureLens AI — Lecture to Learning Pack

Deploy Link : https://lecture-ai-agent-system-6plw.vercel.app


Loom Video : https://drive.google.com/file/d/1P9KhSK-4ZkHjnO4AYKKKr0qq12aMYlMr/view?usp=sharing

Turn any long lecture (60+ minutes) into a complete learning pack: timestamped chapters, revision notes, evidence-backed quiz questions, and short-clip suggestions — all powered by Groq's free LLM API and local Whisper transcription.


---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Models & APIs & Tools Used](#models--apis--tools-used)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [How to Run Locally](#how-to-run-locally)
7. [Environment Variables](#environment-variables)
8. [API Endpoints](#api-endpoints)
9. [Cost](#cost)
10. [How It Was Tested](#how-it-was-tested)
11. [Known Limitations & Possible Breaks](#known-limitations--possible-breaks)
12. [Deploy to Render](#deploy-to-render)

---

## What It Does

| Feature | Detail |
|---------|--------|
| **3 input modes** | YouTube URL, video file upload, transcript file (SRT / VTT / TXT / JSON) |
| **Auto chaptering** | Lecture split into 5-minute chunks → each chunk titled and summarised |
| **Revision notes** | Structured Markdown notes with headings and bullet points |
| **Quiz** | 8 questions with 4 options, correct answer, explanation, and verbatim transcript evidence |
| **Clip suggestions** | Up to 3–5 timestamp ranges (30–90 s each) with reasons |
| **Exports** | Download as Markdown, JSON, or PDF |
| **Optional clip cutting** | FFmpeg cuts actual MP4 clips with burned-in phrase subtitles |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     USER BROWSER                        │
│              React + Vite  (port 5173)                  │
│   [YouTube tab] [Upload Video tab] [Transcript tab]     │
│         ↓ FormData POST via axios ↓                     │
└─────────────────────┬───────────────────────────────────┘
                      │  HTTP  /api/*  (proxied in dev)
                      ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend  (port 8000)               │
│                                                         │
│  POST /generate/youtube   →  process_youtube()          │
│  POST /generate/upload    →  process_uploaded_video()   │
│  POST /generate/transcript→  process_transcript()       │
│  POST /export/markdown    →  export_markdown()          │
│  POST /export/pdf         →  export_pdf()               │
│  POST /export/json        →  (inline JSON response)     │
│  GET  /health             →  key + model status         │
│                                                         │
│  All blocking calls run in ThreadPoolExecutor           │
│  so the async event loop never blocks                   │
└──────┬──────────────┬──────────────────────────────────┘
       │              │
       ▼              ▼
┌────────────┐  ┌─────────────────────────────────────────┐
│  YouTube   │  │           pipeline.py                   │
│  captions  │  │                                         │
│  (free,    │  │  1. get_youtube_captions()              │
│  no key)   │  │     └─ youtube-transcript-api           │
└────────────┘  │                                         │
                │  2. [fallback] download_youtube()        │
┌────────────┐  │     └─ yt-dlp                           │
│  Local     │  │                                         │
│  Whisper   │  │  3. [fallback] transcribe_video()       │
│  (CPU,     │  │     └─ faster-whisper (base model)      │
│  no cost)  │  │                                         │
└────────────┘  │  4. chunk_segments()  [5-min windows]   │
                │                                         │
                │  5. Per-chunk → call_ai()  ──────────────────┐
                │     "Summarise this chunk"                    │
                │     ← title, summary, key_points             │
                │                                              ▼
                │  6. Final synthesis → call_ai()    ┌──────────────────┐
                │     "Build notes + quiz + clips"   │  Groq API        │
                │     ← notes_markdown, quiz, clips  │  llama-3.3-70b   │
                │                                    │  -versatile      │
                │  7. build_result()                 │  (free tier)     │
                │     → chapters, notes, quiz,       └──────────────────┘
                │       clips, metadata
                │
                │  8. export_markdown() / export_pdf()
                │     └─ ReportLab (PDF)
                │
                │  9. [optional] render_video_clips()
                │     └─ FFmpeg (system install)
                └─────────────────────────────────────────┘
```

### Data flow summary

```
Input
  └─► Transcript segments  [{start, end, text}, ...]
        └─► 5-min chunks
              └─► Groq (per chunk) → chunk summary
                    └─► Groq (final) → notes + quiz + clips
                          └─► JSON result → React UI → exports
```

---

## Models & APIs & Tools Used

### AI / LLM

| Tool | Purpose | Cost |
|------|---------|------|
| **Groq API** — `llama-3.3-70b-versatile` | Chunk summarisation + final notes/quiz/clips generation | Free tier (rate-limited); see [console.groq.com](https://console.groq.com) |
| OpenAI Python SDK (`openai>=1.50`) | Used as the HTTP client pointed at `https://api.groq.com/openai/v1` — Groq is OpenAI-compatible | — |

### Transcription

| Tool | Purpose | Cost |
|------|---------|------|
| **youtube-transcript-api** | Fetches YouTube auto/manual captions directly — no download needed | Free |
| **yt-dlp** | Downloads YouTube video when captions are unavailable | Free |
| **faster-whisper** (`base` model) | Local CPU speech-to-text for uploaded videos or when captions fail | Free — runs on your machine; model ~150 MB downloaded once |
| **ctranslate2** | Required runtime for faster-whisper | Free |

### Backend

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.10 – 3.13 | Runtime |
| **FastAPI** | ≥ 0.111 | REST API server |
| **Uvicorn** | ≥ 0.30 | ASGI server |
| **python-multipart** | ≥ 0.0.9 | File upload parsing |
| **python-dotenv** | ≥ 1.0 | Loads `backend/.env` |
| **ReportLab** | ≥ 4.2 | PDF generation |
| **FFmpeg** | system install | Optional: cuts MP4 clips and burns subtitles |

### Frontend

| Tool | Version | Purpose |
|------|---------|---------|
| **React** | 19 | UI framework |
| **Vite** | 8 | Dev server + production build |
| **axios** | 1.x | HTTP requests to backend |
| **react-markdown** | 10.x | Renders AI-generated notes as HTML |

---

## Project Structure

```
LectureLens_AI_Grok/
├── backend/
│   ├── .env                  ← Groq key + config (never commit)
│   ├── main.py               ← FastAPI app, all endpoints
│   └── requirements.txt      ← Python dependencies
├── frontend/
│   ├── public/
│   │   └── favicon.svg
│   ├── src/
│   │   ├── App.jsx           ← Full React UI
│   │   ├── App.css           ← Light theme styles
│   │   ├── index.css         ← Body reset
│   │   └── main.jsx          ← React entry point
│   ├── .env.example          ← Frontend env template
│   ├── index.html
│   ├── package.json
│   └── vite.config.js        ← Dev proxy: /api → localhost:8000
├── tests/
│   └── test_pipeline.py      ← 11 unit tests
├── pipeline.py               ← All processing logic
├── .env.example              ← Backend env template
├── .gitignore
├── Procfile                  ← Railway / Heroku deploy
├── render.yaml               ← Render.com one-click deploy
├── pitch_deck_outline.md
└── README.md
```

---

## Prerequisites

### Required

- **Python 3.10 – 3.13** — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Groq API key** (free) — [console.groq.com](https://console.groq.com) → API Keys → Create

### Optional (only needed for actual video clip cutting)

- **FFmpeg** — [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
  - Windows: download a build, extract, add the `bin/` folder to your system PATH
  - Verify: `ffmpeg -version` in a new terminal

> Without FFmpeg the app still works fully — chapters, notes, quiz, clip suggestions and all exports work. FFmpeg is only needed to cut and download actual MP4 clips.

---

## How to Run Locally

### Step 1 — Clone / extract the project

```powershell
cd LectureLens_AI_Grok
```

### Step 2 — Set up the backend

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # macOS / Linux

# Install dependencies
pip install -r backend\requirements.txt
```

### Step 3 — Add your Groq API key

Open `backend/.env` and replace the placeholder:

```env
GROQ_API_KEY=gsk_your_actual_key_here
GROQ_MODEL=llama-3.3-70b-versatile
WHISPER_MODEL=base
MAX_CLIPS=3
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Get a free key at [console.groq.com](https://console.groq.com) → API Keys → Create key.

### Step 4 — Start the backend

```powershell
uvicorn backend.main:app --reload
```

Backend runs at `http://localhost:8000`.  
Check it: open `http://localhost:8000/health` — you should see `{"status":"ok","groq_key_configured":true,...}`.

### Step 5 — Set up and start the frontend

Open a **second terminal**:

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

### Step 6 — Use the app

1. Open `http://localhost:5173`
2. Pick a tab: YouTube URL / Upload Video / Transcript file
3. Click **Generate Learning Pack**
4. Wait — a 60-minute lecture takes 2–8 minutes depending on transcription method and Groq rate limits
5. Browse Chapters / Notes / Quiz / Clips tabs
6. Download Markdown, JSON, or PDF

---

## Environment Variables

### `backend/.env`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ Yes | — | Your Groq API key from console.groq.com |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `WHISPER_MODEL` | No | `base` | faster-whisper model size: `tiny`, `base`, `small`, `medium` |
| `MAX_CLIPS` | No | `3` | Number of clip suggestions (3–5) |
| `CORS_ORIGINS` | No | localhost | Comma-separated allowed frontend origins |

### `frontend/.env` (create from `.env.example`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_URL` | No | `/api` (proxied) | Backend URL for production deploy e.g. `https://lecturelens-api.onrender.com` |

---

## API Endpoints

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `GET` | `/health` | — | `{status, groq_key_configured, model}` |
| `POST` | `/generate/youtube` | `FormData: url` | Full result JSON |
| `POST` | `/generate/upload` | `FormData: file` (mp4/mov/mkv/webm) | Full result JSON |
| `POST` | `/generate/transcript` | `FormData: file` (srt/vtt/txt/json) | Full result JSON |
| `POST` | `/export/markdown` | Result JSON body | `.md` file download |
| `POST` | `/export/pdf` | Result JSON body | `.pdf` file download |
| `POST` | `/export/json` | Result JSON body | `.json` file download |

### Result JSON shape

```json
{
  "metadata": {
    "source": "https://youtube.com/...",
    "duration_text": "01:12:34",
    "word_count": 12400,
    "transcription_mode": "YouTube captions",
    "generation_mode": "Groq llama-3.3-70b-versatile",
    "processing_seconds": 47.2,
    "warnings": []
  },
  "chapters": [
    { "start": "00:00", "end": "05:00", "title": "...", "summary": "...", "key_points": ["..."] }
  ],
  "notes_markdown": "## Introduction\n- ...",
  "quiz": [
    {
      "question": "...", "options": ["A","B","C","D"],
      "answer": "A", "explanation": "...", "evidence": "verbatim transcript quote"
    }
  ],
  "clips": [
    { "start": 120.0, "end": 195.0, "start_text": "02:00", "end_text": "03:15", "title": "...", "reason": "..." }
  ]
}
```

---

## Cost

### Groq API — Free tier

Groq offers a **free tier** with rate limits. As of writing:

| Model | Free RPM | Free TPM | Free RPD |
|-------|----------|----------|----------|
| `llama-3.3-70b-versatile` | 30 | 131,072 | 1,000 |

A typical 60-minute lecture generates roughly:
- ~12 chunk calls (5-min chunks × ~12 chunks) at ~1,800 tokens output each
- 1 final synthesis call at ~6,500 tokens output
- **Total: ~28,000–50,000 input tokens + ~28,000 output tokens**

This fits within the free daily limit for a single lecture. For heavy usage or paid tier, check current pricing at [console.groq.com/settings/billing](https://console.groq.com/settings/billing).

> If you hit a `429 rate limit` error mid-processing, wait 60 seconds and retry. The app does not auto-retry yet.

### Whisper — Free (local)

faster-whisper runs entirely on your CPU. No API cost. The `base` model (~150 MB) is downloaded once on first use to `~/.cache/huggingface/`. Transcription speed is roughly 10–30× real-time on a modern CPU (a 60-min video takes 2–6 minutes).

### YouTube captions — Free

`youtube-transcript-api` fetches captions directly from YouTube at no cost. No download or transcription needed when captions are available.

### Hosting

- Local: free
- Render.com free tier: backend may spin down after inactivity (cold start ~30s); frontend static hosting is always-on free

---

## How It Was Tested

### Automated unit tests (11 tests)

```powershell
python -m pytest tests/test_pipeline.py -v
```

Covers:
- `fmt_time` — minutes and hours formatting
- `_srt_time` — SRT timestamp formatting
- `parse_transcript` — SRT, VTT, TXT, JSON inputs
- `chunk_segments` — correct split, no-split, empty input

All 11 pass on Python 3.13.

### Manual end-to-end tests to run before submission

Run these and record real values — do not fabricate results:

| Test | What to check |
|------|--------------|
| 60+ min YouTube URL with captions | Full pack generated, all chapters cover the lecture duration |
| 60+ min YouTube URL without captions | Falls back to yt-dlp + Whisper, warning shown in UI |
| Uploaded MP4 video | Whisper transcribes, pack generated |
| SRT transcript upload | Parsed correctly, timestamps match source |
| Quiz evidence | Manually verify each answer's evidence quote exists verbatim in the transcript |
| Clip timestamps | Confirm start/end times fall within lecture duration |
| All 3 exports | Markdown, JSON, PDF all download and open correctly |
| `/health` endpoint | Returns `groq_key_configured: true` |
| Rate limit hit | `429` error shown clearly in UI, no silent failure |

---

## Known Limitations & Possible Breaks

### AI / Quality

- **Transcript truncation** — The final synthesis prompt sends up to 28,000 characters of transcript. Very long lectures (2+ hours) will have the tail truncated. Quiz evidence for later chapters may be weaker.
- **Quiz grounding** — Evidence quotes are AI-generated near-verbatim excerpts, not verified substring matches. Human review is required before publishing.
- **Hallucination risk** — The model is instructed not to invent facts, but LLMs can still hallucinate. Always verify against the source.

### YouTube

- **Caption availability** — Auto-captions are not available on all videos. Age-restricted, private, or region-blocked videos will fail entirely.
- **yt-dlp breakage** — YouTube frequently changes its internal API. yt-dlp may stop working until updated. Run `pip install -U yt-dlp` if downloads fail.
- **Rate limiting** — Rapid repeated requests to the same video may be throttled by YouTube.

### Transcription

- **CPU speed** — Whisper `base` on CPU is slow. A 60-min video can take 5–10 minutes. Use `WHISPER_MODEL=small` for better accuracy at the cost of more time/RAM.
- **No GPU support** — The app uses `device="cpu"`. GPU support requires CUDA and a different `compute_type`.
- **Non-English audio** — Whisper handles many languages but accuracy varies. Hindi/Hinglish lectures may have lower accuracy with the `base` model.

### FFmpeg (clip cutting)

- **System install required** — FFmpeg must be on PATH. The app detects its absence and disables clip cutting gracefully.
- **Subtitle path on Windows** — The Windows FFmpeg subtitle filter path escaping is handled (`C\:/path/...`) but may fail on unusual temp directory paths containing special characters.
- **No video available** — If YouTube captions were used and the video download failed (shown as a warning), the clip-cut button will not appear.

### Groq Rate Limits

- Free tier: 30 requests/minute, 1,000 requests/day. A long lecture with many chunks can hit the per-minute limit mid-processing. The error is shown clearly; retry after 60 seconds.

### Deployment

- **Whisper on Render free tier** — Render free instances have 512 MB RAM. The `base` Whisper model needs ~500 MB. Video upload + transcription may OOM on the free tier. Use transcript upload mode for deployed instances, or upgrade to a paid Render plan.
- **File upload size** — FastAPI has no upload size limit set. Large video files (>500 MB) may time out on hosted platforms. Set `MAX_UPLOAD_SIZE` in your hosting config if needed.
- **Cold starts** — Render free tier spins down after 15 minutes of inactivity. First request after spin-down takes ~30 seconds.

---

## Deploy to Render

The repo includes `render.yaml` for one-click deployment.

### Steps

1. Push the project to a GitHub repository
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo — Render reads `render.yaml` automatically
4. Set these environment variables in the Render dashboard:

**Backend service (`lecturelens-api`):**

| Key | Value |
|-----|-------|
| `GROQ_API_KEY` | your Groq key |
| `CORS_ORIGINS` | `https://lecturelens-ui.onrender.com` (your frontend URL) |

**Frontend service (`lecturelens-ui`):**

| Key | Value |
|-----|-------|
| `VITE_API_URL` | `https://lecturelens-api.onrender.com` (your backend URL) |

5. Deploy — both services build and start automatically

### Railway / Heroku

The `Procfile` is included for Railway or Heroku:

```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Set the same environment variables as above in your platform's dashboard.

---

## Running Tests

```powershell
# From project root (activate venv first)
python -m pytest tests/test_pipeline.py -v
```

Expected output:
```
11 passed in ~1s
```

---

## Quick Reference

```powershell
# Backend
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload          # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                                # http://localhost:5173

# Tests
python -m pytest tests\test_pipeline.py -v

# Production frontend build
cd frontend && npm run build               # outputs to frontend/dist/
```

---

## Security Notes

- The Groq API key is stored only in `backend/.env` which is listed in `.gitignore` — it is never sent to the browser or included in the frontend build
- `backend/.env` must never be committed to version control
- On deployment, set `GROQ_API_KEY` as a secret environment variable in your hosting dashboard, not in any file
- The `/health` endpoint only confirms whether a key is configured (boolean), it never returns the key value
