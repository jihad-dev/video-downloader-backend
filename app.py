
import os
import uuid
import threading
import time
from pathlib import Path
import tempfile

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

# ------------------------------
# Directories (safe path for Render free tier)
# ------------------------------
TEMP_DIR = Path(tempfile.gettempdir()) / "videos"
os.makedirs(TEMP_DIR, exist_ok=True)

# ------------------------------
# App Setup
# ------------------------------
app = FastAPI(title="Video Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # production এ lock করুন
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Helpers
# ------------------------------
def schedule_delete(path: Path, delay_seconds: int = 60):
    """Delete file after delay"""
    def _del():
        time.sleep(delay_seconds)
        try:
            if path.exists():
                path.unlink()
                print(f"Deleted: {path}")
        except Exception as e:
            print("Delete error:", e)
    threading.Thread(target=_del, daemon=True).start()

# ------------------------------
# Routes
# ------------------------------
@app.post("/download")
async def download_video(url: str = Form(...)):
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Unique file path
    random_name = str(uuid.uuid4())
    file_path = TEMP_DIR / f"{random_name}.mp4"

    ydl_opts = {
        "outtmpl": str(file_path),
        "format": "best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # যদি playlist হয়, প্রথম ভিডিও নাও
            if "_type" in info and info["_type"] == "playlist":
                info = info["entries"][0]

        # Auto delete 1 minute later
        schedule_delete(file_path, delay_seconds=60)

        return JSONResponse({
            "status": "success",
            "filename": file_path.name,
            "title": info.get("title"),
            "filesize": file_path.stat().st_size,
            "download_url": f"/file/{file_path.name}",
        })

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Video download failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.get("/file/{filename}")
async def get_file(filename: str):
    file_path = TEMP_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream"
    )

