import os, sys, re, json, tempfile, subprocess, shutil, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from openai import OpenAI

# Auto-load environment variables if not already loaded
if not os.getenv("GROQ_API_KEY"):
    load_dotenv(Path(__file__).parent / "backend" / ".env")
    load_dotenv(Path(__file__).parent / ".env")


def _ensure_ffmpeg_in_path():
    """Ensure ffmpeg from WinGet or system paths is in os.environ['PATH']."""
    if shutil.which("ffmpeg"):
        return True
    local_app = os.getenv("LOCALAPPDATA", "")
    if local_app:
        candidates = [
            Path(local_app) / "Microsoft" / "WinGet" / "Links",
        ]
        pkg_dir = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
        if pkg_dir.exists():
            candidates.extend(p.parent for p in pkg_dir.glob("**/ffmpeg.exe"))
        for c in candidates:
            if (c / "ffmpeg.exe").exists() or (c / "ffmpeg").exists():
                os.environ["PATH"] = str(c) + os.pathsep + os.environ.get("PATH", "")
                return True
_ensure_ffmpeg_in_path()


def _patch_pyav_metadata_errors():
    """Patch PyAV 14+ / 19+ where metadata_errors was removed from av.open().
    faster_whisper calls av.open(..., metadata_errors='ignore') which fails without this patch."""
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

_patch_pyav_metadata_errors()


def _groq_client():
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY not set in environment.")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")


def _model():
    return os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def fmt_time(seconds):
    n = max(0, int(float(seconds or 0)))
    h, r = divmod(n, 3600)
    m, s = divmod(r, 60)
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"


