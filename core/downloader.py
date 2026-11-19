import asyncio
import os
from pathlib import Path
import yt_dlp
from config import TEMP_DIR

class VideoDownloader:
    @staticmethod
    async def download_reference(url: str, output_name: str = "reference.mp4") -> Path:
        """Скачивает видео-референс по ссылке (YouTube Shorts/Reels/TikTok и др.)"""
        output_path = TEMP_DIR / output_name
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path.with_suffix('')) + '.%(ext)s',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 100 * 1024 * 1024,  # лимит 100 МБ
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(_download)
        
        # Находим итоговый скачанный файл
        final_file = list(TEMP_DIR.glob(f"{output_path.stem}.*"))
        if final_file:
            return final_file[0]
        return output_path
