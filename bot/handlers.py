import os
import re
import subprocess
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TEMP_DIR, FFMPEG_PATH
from bot.keyboards import get_main_keyboard, get_process_keyboard, get_settings_keyboard
from core.downloader import VideoDownloader
from core.video_analyzer import VideoAnalyzer
from core.audio_analyzer import AudioAnalyzer
from core.video_processor import VideoProcessor

router = Router()

class EditorStates(StatesGroup):
    waiting_for_video = State()
    waiting_for_reference_or_prompt = State()
    processing = State()

# Сессии пользователей
user_sessions = {}

def get_session(user_id: int) -> dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "input_video": None,
            "reference_url": None,
            "prompt": None,
            "add_sfx": True,
            "add_music": False
        }
    return user_sessions[user_id]

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🎬 <b>Добро пожаловать в AI-Editor (from softer_052)!</b>\n\n"
        "Я помогу вам автоматически смонтировать видео:\n"
        "1. ✂️ <b>Вырезка пауз</b> и вздохов\n"
        "2. 🔍 <b>Динамические зумы</b> (удержание внимания)\n"
        "3. 🔊 <b>Звуковые эффекты переходов (Whoosh)</b> на склейках\n"
        "4. 🎵 <b>Фоновая музыка (Lo-Fi)</b> с авто-балансом под голос\n"
        "5. 🔗 Монтаж по любому референсу (TikTok, Reels, Shorts)\n\n"
        "👉 <b>Отправьте видео</b> (файлом или ссылкой на Google Drive / Яндекс.Диск)!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.answer()
    help_text = (
        "ℹ️ <b>Как пользоваться студией:</b>\n\n"
        "1. <b>Исходное видео:</b> отправьте файл до 20 МБ прямо в чат ИЛИ пришлите ссылку (Google Диск, YouTube, Яндекс.Диск).\n"
        "2. <b>Звук и эффекты:</b> вы можете включать/выключать Whoosh-переходы и фоновую музыку прямо перед запуском!\n"
        "3. Нажмите <b>«🚀 Запустить монтаж»</b>.\n"
        "4. Получите готовый динамичный ролик в чат!"
    )
    await callback.message.answer(help_text, parse_mode="HTML")

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    await callback.answer()
    session = get_session(callback.from_user.id)
    kb = get_settings_keyboard(session["add_sfx"], session["add_music"])
    await callback.message.edit_text(
        "⚙️ <b>Настройки звука и монтажа:</b>\n\n"
        "Нажимайте на кнопки, чтобы включить или выключить эффекты:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery):
    await callback.answer()
    welcome_text = (
        "🎬 <b>Главное меню AI-Editor:</b>\n\n"
        "Отправьте мне видео (файл или ссылку) для запуска монтажа:"
    )
    await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data.in_(["toggle_sfx", "toggle_music"]))
