import os
import uuid
import shutil
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import threading
import time

# ------------------------------
# Directories
# ------------------------------
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
TEMP_DIR = BASE_DIR / "temp"

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ------------------------------
# App Setup
# ------------------------------
app = FastAPI(title="Video Downloader API")

# Allow local dev RN/Next.js app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Helpers
# ------------------------------
def schedule_delete(path: Path, delay_seconds: int = 3600):
    """
    Delete file after delay (background thread)
    """
    def _del():
        time.sleep(delay_seconds)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
    t = threading.Thread(target=_del, daemon=True)
    t.start()

# ------------------------------
# Routes
# ------------------------------
@app.post("/download")
async def download_video(url: str = Form(...)):
    """
    Download video using yt-dlp and return metadata & filename
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Unique temp folder for this download
    uid = uuid.uuid4().hex
    out_dir = TEMP_DIR / uid
    os.makedirs(out_dir, exist_ok=True)

    # Generate random UUID for filename
    random_name = str(uuid.uuid4())

    # yt-dlp options with safe random filename
    ydl_opts = {
        "outtmpl": str(out_dir / f"{random_name}.%(ext)s"),
        "format": "best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            # If playlist, pick first entry
            if "_type" in info and info["_type"] == "playlist":
                info = info["entries"][0]

            # Get the downloaded file path
            files = list(out_dir.glob("*"))
            if not files:
                raise RuntimeError("Downloaded file not found")
            src = files[0]

            # Move file to downloads folder
            dest = DOWNLOADS_DIR / src.name
            shutil.move(str(src), dest)
    except Exception as e:
        # Cleanup temp folder
        try:
            shutil.rmtree(out_dir)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Download failed: {e}")
    finally:
        # Cleanup temp folder if exists
        try:
            if out_dir.exists():
                shutil.rmtree(out_dir)
        except Exception:
            pass

    # Schedule auto-delete after 6 hours
    schedule_delete(dest, delay_seconds=6 * 3600)

    return JSONResponse(
        {
            "status": "success",
            "filename": dest.name,
            "title": info.get("title"),
            "filesize": dest.stat().st_size,
            "download_url": f"/file/{dest.name}",
        }
    )

@app.get("/file/{filename}")
async def get_file(filename: str):
    """
    Stream file to client
    """
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream"
    )
