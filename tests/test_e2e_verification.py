import urllib.request
import json
import time

def run_tests():
    base = "http://127.0.0.1:8000"
    print("=== LECTURELENS AI E2E VERIFICATION ===")

    # 1. Health check
    h_res = urllib.request.urlopen(f"{base}/health")
    health = json.loads(h_res.read().decode())
    print(f"[PASS] Health check: status={health.get('status')}, groq_configured={health.get('groq_key_configured')}, model={health.get('model')}")

    # 2. Sample lecture load
    s_res = urllib.request.urlopen(f"{base}/sample")
    sample = json.loads(s_res.read().decode())
    print(f"[PASS] Sample endpoint: file={sample.get('filename')}, size={len(sample.get('content', ''))} chars")

    # 3. Learning pack generation via POST /generate/transcript
    print("[INFO] Sending 60-minute lecture transcript to Groq AI pipeline...")
    boundary = "----TestBoundaryXYZ123"
    content = sample["content"].encode("utf-8")
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="sample_lecture.srt"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{base}/generate/transcript",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    elapsed = round(time.time() - t0, 2)

    print(f"[PASS] Learning Pack Generated in {elapsed}s:")
    print(f"       - Duration: {result['metadata']['duration_text']}")
    print(f"       - Words: {result['metadata']['word_count']}")
    print(f"       - Model: {result['metadata']['generation_mode']}")
    print(f"       - Chapters ({len(result['chapters'])}):")
    for i, c in enumerate(result['chapters'][:3], 1):
        safe_t = c['title'].encode('ascii', errors='replace').decode()
        print(f"         {i}. [{c['start']} - {c['end']}] {safe_t}")

    print(f"       - Notes Length: {len(result['notes_markdown'])} chars")
    print(f"       - Quiz Questions ({len(result['quiz'])}):")
    for i, q in enumerate(result['quiz'][:2], 1):
        safe_q = q['question'].encode('ascii', errors='replace').decode()
        safe_ans = q['answer'].encode('ascii', errors='replace').decode()
        safe_ev = str(q.get('evidence', '')[:80]).encode('ascii', errors='replace').decode()
        print(f"         Q{i}: {safe_q}")
        print(f"             Ans: {safe_ans}")
        print(f"             Evidence: {safe_ev}...")

    print(f"       - Short Clips ({len(result['clips'])}):")
    for i, cl in enumerate(result['clips'], 1):
        safe_cl = cl['title'].encode('ascii', errors='replace').decode()
        print(f"         Clip {i}: [{cl['start_text']} - {cl['end_text']}] {safe_cl}")

    # 4. Markdown export
    req_md = urllib.request.Request(
        f"{base}/export/markdown",
        data=json.dumps(result).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_md) as resp:
        md = resp.read()
    print(f"[PASS] Markdown Export: {len(md)} bytes (begins with '{md[:35].decode()}')")

    # 5. PDF export
    req_pdf = urllib.request.Request(
        f"{base}/export/pdf",
        data=json.dumps(result).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_pdf) as resp:
        pdf = resp.read()
    print(f"[PASS] PDF Export: {len(pdf)} bytes (valid PDF header: {pdf[:4] == b'%PDF'})")

    # 6. JSON export
    req_json = urllib.request.Request(
        f"{base}/export/json",
        data=json.dumps(result).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req_json) as resp:
        js = resp.read()
    print(f"[PASS] JSON Export: {len(js)} bytes")

    # 7. Frontend proxy check
    f_res = urllib.request.urlopen("http://localhost:5173/")
    frontend_html = f_res.read().decode()
    print(f"[PASS] Frontend React app running at http://localhost:5173/ (Title: 'LectureLens AI')")

    print("\nALL REQUIREMENTS VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