async def cb_toggle_audio(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = get_session(user_id)

    if callback.data == "toggle_sfx":
        session["add_sfx"] = not session.get("add_sfx", True)
        status = "включен ✅" if session["add_sfx"] else "выключен ❌"
        await callback.answer(f"Звук Whoosh {status}")
    elif callback.data == "toggle_music":
        session["add_music"] = not session.get("add_music", False)
        status = "включена ✅" if session["add_music"] else "выключена ❌"
        await callback.answer(f"Фоновая музыка {status}")

    # Обновляем клавиатуру в зависимости от контекста сообщения
    if session.get("input_video"):
        kb = get_process_keyboard(session["add_sfx"], session["add_music"])
    else:
        kb = get_settings_keyboard(session["add_sfx"], session["add_music"])
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

@router.callback_query(F.data.in_(["preset_reels", "preset_reference"]))
async def cb_presets(callback: CallbackQuery):
    await callback.answer()
    if callback.data == "preset_reels":
        await callback.message.answer(
            "⚡ <b>Выбран пресет: Быстрый Reels / Shorts</b>\n"
            "Авто-удаление пауз + динамические зумы 1.1x + Whoosh эффекты.\n"
            "Отправьте видео или ссылку на него!",
            parse_mode="HTML"
        )
    elif callback.data == "preset_reference":
        await callback.message.answer(
            "🔗 Отправьте ссылку на видео-референс (TikTok, Reels или Shorts):",
            parse_mode="HTML"
        )

@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot, state: FSMContext):
    document = message.video or message.document
    if message.document and not (message.document.mime_type and "video" in message.document.mime_type):
        await message.answer("Пожалуйста, отправьте видеофайл (mp4, mov, avi).")
        return

    file_size = getattr(document, "file_size", 0) or 0
    max_size_bytes = 20 * 1024 * 1024

    if file_size > max_size_bytes:
        size_mb = round(file_size / (1024 * 1024), 1)
        warning_text = (
            f"⚠️ <b>Файл слишком большой ({size_mb} МБ)!</b>\n\n"
            "Telegram Bot API запрещает ботам напрямую скачивать файлы тяжелее <b>20 МБ</b>.\n\n"
            "💡 <b>Как отправить это видео:</b>\n"
            "1. Загрузите его на <b>Google Диск</b> или <b>Яндекс.Диск</b> и отправьте боту ссылку — скачаем без ограничений!\n"
            "2. Либо отправьте более короткий/сжатый фрагмент (до 20 МБ, около 1–2 минут)."
        )
        await message.answer(warning_text, parse_mode="HTML")
        return

    status_msg = await message.answer("⏳ Скачиваю видео на сервер обработки...")
    try:
        file_id = document.file_id
        file_info = await bot.get_file(file_id)
        
        file_ext = Path(file_info.file_path).suffix or ".mp4"
        user_id = message.from_user.id
        input_path = TEMP_DIR / f"user_{user_id}_input{file_ext}"

        await bot.download_file(file_info.file_path, destination=input_path)
        
        session = get_session(user_id)
        session["input_video"] = input_path

        ref_status = f"\n🔗 <i>Прикреплен референс:</i> <code>{session['reference_url']}</code>" if session.get("reference_url") else ""

        await status_msg.edit_text(
            f"✅ <b>Видео успешно получено ({round(file_size/(1024*1024), 1)} МБ)!</b>{ref_status}\n\n"
            "Настройте звуковые эффекты кнопками ниже и запустите монтаж:",
            reply_markup=get_process_keyboard(session["add_sfx"], session["add_music"]),
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Не удалось скачать файл: {e}\n"
            "Попробуйте отправить файл меньшего размера или ссылкой на диск/YouTube.",
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("set_link_"))
async def cb_set_link_type(callback: CallbackQuery):
    await callback.answer()
    action = callback.data.replace("set_link_", "")
    user_id = callback.from_user.id
    session = get_session(user_id)
    url = session.get("pending_url")

    if not url:
        await callback.message.edit_text("Ссылка устарела. Отправьте ее снова.")
        return

    if action == "input":
        msg = await callback.message.edit_text(f"⏳ Скачиваю исходное видео по ссылке...\n<code>{url}</code>", parse_mode="HTML")
        try:
            downloaded = await VideoDownloader.download_reference(url, f"user_{user_id}_input.mp4")
            session["input_video"] = downloaded
            await msg.edit_text(
                "✅ <b>Исходное видео успешно скачано!</b>\n\n"
                "Настройте звуковые эффекты и нажмите запуск:",
                reply_markup=get_process_keyboard(session["add_sfx"], session["add_music"]),
                parse_mode="HTML"
            )
        except Exception as e:
            await msg.edit_text(f"❌ {e}", parse_mode="HTML")
    else:
        session["reference_url"] = url
        if session.get("input_video"):
            await callback.message.edit_text(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n"
                "Видео и референс готовы к обработке!",
                reply_markup=get_process_keyboard(session["add_sfx"], session["add_music"]),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n\n"
                "👉 Теперь отправьте ваше исходное видео (файлом до 20 МБ или ссылкой)!",
                parse_mode="HTML"
            )

@router.message(F.text)
async def handle_text_or_url(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    session = get_session(user_id)

    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(text)

    if urls:
        url = urls[0]
        session["pending_url"] = url

        if session.get("input_video"):
            session["reference_url"] = url
            await message.answer(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n"
                "Все готово к монтажу!",
                reply_markup=get_process_keyboard(session["add_sfx"], session["add_music"]),
                parse_mode="HTML"
            )
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📥 Это исходное видео (смонтировать его)", callback_data="set_link_input")
                ],
                [
                    InlineKeyboardButton(text="🎯 Это референс стиля (Shorts / TikTok)", callback_data="set_link_ref")
                ]
            ])
            await message.answer(
                f"🔗 <b>Получена ссылка:</b> <code>{url}</code>\n\n"
                "Уточните, как использовать эту ссылку:",
                reply_markup=kb,
                parse_mode="HTML"
            )
    else:
        session["prompt"] = text
        if session.get("input_video"):
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n"
                "Нажмите кнопку ниже для запуска монтажа:",
                reply_markup=get_process_keyboard(session["add_sfx"], session["add_music"]),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n\n"
                "👉 Теперь отправьте исходное видео для монтажа (файл или ссылку)!",
                parse_mode="HTML"
            )

