import os
import re
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TEMP_DIR
from bot.keyboards import get_main_keyboard, get_process_keyboard
from core.downloader import VideoDownloader
from core.video_analyzer import VideoAnalyzer
from core.audio_analyzer import AudioAnalyzer
from core.video_processor import VideoProcessor

router = Router()

class EditorStates(StatesGroup):
    waiting_for_video = State()
    waiting_for_reference_or_prompt = State()
    processing = State()

# Сессии пользователей: { user_id: { "input_video": Path, "reference_url": str, "prompt": str } }
user_sessions = {}

def get_session(user_id: int) -> dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "input_video": None,
            "reference_url": None,
            "prompt": None
        }
    return user_sessions[user_id]

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🎬 <b>Добро пожаловать в AI-Editor (from softer_052)!</b>\n\n"
        "Я помогу вам автоматически смонтировать видео:\n"
        "1. ✂️ Вырежу неловкие паузы и «воду»\n"
        "2. 🔍 Добавлю динамические зумы (удержание внимания)\n"
        "3. 🔗 Смонтирую под темп любого референса (TikTok, Reels, Shorts)\n\n"
        "👉 <b>Отправьте мне ваше видео</b> (файлом или видеосообщением) или <b>ссылку на референс</b>!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    help_text = (
        "ℹ️ <b>Как пользоваться студией:</b>\n\n"
        "1. Отправьте видео, которое хотите смонтировать.\n"
        "2. Пришлите ссылку на TikTok / Reels / Shorts (или опишите текстом стиль).\n"
        "3. Нажмите кнопку <b>«🚀 Запустить монтаж»</b>.\n"
        "4. Получите готовое смонтированное видео обратно в чат!"
    )
    await callback.message.answer(help_text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.in_(["preset_reels", "preset_reference", "settings"]))
async def cb_presets(callback: CallbackQuery):
    if callback.data == "preset_reels":
        await callback.message.answer(
            "⚡ <b>Выбран пресет: Быстрый Reels / Shorts</b>\n"
            "Будет применено: авто-удаление всех пауз + динамические зумы 1.1x.\n"
            "Теперь отправьте видео (если еще не отправляли) или нажмите запуск!",
            parse_mode="HTML"
        )
    elif callback.data == "preset_reference":
        await callback.message.answer(
            "🔗 Отправьте ссылку на видео-референс (TikTok, Reels или YouTube Shorts):",
            parse_mode="HTML"
        )
    elif callback.data == "settings":
        await callback.message.answer(
            "⚙️ <b>Текущие настройки:</b>\n"
            "• Порог тишины: <code>-30 dB</code>\n"
            "• Мин. длительность паузы: <code>0.5 сек</code>\n"
            "• Динамический зум: <code>Включен (1.1x)</code>\n"
            "• Формат: <code>MP4 (H.264)</code>",
            parse_mode="HTML"
        )
    await callback.answer()

@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot, state: FSMContext):
    document = message.video or message.document
    if message.document and not (message.document.mime_type and "video" in message.document.mime_type):
        await message.answer("Пожалуйста, отправьте именно видеофайл (mp4, mov, avi).")
        return

    status_msg = await message.answer("⏳ Скачиваю видео на сервер обработки...")
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
        f"✅ <b>Видео успешно получено!</b>{ref_status}\n\n"
        "Теперь вы можете:\n"
        "• Отправить ссылку на референс (TikTok / Reels / Shorts)\n"
        "• Написать текстовые пожелания к монтажу\n"
        "• Или сразу нажать <b>«🚀 Запустить монтаж»</b>:",
        reply_markup=get_process_keyboard(),
        parse_mode="HTML"
    )

@router.message(F.text)
async def handle_text_or_url(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    session = get_session(user_id)

    # Поиск URL (YouTube, TikTok, Instagram и т.д.)
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(text)

    if urls:
        session["reference_url"] = urls[0]
        if session.get("input_video"):
            await message.answer(
                f"🔗 <b>Референс принят:</b> <code>{urls[0]}</code>\n"
                "Видео и референс готовы! Нажмите кнопку ниже для запуска:",
                reply_markup=get_process_keyboard(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"🔗 <b>Референс принят:</b> <code>{urls[0]}</code>\n\n"
                "👉 Теперь <b>отправьте ваше исходное видео</b> (файлом или видеосообщением), которое нужно смонтировать по этому образцу!",
                parse_mode="HTML"
            )
    else:
        session["prompt"] = text
        if session.get("input_video"):
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n"
                "Нажмите кнопку ниже для запуска монтажа:",
                reply_markup=get_process_keyboard(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n\n"
                "👉 Теперь <b>отправьте ваше исходное видео</b> для монтажа!",
                parse_mode="HTML"
            )

@router.callback_query(F.data == "start_render")
async def process_video(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    session = get_session(user_id)

    if not session.get("input_video"):
        await callback.message.answer("⚠️ Сначала отправьте исходное видео в чат.")
        await callback.answer()
        return

    input_video = session["input_video"]
    ref_url = session.get("reference_url")
    
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

        await status_msg.edit_text(
            f"🎬 <b>Шаг 3/3:</b> Монтирую ролик...\n"
            f"• Найдено пауз: <b>{len(silences)}</b>\n"
            f"• Динамический зум: <b>Включен</b>\n"
            f"Идет рендеринг через FFmpeg...",
            parse_mode="HTML"
        )
        
        output_name = f"result_{user_id}.mp4"
        result_path = await VideoProcessor.cut_silences_and_render(
            input_video=input_video,
            silences=silences,
            output_name=output_name,
            apply_dynamic_zoom=True
        )

        await status_msg.edit_text("🚀 Отправляю готовое видео в чат...", parse_mode="HTML")
        video_file = FSInputFile(result_path)
        
        pace_str = pace_info['pace'] if pace_info else 'Reels Dynamic'
        caption = (
            "✨ <b>Ваше видео готово!</b>\n\n"
            f"• Вырезано немых пауз: <b>{len(silences)}</b>\n"
            f"• Темп склеек: <b>{pace_str}</b>\n\n"
            "Смонтировано в <b>ai-editor from softer_052</b>"
        )
        await callback.message.answer_video(video=video_file, caption=caption, parse_mode="HTML")
        await status_msg.delete()

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка во время монтажа: {e}")
    finally:
        await state.clear()
        await callback.answer()

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Обработка отменена. Отправьте /start для начала заново.")
    await callback.answer()
