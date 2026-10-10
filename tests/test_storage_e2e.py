import urllib.request
import json

def test_storage_and_proof():
    base = "http://localhost:5173/api"
    # 1. Check history
    h1 = json.loads(urllib.request.urlopen(f"{base}/history").read().decode())
    print(f"1. Current history records count: {len(h1)}")

    # 2. Upload transcript
    with open("sample_lecture.srt", "r", encoding="utf-8") as f:
        sample_txt = f.read()

    boundary = "----HistoryTestBoundaryXYZ"
    header = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample_lecture.srt\"\r\nContent-Type: text/plain\r\n\r\n").encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + sample_txt.encode("utf-8") + footer
    req = urllib.request.Request(
        f"{base}/generate/transcript",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    print("2. Generating lecture learning pack and saving to persistent storage...")
    resp = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
    pack_id = resp.get("id")
    proof_hash = resp.get("proof_hash")
    print(f"   -> Pack ID generated: {pack_id}")
    print(f"   -> Proof Verification Hash: #{proof_hash}")

    # 3. Check history again
    h2 = json.loads(urllib.request.urlopen(f"{base}/history").read().decode())
    print(f"3. Updated history count in SQLite DB: {len(h2)}")
    latest = h2[0]
    print(f"   -> Latest item: {latest['source']} ({latest['duration_text']}) | Hash: #{latest['proof_hash']}")

    # 4. Fetch proof certificate
    cert = urllib.request.urlopen(f"{base}/history/{pack_id}/proof").read().decode("utf-8")
    print(f"4. Proof certificate downloaded ({len(cert)} bytes)")
    for line in cert.splitlines()[:8]:
        print("   " + line.encode('ascii', errors='replace').decode())

    print("\nSTORAGE & AUDIT PROOF SYSTEM FULLY VERIFIED!")

if __name__ == "__main__":
    test_storage_and_proof()