def _srt_time(sec):
    ms = int(max(0, sec) * 1000)
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_ts(s):
    try:
        parts = [float(x) for x in s.replace(",", ".").split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    except Exception:
        pass
    return None


def parse_transcript(raw, filename):
    if filename.lower().endswith(".json"):
        obj = json.loads(raw)
        if isinstance(obj, dict):
            obj = obj.get("segments", obj.get("transcript", []))
        if isinstance(obj, str):
            return [{"start": 0.0, "end": 0.0, "text": obj}]
        return [
            {"start": float(x.get("start", 0)),
             "end": float(x.get("end", x.get("start", 0))),
             "text": str(x.get("text", "")).strip()}
            for x in obj if str(x.get("text", "")).strip()
        ]
    segments = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        line = next((x for x in lines if "-->" in x), None)
        if not line:
            continue
        left, right = [x.strip().split()[0] for x in line.split("-->")[:2]]
        start, end = parse_ts(left), parse_ts(right)
        txt = " ".join(x for x in lines if x != line and not x.isdigit() and x.upper() != "WEBVTT")
        txt = re.sub(r"<[^>]+>", "", txt).strip()
        if txt and start is not None:
            segments.append({"start": start, "end": end if end is not None else start, "text": txt})
    if segments:
        return segments
    clean = raw.strip()
    if clean:
        return [{"start": 0.0, "end": 0.0, "text": clean}]
    raise ValueError("Transcript file is empty or unsupported.")


def get_youtube_captions(url):
    from urllib.parse import urlparse, parse_qs
    from youtube_transcript_api import YouTubeTranscriptApi
    u = urlparse(url)
    vid = parse_qs(u.query).get("v", [None])[0]
    if not vid and u.hostname and "youtu.be" in u.hostname:
        vid = u.path.strip("/").split("/")[0]
    if not vid and "embed" in u.path:
        vid = u.path.strip("/").split("/")[-1]
    if not vid and "shorts" in u.path:
        vid = u.path.strip("/").split("/")[-1]
    if not vid:
        raise ValueError("Could not extract YouTube video ID from URL.")

    api = YouTubeTranscriptApi()
    transcript_list = api.list(vid)
    transcript = None
    try:
        # Prefer English if available
        transcript = transcript_list.find_transcript(["en", "en-US", "en-GB"])
    except Exception:
        try:
            transcript = transcript_list.find_manually_created_transcript(
                [t.language_code for t in transcript_list]
            )
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(
                    [t.language_code for t in transcript_list]
                )
            except Exception:
                try:
                    transcript = next(iter(transcript_list))
                except Exception:
                    raise ValueError(f"No transcripts found for YouTube video {vid}")

    data = transcript.fetch()
    segments = []
    for s in data:
        st = float(getattr(s, "start", s["start"] if isinstance(s, dict) else 0.0))
        dur = float(getattr(s, "duration", s["duration"] if isinstance(s, dict) else 0.0))
        txt = str(getattr(s, "text", s["text"] if isinstance(s, dict) else "")).strip()
        if txt:
            segments.append({"start": st, "end": st + dur, "text": txt})
    if not segments:
        raise ValueError("Transcript is empty.")
    return segments


def download_youtube(url, outdir):
    _ensure_ffmpeg_in_path()
    import yt_dlp
    opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "outtmpl": str(Path(outdir) / "lecture.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    candidates = list(Path(outdir).glob("lecture.*"))
    if not candidates:
        raise RuntimeError("yt-dlp completed but no video file was found.")
    return str(candidates[0])


def extract_audio(video_path):
    """Extract audio from video to a lightweight 16kHz MP3 using FFmpeg."""
    _ensure_ffmpeg_in_path()
    if not shutil.which("ffmpeg"):
        return video_path
    out_audio = tempfile.mktemp(suffix=".mp3")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
        str(out_audio)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        if os.path.exists(out_audio) and os.path.getsize(out_audio) > 0:
            return out_audio
    except Exception:
        pass
    return video_path


def transcribe_video(path):
    _patch_pyav_metadata_errors()
    audio_path = extract_audio(path)

    # 1. Try Groq's high-speed Whisper model first (whisper-large-v3-turbo)
    try:
        client = _groq_client()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                response_format="verbose_json",
            )
        raw_segs = getattr(resp, "segments", None)
        if raw_segs:
            out = []
            for s in raw_segs:
                txt = s.get("text", "") if isinstance(s, dict) else getattr(s, "text", "")
                st = s.get("start", 0) if isinstance(s, dict) else getattr(s, "start", 0)
                en = s.get("end", 0) if isinstance(s, dict) else getattr(s, "end", 0)
                if txt and str(txt).strip():
                    out.append({"start": float(st), "end": float(en), "text": str(txt).strip()})
            if out:
                return out
        full_text = getattr(resp, "text", "")
        if full_text and full_text.strip():
            return [{"start": 0.0, "end": 0.0, "text": full_text.strip()}]
    except Exception:
        pass

    # 2. Fallback to local faster-whisper
    from faster_whisper import WhisperModel
    m = WhisperModel(os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
    segments, _ = m.transcribe(audio_path, vad_filter=True, word_timestamps=False)
    out = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
           for s in segments if s.text.strip()]
    if not out:
        raise RuntimeError("Speech-to-text completed, but no spoken words were detected in this video file.")
    return out


def chunk_segments(segments, max_seconds=300):
    if not segments:
        return []
    chunks, group, chunk_start = [], [], float(segments[0]["start"])
    for s in segments:
        if group and float(s["end"]) - chunk_start >= max_seconds:
            chunks.append(group)
            group, chunk_start = [], float(s["start"])
        group.append(s)
    if group:
        chunks.append(group)
    return chunks


def call_ai(system, prompt, max_tokens=3500):
    client = _groq_client()
    preferred = _model()
    # Fallback cascade across available models
    models_to_try = [preferred, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    seen = set()
    order = [m for m in models_to_try if not (m in seen or seen.add(m))]

    last_err = None
    for m in order:
        for attempt in range(3):
            try:
                r = client.chat.completions.create(
                    model=m,
                    temperature=0.2,
                    max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                )
                return r.choices[0].message.content
            except Exception as e:
                last_err = e
                err_msg = str(e).lower()
                if "rate_limit" in err_msg or "429" in err_msg:
                    time.sleep(2 * (attempt + 1))
                    continue
                if "model_not_found" in err_msg or "does not exist" in err_msg or "404" in err_msg:
                    break
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise
    raise last_err


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < s:
        raise ValueError("AI did not return a JSON object.")
    snippet = text[s:e + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        # Clean potential trailing commas before closing braces
        clean = re.sub(r",\s*([\]}])", r"\1", snippet)
        return json.loads(clean)


def _process_chunk_summary(i, total, chunk):
    transcript = "\n".join(
        f"[{fmt_time(s['start'])}-{fmt_time(s['end'])}] {s['text']}" for s in chunk
    )
    obj = extract_json(call_ai(
        "You are an educational editor. Return valid JSON only.",
        f"Summarize transcript chunk {i}/{total}. "
        f"Return JSON: title, summary, key_points (array of strings). Facts only.\nTRANSCRIPT:\n{transcript[:14000]}",
        1800,
    ))
    return {
        "index": i,
        "start": chunk[0]["start"],
        "end": chunk[-1]["end"],
        "title": str(obj.get("title", f"Section {i}")),
        "summary": str(obj.get("summary", "")),
        "key_points": obj.get("key_points", []),
    }


def build_learning_pack(segments, max_clips=3):
    chunks = chunk_segments(segments, 300)
    
    # Process chunks concurrently with max_workers=3 for fast speed while staying inside Groq limits
    with ThreadPoolExecutor(max_workers=min(3, len(chunks) or 1)) as pool:
        futures = [pool.submit(_process_chunk_summary, i, len(chunks), ch) for i, ch in enumerate(chunks, 1)]
        chunk_summaries = [f.result() for f in futures]
    
    chunk_summaries.sort(key=lambda x: x["start"])

    compact = json.dumps(chunk_summaries, ensure_ascii=False)
    evidence = "\n".join(
        f"[{fmt_time(s['start'])}-{fmt_time(s['end'])}] {s['text']}" for s in segments
    )
    obj = extract_json(call_ai(
        "You generate source-grounded educational materials. Output JSON only; never invent facts.",
        f"""Return one JSON object with:
notes_markdown: comprehensive structured markdown notes with clear #, ## headings, summaries, key concepts, formulas/definitions, and bullet points;
quiz: array of 8 objects {{"question":string,"options":[four strings],"answer":one option string,"explanation":string,"evidence":verbatim transcript excerpt}};
clips: array of up to {max_clips} objects {{"start":number,"end":number,"title":string,"reason":string}} in seconds (30-90s each).
SECTION SUMMARIES:\n{compact[:18000]}\nTRANSCRIPT:\n{evidence[:28000]}""",
        6500,
    ))

    duration = max((float(s.get("end", 0)) for s in segments), default=0)
    chapters = [
        {"start": fmt_time(c["start"]), "end": fmt_time(c["end"]),
         "title": c["title"], "summary": c["summary"], "key_points": c["key_points"]}
        for c in chunk_summaries
    ]

    clips = []
    for c in obj.get("clips", [])[:max_clips]:
        try:
            a = max(0, min(float(c["start"]), duration))
            b = max(a, min(float(c["end"]), duration))
            if b > a:
                clips.append({"start": a, "end": b, "start_text": fmt_time(a),
                               "end_text": fmt_time(b), "title": str(c.get("title", "Clip")),
                               "reason": str(c.get("reason", ""))})
        except Exception:
            continue
    if not clips:
        for c in chunk_summaries[:max_clips]:
            if c["end"] - c["start"] >= 30:
                a = max(c["start"], c["end"] - 75)
                b = min(c["end"], a + 75)
                clips.append({"start": a, "end": b, "start_text": fmt_time(a),
                               "end_text": fmt_time(b), "title": c["title"],
                               "reason": "Fallback from chapter."})

    valid = []
    for q in obj.get("quiz", []):
        if (isinstance(q, dict) and q.get("question")
                and isinstance(q.get("options"), list)
                and len(q["options"]) >= 2 and q.get("answer")):
            valid.append({
                "question": q["question"], "options": q["options"][:4],
                "answer": q["answer"], "explanation": q.get("explanation", ""),
                "evidence": q.get("evidence", ""),
            })
    if not valid:
        raise RuntimeError("AI returned no valid quiz questions. Retry.")
    return chapters, str(obj.get("notes_markdown", "")), valid, clips


def build_result(segments, source, video_path, max_clips, started, mode):
    if not segments:
        raise ValueError("No transcript segments were produced.")
    chapters, notes, quiz, clips = build_learning_pack(segments, max_clips)
    duration = max((float(s.get("end", 0)) for s in segments), default=0)
    return {
        "metadata": {
            "source": source, "duration_seconds": duration,
            "duration_text": fmt_time(duration),
            "word_count": sum(len(s["text"].split()) for s in segments),
            "transcription_mode": mode,
            "generation_mode": f"Groq {_model()}",
            "processing_seconds": round(time.time() - started, 2),
            "warnings": [],
        },
        "chapters": chapters, "notes_markdown": notes,
        "quiz": quiz, "clips": clips,
        "segments": segments, "video_path": video_path,
    }


def process_youtube(url, max_clips=3):
    started = time.time()
    temp = tempfile.mkdtemp(prefix="lecturelens_")
    video, mode = None, "YouTube captions"
    try:
        segments = get_youtube_captions(url)
    except Exception as ce:
        # If captions are unavailable, fall back to downloading and local whisper
        try:
            video = download_youtube(url, temp)
            segments = transcribe_video(video)
            mode = "Local faster-whisper"
        except Exception as e:
            raise RuntimeError(f"Captions failed: {ce}. Download/transcription failed: {e}")

    result = build_result(segments, url, video, max_clips, started, mode)
    return result


def process_uploaded_video(path, name, max_clips=3):
    started = time.time()
    return build_result(transcribe_video(path), name, path, max_clips, started, "Local faster-whisper")


def process_transcript(raw, name, max_clips=3):
    started = time.time()
    return build_result(parse_transcript(raw, name), name, None, max_clips, started, "Uploaded transcript")


def render_one_clip(video_path, start, end, segments=None, title="clip"):
    """Render a short MP4 clip from video_path with subtitles or clean trim."""
    _ensure_ffmpeg_in_path()
    if not video_path or not Path(video_path).exists():
        raise RuntimeError("Source video unavailable on disk.")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed.")

    outdir = Path(tempfile.mkdtemp(prefix="lecturelens_clip_"))
    safe_title = re.sub(r"[^a-zA-Z0-9_\-]", "_", title)[:30] or "clip"
    dest = outdir / f"{safe_title}.mp4"

    a, b = max(0.0, float(start)), max(0.0, float(end))
    dur = max(1.0, b - a)

    rendered = False
    if segments:
        rows = [s for s in segments if float(s.get("end", 0)) > a and float(s.get("start", 0)) < b]
        if rows:
            srt = outdir / "subtitles.srt"
            with open(srt, "w", encoding="utf-8") as f:
                for j, s in enumerate(rows, 1):
                    st = max(0.0, float(s["start"]) - a)
                    en = max(st + 0.2, min(dur, float(s["end"]) - a))
                    f.write(f"{j}\n{_srt_time(st)} --> {_srt_time(en)}\n{s['text'].replace(chr(10), ' ')}\n\n")
            raw_path = str(srt.resolve())
            if os.name == "nt":
                subpath = raw_path.replace("\\", "/")
                if len(subpath) > 1 and subpath[1] == ":":
                    subpath = subpath[0] + "\\:" + subpath[2:]
            else:
                subpath = raw_path.replace("\\", "/").replace(":", "\\:")
            cmd = [
                "ffmpeg", "-y", "-ss", str(a), "-i", str(video_path),
                "-t", str(dur), "-vf", f"subtitles='{subpath}'",
                "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(dest),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
                if dest.exists() and dest.stat().st_size > 0:
                    rendered = True
            except Exception:
                rendered = False

    if not rendered:
        cmd_trim = [
            "ffmpeg", "-y", "-ss", str(a), "-i", str(video_path),
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(dest),
        ]
        subprocess.run(cmd_trim, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)

    if not dest.exists():
        raise RuntimeError("FFmpeg clip generation failed.")
    return str(dest)


def cut_youtube_clip(url, start, end, segments=None, title="clip"):
    """Download the specific clip range from YouTube and process with FFmpeg."""
    _ensure_ffmpeg_in_path()
    outdir = Path(tempfile.mkdtemp(prefix="lecturelens_yt_clip_"))
    temp_video = outdir / "section.mp4"
    import yt_dlp
    a, b = float(start), float(end)
    opts = {
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "outtmpl": str(temp_video),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(a, b)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    candidates = list(outdir.glob("section.*"))
    if not candidates:
        raise RuntimeError("Failed to extract YouTube clip segment.")
    return render_one_clip(str(candidates[0]), 0, b - a, segments, title)


def export_markdown(r):
    out = [
        "# LectureLens AI — Learning Pack",
        f"**Source:** {r['metadata']['source']}",
        f"**Duration:** {r['metadata']['duration_text']}",
        f"**Word Count:** {r['metadata'].get('word_count', 'N/A')}",
        "## Chapters",
    ]
    for c in r["chapters"]:
        out.append(f"- **{c['start']}–{c['end']} — {c['title']}**: {c['summary']}")
        if c.get("key_points"):
            for p in c["key_points"]:
                out.append(f"  * {p}")
    out += ["", "## Revision Notes", r["notes_markdown"], "", "## Quiz"]
    for i, q in enumerate(r["quiz"], 1):
        out += (
            [f"### {i}. {q['question']}"]
            + ["- " + str(x) for x in q["options"]]
            + [f"**Answer:** {q['answer']}",
               f"**Explanation:** {q.get('explanation', '')}",
               f"**Evidence:** {q.get('evidence', '')}", ""]
        )
    out += ["## Short Clips"]
    for c in r["clips"]:
        out.append(f"- **{c['start_text']}–{c['end_text']}: {c['title']}** — {c['reason']}")
    return "\n\n".join(out)


def export_pdf(r):
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io, html
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=letter, title="LectureLens AI")
    styles = getSampleStyleSheet()

    story = [
        Paragraph("LectureLens AI — Learning Pack", styles["Title"]),
        Paragraph(f"Source: {html.escape(str(r['metadata']['source']))} | Duration: {r['metadata']['duration_text']}", styles["Normal"]),
        Spacer(1, 14),
        Paragraph("Chapters", styles["Heading1"]),
    ]
    for c in r["chapters"]:
        story += [
            Paragraph(
                f"<b>{html.escape(c['start'])}–{html.escape(c['end'])}: "
                f"{html.escape(c['title'])}</b><br/>{html.escape(c['summary'])}",
                styles["BodyText"],
            ),
            Spacer(1, 6),
        ]
    story.append(Spacer(1, 10))
    story.append(Paragraph("Revision Notes", styles["Heading1"]))
    for line in r["notes_markdown"].splitlines():
        if line.strip():
            story.append(Paragraph(html.escape(line), styles["BodyText"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Quiz", styles["Heading1"]))
    for i, q in enumerate(r["quiz"], 1):
        story.append(Paragraph(f"<b>Q{i}. {html.escape(q['question'])}</b>", styles["BodyText"]))
        for opt in q["options"]:
            story.append(Paragraph("• " + html.escape(str(opt)), styles["BodyText"]))
        story += [
            Paragraph("<b>Answer:</b> " + html.escape(str(q["answer"])), styles["BodyText"]),
            Paragraph("<b>Evidence:</b> " + html.escape(str(q.get("evidence", ""))), styles["BodyText"]),
            Spacer(1, 6),
        ]
    story.append(Spacer(1, 10))
    story.append(Paragraph("Short Clips", styles["Heading1"]))
    for c in r.get("clips", []):
        story += [
            Paragraph(
                f"<b>{html.escape(c['start_text'])}–{html.escape(c['end_text'])}: "
                f"{html.escape(c['title'])}</b><br/>{html.escape(c['reason'])}",
                styles["BodyText"],
            ),
            Spacer(1, 4),
        ]
    doc.build(story)
    return buff.getvalue()
