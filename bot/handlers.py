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

# Временное хранилище пользовательских сессий
user_sessions = {}

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🎬 **Добро пожаловать в AI-Editor (from softer_052)!**\n\n"
        "Я помогу вам автоматически смонтировать видео:\n"
        "1. Вырежу неловкие паузы и «воду»\n"
        "2. Добавлю динамические зумы (эффект удержания внимания)\n"
        "3. Смонтирую под темп любого видео-референса (YouTube / Reels / TikTok)\n\n"
        "📤 **Отправьте мне видео**, которое хотите смонтировать (файлом или видеосообщением):"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    help_text = (
        "ℹ️ **Как пользоваться студией автомонтажа:**\n\n"
        "1. Отправьте исходное видео в этот чат.\n"
        "2. Пришлите ссылку на видео-референс или напишите текстом пожелания.\n"
        "3. Бот проанализирует референс, вырежет паузы и смонтирует ролик.\n"
        "4. Готовый файл придет вам прямо сюда в высоком качестве!"
    )
    await callback.message.answer(help_text, parse_mode="Markdown")
    await callback.answer()

@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot, state: FSMContext):
    document = message.video or message.document
    if message.document and not (message.document.mime_type and "video" in message.document.mime_type):
        await message.answer("Пожалуйста, отправьте именно видеофайл (mp4, mov).")
        return

    status_msg = await message.answer("⏳ Скачиваю видео на сервер обработки...")
    file_id = document.file_id
    file_info = await bot.get_file(file_id)
    
    file_ext = Path(file_info.file_path).suffix or ".mp4"
    user_id = message.from_user.id
    input_path = TEMP_DIR / f"user_{user_id}_input{file_ext}"

    await bot.download_file(file_info.file_path, destination=input_path)
    
    user_sessions[user_id] = {
        "input_video": input_path,
        "reference_url": None,
        "prompt": None
    }
    await state.set_state(EditorStates.waiting_for_reference_or_prompt)

    await status_msg.edit_text(
        "✅ **Видео успешно получено!**\n\n"
        "Теперь вы можете:\n"
        "• Отправить **ссылку на референс** (YouTube Shorts / Reels / TikTok)\n"
        "• Написать **текстовые требования** (например: «сделай быстрый клиповый монтаж, удали все паузы»)\n"
        "• Или нажмите кнопку ниже для быстрого авто-монтажа:",
        reply_markup=get_process_keyboard(),
        parse_mode="Markdown"
    )

@router.message(EditorStates.waiting_for_reference_or_prompt, F.text)
async def handle_reference_or_prompt(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    session = user_sessions.get(user_id, {})

    # Проверка: ссылка ли это
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(text)

    if urls:
        session["reference_url"] = urls[0]
        await message.answer(
            f"🔗 Референс принят: `{urls[0]}`\nГотов к монтажу по стилю этого видео!",
            reply_markup=get_process_keyboard(),
            parse_mode="Markdown"
        )
    else:
        session["prompt"] = text
        await message.answer(
            f"📝 Требования приняты: *{text}*\nНажмите кнопку ниже для запуска:",
            reply_markup=get_process_keyboard(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "start_render")
async def process_video(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    session = user_sessions.get(user_id)

    if not session or "input_video" not in session:
        await callback.message.answer("Сначала отправьте исходное видео.")
        await callback.answer()
        return

    input_video = session["input_video"]
    ref_url = session.get("reference_url")
    
    status_msg = await callback.message.edit_text("🔍 **Шаг 1/3:** Анализирую паузы и структуру речи...")
    
    try:
        # Анализ референса, если ссылка была предоставлена
        pace_info = None
        if ref_url:
            await status_msg.edit_text("📥 **Шаг 1/3:** Скачиваю и анализирую видео-референс...")
            try:
                ref_path = await VideoDownloader.download_reference(ref_url, f"ref_{user_id}.mp4")
                pace_info = await VideoAnalyzer.analyze_cuts(ref_path)
            except Exception as e:
                await callback.message.answer(f"⚠️ Не удалось распарсить референс ({e}), использую стандартный динамичный темп.")

        await status_msg.edit_text("✂️ **Шаг 2/3:** Нахожу немые паузы для вырезания...")
        silences = await AudioAnalyzer.detect_silence(input_video)

        await status_msg.edit_text(
            f"🎬 **Шаг 3/3:** Монтирую ролик... Найдено пауз: {len(silences)}.\nПрименяю динамический зум и склейку..."
        )
        
        output_name = f"result_{user_id}.mp4"
        result_path = await VideoProcessor.cut_silences_and_render(
            input_video=input_video,
            silences=silences,
            output_name=output_name,
            apply_dynamic_zoom=True
        )

        await status_msg.edit_text("🚀 Отправляю готовое видео в чат...")
        video_file = FSInputFile(result_path)
        
        caption = (
            "✨ **Ваше видео готово!**\n"
            f"• Вырезано пауз: {len(silences)}\n"
            f"• Стиль: {pace_info['pace'] if pace_info else 'Reels Dynamic'}\n\n"
            "Смонтировано в **ai-editor from softer_052**"
        )
        await callback.message.answer_video(video=video_file, caption=caption, parse_mode="Markdown")
        await status_msg.delete()

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка во время монтажа: {e}")
    finally:
        await state.clear()
        await callback.answer()
