import asyncio
import os
from pathlib import Path
from aiohttp import web
from config import TEMP_DIR, BASE_DIR
from bot.keyboards import get_process_keyboard, MODE_NAMES

routes = web.RouteTableDef()
TEMPLATES_DIR = BASE_DIR / "web" / "templates"

bot_instance = None
user_sessions_ref = None

def init_web_app(bot, user_sessions):
    global bot_instance, user_sessions_ref
    bot_instance = bot
    user_sessions_ref = user_sessions
    app = web.Application(client_max_size=15 * 1024 * 1024 * 1024)  # Лимит до 15 ГБ
    app.add_routes(routes)
    return app

@routes.get("/")
@routes.get("/upload")
async def handle_index(request: web.Request):
    html_path = TEMPLATES_DIR / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="Web Uploader Page Not Found", status=404)

@routes.post("/api/upload")
async def handle_upload(request: web.Request):
    reader = await request.multipart()
    user_id = 6493650695
    input_path = None
    file_size = 0

    while True:
        part = await reader.next()
        if part is None:
            break

        if part.name == "user_id":
            val = await part.text()
            try:
                user_id = int(val)
            except Exception:
                pass
        elif part.name == "video":
            filename = part.filename or "uploaded_video.mp4"
            ext = Path(filename).suffix or ".mp4"
            input_path = TEMP_DIR / f"user_{user_id}_input{ext}"

            # Потоковая запись чанками по 1 МБ (не расходует оперативную память)
            with open(input_path, "wb") as f:
                while True:
                    chunk = await part.read_chunk(size=1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    file_size += len(chunk)

    if input_path and input_path.exists() and file_size > 0:
        size_gb = round(file_size / (1024 * 1024 * 1024), 2)
        size_mb = round(file_size / (1024 * 1024), 1)
        size_str = f"{size_gb} ГБ" if size_gb >= 1.0 else f"{size_mb} МБ"

        # Привязываем видео к сессии бота
        if user_sessions_ref is not None:
            if user_id not in user_sessions_ref:
                user_sessions_ref[user_id] = {
                    "input_video": None,
                    "reference_url": None,
                    "prompt": None,
                    "mode": "edit_tiktok",
                    "custom_music_path": None,
                    "use_ai_music": True,
                    "add_sfx": True
                }
            session = user_sessions_ref[user_id]
            session["input_video"] = input_path

            # Оповещаем пользователя в Telegram
            if bot_instance is not None:
                try:
                    kb = get_process_keyboard(
                        mode=session["mode"],
                        has_custom_music=session.get("custom_music_path") is not None,
                        use_ai_music=session.get("use_ai_music", True),
                        add_sfx=session.get("add_sfx", True)
                    )
                    notify_text = (
                        f"🎉 <b>Видео успешно получено через веб-студию!</b>\n"
                        f"• Размер файла: <b>{size_str}</b>\n"
                        f"• Режим монтажа: <b>{MODE_NAMES.get(session['mode'])}</b>\n\n"
                        "Нажмите кнопку ниже для запуска монтажа:"
                    )
                    await bot_instance.send_message(chat_id=user_id, text=notify_text, reply_markup=kb, parse_mode="HTML")
                except Exception as e:
                    print("Telegram notify error:", e)

        return web.json_response({"status": "ok", "size": file_size, "path": str(input_path)})

    return web.json_response({"error": "No file received"}, status=400)
