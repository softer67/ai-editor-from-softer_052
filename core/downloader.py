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
        - Google Диск: использует gdown
        - Яндекс.Диск / YouTube / TikTok / Reels и прямые ссылки: использует yt-dlp
        """
        output_path = TEMP_DIR / output_name

        # Проверка на Google Drive
        if "drive.google.com" in url or "docs.google.com" in url:
            def _download_gdrive():
                output_file = str(output_path)
                
                # Извлекаем ID файла из ссылки
                file_id = None
                id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', url) or re.search(r'id=([a-zA-Z0-9_-]+)', url)
                if id_match:
                    file_id = id_match.group(1)

                try:
                    if file_id:
                        res = gdown.download(id=file_id, output=output_file, quiet=False)
                    else:
                        res = gdown.download(url=url, output=output_file, quiet=False)
                    
                    if not res or not Path(res).exists() or Path(res).stat().st_size == 0:
                        raise ValueError(
                            "Google Диск не отдает файл (404/403). Доступ к файлу закрыт.\n"
                            "В Google Диске нажмите «Поделиться» -> смените «Ограниченный доступ» на «Все, у кого есть ссылка» -> «Готово»."
                        )
                    return Path(res)
                except Exception as e:
                    err_str = str(e)
                    if "Cannot retrieve" in err_str or "Permission denied" in err_str or "403" in err_str or "404" in err_str:
                        raise ValueError(
                            "Google Диск отклонил доступ. Файл сейчас закрыт настройками приватности.\n"
                            "Откройте доступ: в Google Диске нажмите «Поделиться» -> переключите «Ограниченный доступ» на «Все, у кого есть ссылка» -> нажмите «Готово»."
                        )
                    raise e

            return await asyncio.to_thread(_download_gdrive)

        # Обычные ссылки (Яндекс.Диск, YouTube, TikTok, Reels и др.) через yt-dlp
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path.with_suffix('')) + '.%(ext)s',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 500 * 1024 * 1024,
        }

        def _download_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await asyncio.to_thread(_download_ytdlp)
        
        final_file = list(TEMP_DIR.glob(f"{output_path.stem}.*"))
        if final_file:
            return final_file[0]
        return output_path
