from pathlib import Path
from typing import Optional
from config import BASE_DIR

MUSIC_DIR = BASE_DIR / "assets" / "music"

PRESET_TRACKS = {
    "phonk": {
        "name": "🔥 Phonk / Драйв (для гейминга и эдитов)",
        "file": MUSIC_DIR / "phonk_gaming.wav"
    },
    "lofi": {
        "name": "☕ Lo-Fi / Chill (спокойный для блогов)",
        "file": MUSIC_DIR / "lofi_beat.wav"
    },
    "upbeat": {
        "name": "⚡ Upbeat / Энергичный (для Reels / Shorts)",
        "file": MUSIC_DIR / "energetic_upbeat.wav"
    }
}

class MusicSelector:
    @staticmethod
    def ai_select_track(prompt: Optional[str] = None, mode: str = "edit_tiktok") -> Path:
        """
        Нейро-подбор музыки под стиль видео и пожелания пользователя:
        - Если в тексте упоминаются игра, GTA, шутер, эдит, phonk -> Phonk / Gaming
        - Если ютуб, обзор, подкаст, спокойный -> Lo-Fi
        - Если шортс, рилс, тикток -> Upbeat
        """
        text = (prompt or "").lower()

        if any(w in text for w in ["гейм", "игра", "gta", "стандофф", "standoff", "cs", "эдит", "фонк", "phonk", "драйв"]):
            return PRESET_TRACKS["phonk"]["file"]
        
        if any(w in text for w in ["ютуб", "youtube", "подкаст", "разговор", "спокойн", "чит", "блог"]):
            return PRESET_TRACKS["lofi"]["file"]

        if mode == "edit_tiktok":
            return PRESET_TRACKS["phonk"]["file"]
        elif mode == "youtube_long":
            return PRESET_TRACKS["lofi"]["file"]
        else:
            return PRESET_TRACKS["upbeat"]["file"]
