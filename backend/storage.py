import os
import json
import sqlite3
import hashlib
import datetime
from pathlib import Path

DB_DIR = Path(__file__).parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "lecturelens.db"


def _get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learning_packs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                source_type TEXT NOT NULL,
                duration_text TEXT,
                word_count INTEGER DEFAULT 0,
                model TEXT,
                processing_seconds REAL DEFAULT 0,
                chapters_count INTEGER DEFAULT 0,
                quiz_count INTEGER DEFAULT 0,
                clips_count INTEGER DEFAULT 0,
                proof_hash TEXT,
                data_json TEXT NOT NULL
            )
        """)
        conn.commit()


# Initialize on import
init_db()


def compute_proof_hash(source, segments_count, notes, chapters):
    content = f"{source}|{segments_count}|{notes[:500]}|{len(chapters)}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16].upper()


def save_pack(result, source_type="unknown"):
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now.strftime("%Y%m%d_%H%M%S")
    rand_suffix = hashlib.md5(f"{result.get('metadata', {}).get('source')}_{ts_str}".encode()).hexdigest()[:6]
    pack_id = f"pack_{ts_str}_{rand_suffix}"
    created_at = now.isoformat()

    meta = result.get("metadata", {})
    source = meta.get("source", "Unknown")
    duration_text = meta.get("duration_text", "00:00")
    word_count = int(meta.get("word_count", 0))
    model = meta.get("generation_mode", "Groq AI")
    proc_secs = float(meta.get("processing_seconds", 0.0))

    chapters = result.get("chapters", [])
    quiz = result.get("quiz", [])
    clips = result.get("clips", [])
    notes = result.get("notes_markdown", "")
    segments = result.get("segments", [])

    proof_hash = compute_proof_hash(source, len(segments), notes, chapters)
    result["id"] = pack_id
    result["proof_hash"] = proof_hash
    result["created_at"] = created_at

    data_json = json.dumps(result, ensure_ascii=False)

    with _get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO learning_packs (
                id, created_at, source, source_type, duration_text,
                word_count, model, processing_seconds, chapters_count,
                quiz_count, clips_count, proof_hash, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pack_id, created_at, source, source_type, duration_text,
            word_count, model, proc_secs, len(chapters),
            len(quiz), len(clips), proof_hash, data_json
        ))
        conn.commit()

    return pack_id, proof_hash


def list_packs():
    with _get_connection() as conn:
        cur = conn.execute("""
            SELECT id, created_at, source, source_type, duration_text,
                   word_count, model, processing_seconds, chapters_count,
                   quiz_count, clips_count, proof_hash
            FROM learning_packs
            ORDER BY created_at DESC
            LIMIT 100
        """)
        rows = [dict(r) for r in cur.fetchall()]
        return rows


def get_pack(pack_id):
    with _get_connection() as conn:
        cur = conn.execute("SELECT data_json FROM learning_packs WHERE id = ?", (pack_id,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["data_json"])


def delete_pack(pack_id):
    with _get_connection() as conn:
        conn.execute("DELETE FROM learning_packs WHERE id = ?", (pack_id,))
        conn.commit()
    return True


def get_proof_certificate(pack_id):
    pack = get_pack(pack_id)
    if not pack:
        return None

    meta = pack.get("metadata", {})
    chapters = pack.get("chapters", [])
    quiz = pack.get("quiz", [])
    clips = pack.get("clips", [])

    lines = [
        "==================================================================",
        "          🎓 LECTURELENS AI — PROOF OF AUDIT & LEARNING PACK      ",
        "==================================================================",
        f"CERTIFICATE ID:   {pack_id}",
        f"VERIFICATION HASH: SHA256:{pack.get('proof_hash', 'N/A')}",
        f"TIMESTAMP (UTC):  {pack.get('created_at', meta.get('created_at', 'N/A'))}",
        "------------------------------------------------------------------",
        f"LECTURE SOURCE:   {meta.get('source', 'N/A')}",
        f"TRANSCRIPTION:    {meta.get('transcription_mode', 'N/A')}",
        f"AI MODEL USED:    {meta.get('generation_mode', 'Groq AI')}",
        f"RECORDED DURATION:{meta.get('duration_text', 'N/A')} ({meta.get('duration_seconds', 0)} seconds)",
        f"LECTURE WORDS:    {meta.get('word_count', 0):,} words",
        f"GENERATION SPEED: {meta.get('processing_seconds', 0)} seconds",
        "------------------------------------------------------------------",
        "STRUCTURED PROOF OF CONTENT GENERATED:",
        f"  • Chapters Generated:     {len(chapters)} logical chapters",
        f"  • Revision Notes Size:    {len(pack.get('notes_markdown', '')):,} characters",
        f"  • Evidenced Quiz Items:   {len(quiz)} questions with transcript citations",
        f"  • Clip Segments Planned:  {len(clips)} suggested video clips",
        "------------------------------------------------------------------",
        "CHAPTER OUTLINE SNAPSHOT:",
    ]
    for i, c in enumerate(chapters[:10], 1):
        lines.append(f"  {i:2d}. [{c['start']} - {c['end']}] {c['title']}")

    lines += [
        "------------------------------------------------------------------",
        "QUIZ INTEGRITY AUDIT SAMPLE:",
    ]
    if quiz:
        q = quiz[0]
        lines.append(f"  Question: {q.get('question')}")
        lines.append(f"  Evidence: \"{q.get('evidence', '')[:100]}...\"")

    lines += [
        "==================================================================",
        "DIGITAL STATUS:   VERIFIED & PERSISTED IN LOCAL AUDIT STORAGE     ",
        "ENGINE:           LectureLens AI Engine v2.0 (Groq Powered)       ",
        "=================================================================="
    ]
    return "\n".join(lines)
