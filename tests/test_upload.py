import urllib.request
import urllib.error
import json

def test_video_upload():
    boundary = "----UploadTestBoundary999"
    with open("test_video.mp4", "rb") as f:
        video_bytes = f.read()

    header = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test_video.mp4\"\r\nContent-Type: video/mp4\r\n\r\n").encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + video_bytes + footer

    req = urllib.request.Request(
        "http://localhost:5173/api/generate/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    print("Sending video upload via Vite proxy to http://localhost:5173/api/generate/upload...")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            res = json.loads(resp.read().decode())
        print("SUCCESS! Video processed without errors!")
        print("Metadata:", res.get("metadata"))
    except urllib.error.HTTPError as e:
        print("HTTPError detail:", e.code, e.read().decode())

if __name__ == "__main__":
    test_video_upload()
