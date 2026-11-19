import asyncio
import os
import re
from pathlib import Path
import yt_dlp
import gdown
from config import TEMP_DIR

class VideoDownloader:
    @staticmethod
    async def download_reference(url: str, output_name: str = "reference.mp4") -> Path:
        """
        Скачивает видео по ссылке:
        - Если ссылка с Google Диска: использует gdown
        - Для остальных сайтов (YouTube/Shorts/TikTok/Reels): использует yt-dlp
        """
        output_path = TEMP_DIR / output_name

        # Проверка на Google Drive
        if "drive.google.com" in url or "docs.google.com" in url:
            def _download_gdrive():
                output_file = str(output_path)
                try:
                    res = gdown.download(url=url, output=output_file, quiet=False, fuzzy=True)
                    if not res or not Path(res).exists() or Path(res).stat().st_size == 0:
                        raise ValueError(
                            "Google Диск отклонил скачивание (HTTP 403 Forbidden). "
                            "Пожалуйста, откройте доступ: нажмите правой кнопкой на файл в Google Диске "
                            "-> «Поделиться» -> смените «Ограниченный доступ» на «Все, у кого есть ссылка»!"
                        )
                    return Path(res)
                except Exception as e:
                    if "Permission denied" in str(e) or "403" in str(e) or "Forbidden" in str(e):
                        raise ValueError(
                            "Google Диск отклонил доступ (403 Forbidden). "
                            "Убедитесь, что в Google Диске включен общий доступ: "
                            "нажмите «Поделиться» -> смените доступ на «Все, у кого есть ссылка»!"
                        )
                    raise e

            return await asyncio.to_thread(_download_gdrive)

        # Обычные ссылки (YouTube, TikTok, Reels и др.) через yt-dlp
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path.with_suffix('')) + '.%(ext)s',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 500 * 1024 * 1024,  # до 500 МБ
        }

        def _download_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(_download_ytdlp)
        
        final_file = list(TEMP_DIR.glob(f"{output_path.stem}.*"))
        if final_file:
            return final_file[0]
        return output_path
