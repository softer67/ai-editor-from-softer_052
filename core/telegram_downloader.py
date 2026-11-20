import asyncio
import time
from pathlib import Path
from typing import Optional, Callable
from telethon import TelegramClient
from config import BOT_TOKEN, TEMP_DIR

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

class TelegramDownloader:
    _instance: Optional["TelegramDownloader"] = None

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "TelegramDownloader":
        if cls._instance is None:
            cls._instance = TelegramDownloader()
        return cls._instance

    async def get_client(self) -> TelegramClient:
        async with self._lock:
            if self.client is None or not self.client.is_connected():
                session_file = str(TEMP_DIR / "bot_mtproto")
                self.client = TelegramClient(session_file, API_ID, API_HASH)
                await self.client.start(bot_token=BOT_TOKEN)
            return self.client

    async def download_video(
        self,
        chat_id: int,
        message_id: int,
        output_path: Path,
        status_update_fn: Optional[Callable[[str], asyncio.Future]] = None
    ) -> Path:
        """
        Скачивает видео ЛЮБОГО размера (до 2 ГБ) напрямую через Telegram MTProto,
        рассчитывая процент и примерное оставшееся время скачивания.
        """
        client = await self.get_client()
        msg = await client.get_messages(chat_id, ids=message_id)
        if not msg or not msg.media:
            raise ValueError("Медиафайл не найден в сообщении.")

        start_time = time.time()
        last_edit_time = [0.0]

        async def _progress(current: int, total: int):
            now = time.time()
            elapsed = now - start_time
            # Обновляем статус раз в 3.5 секунды во избежание Telegram FloodWait
            if now - last_edit_time[0] >= 3.5 and status_update_fn and elapsed > 0.5:
                last_edit_time[0] = now
                percent = int(current / total * 100) if total > 0 else 0
                speed = current / elapsed  # байт в секунду
                remaining_bytes = total - current
                eta_sec = int(remaining_bytes / speed) if speed > 0 else 0

                cur_mb = round(current / (1024 * 1024), 1)
                tot_mb = round(total / (1024 * 1024), 1)

                if eta_sec > 60:
                    eta_str = f"{eta_sec // 60} мин {eta_sec % 60} сек"
                else:
                    eta_str = f"{eta_sec} сек"

                text = (
                    f"⏳ <b>Скачиваю видео напрямую из Telegram:</b>\n"
                    f"• Прогресс: <b>{percent}%</b> ({cur_mb} из {tot_mb} МБ)\n"
                    f"• Примерное время: <b>(осталось ~{eta_str})</b>"
                )
                try:
                    await status_update_fn(text)
                except Exception:
                    pass

        # Запускаем скачивание напрямую с серверов Telegram
        await client.download_media(msg, file=str(output_path), progress_callback=_progress)
        return output_path
