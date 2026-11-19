import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
TEMP_DIR = BASE_DIR / os.getenv("TEMP_DIR", "temp")
TEMP_DIR.mkdir(parents=True, exist_ok=True)