@router.callback_query(F.data == "start_render")
async def process_video(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer("Запускаю процесс монтажа...")
    
    user_id = callback.from_user.id
    session = get_session(user_id)

    if not session.get("input_video"):
        await callback.message.answer("⚠️ Сначала отправьте исходное видео в чат.")
        return

    input_video = session["input_video"]
    ref_url = session.get("reference_url")
    add_sfx = session.get("add_sfx", True)
    add_music = session.get("add_music", False)
    
    status_msg = await callback.message.edit_text("🔍 <b>Шаг 1/3:</b> Анализирую структуру речи и пауз...", parse_mode="HTML")
    
    try:
        pace_info = None
        if ref_url:
            await status_msg.edit_text("📥 <b>Шаг 1/3:</b> Скачиваю и анализирую видео-референс...", parse_mode="HTML")
            try:
                ref_path = await VideoDownloader.download_reference(ref_url, f"ref_{user_id}.mp4")
                pace_info = await VideoAnalyzer.analyze_cuts(ref_path)
            except Exception as e:
                await callback.message.answer(f"⚠️ Не удалось распарсить референс ({e}), использую стандартный динамичный темп.")

        await status_msg.edit_text("✂️ <b>Шаг 2/3:</b> Нахожу немые паузы для вырезания...", parse_mode="HTML")
        silences = await AudioAnalyzer.detect_silence(input_video)

        sfx_text = "Включены (Whoosh 🔊)" if add_sfx else "Выключены"
        music_text = "Включена (Lo-Fi 🎵)" if add_music else "Выключена"

        await status_msg.edit_text(
            f"🎬 <b>Шаг 3/3:</b> Монтирую ролик...\n"
            f"• Найдено пауз: <b>{len(silences)}</b>\n"
            f"• Динамический зум: <b>Включен (1.1x)</b>\n"
            f"• SFX Переходы: <b>{sfx_text}</b>\n"
            f"• Фоновая музыка: <b>{music_text}</b>\n\n"
            f"Идет рендеринг через FFmpeg...",
            parse_mode="HTML"
        )
        
        output_name = f"result_{user_id}.mp4"
        result_path = await VideoProcessor.cut_silences_and_render(
            input_video=input_video,
            silences=silences,
            output_name=output_name,
            apply_dynamic_zoom=True,
            add_sfx_whoosh=add_sfx,
            add_bg_music=add_music
        )

        final_size = result_path.stat().st_size
        max_upload_size = 49 * 1024 * 1024

        if final_size > max_upload_size:
            await status_msg.edit_text("📦 Оптимизирую видео под лимит Telegram (до 50 МБ)...", parse_mode="HTML")
            compressed_path = TEMP_DIR / f"result_{user_id}_compressed.mp4"
            cmd_compress = [
                FFMPEG_PATH, "-y", "-i", str(result_path),
                "-vf", "scale=-2:720",
                "-c:v", "libx264", "-crf", "28",
                "-maxrate", "950k", "-bufsize", "1900k",
                "-c:a", "aac", "-b:a", "96k",
                str(compressed_path)
            ]
            proc = subprocess.run(cmd_compress, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode == 0 and compressed_path.exists():
                result_path = compressed_path

        await status_msg.edit_text("🚀 Отправляю готовое видео в чат...", parse_mode="HTML")
        video_file = FSInputFile(result_path)
        
        pace_str = pace_info['pace'] if pace_info else 'Reels Dynamic'
        caption = (
            "✨ <b>Ваше видео готово!</b>\n\n"
            f"• Вырезано немых пауз: <b>{len(silences)}</b>\n"
            f"• SFX переходы (Whoosh): <b>{'Да 🔊' if add_sfx else 'Нет'}</b>\n"
            f"• Фоновая музыка: <b>{'Да 🎵' if add_music else 'Нет'}</b>\n"
            f"• Стиль: <b>{pace_str}</b>\n\n"
            "Смонтировано в <b>ai-editor from softer_052</b>"
        )
        await callback.message.answer_video(video=video_file, caption=caption, parse_mode="HTML")
        await status_msg.delete()

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка во время монтажа: {e}")
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Обработка отменена. Отправьте /start для начала заново.")
