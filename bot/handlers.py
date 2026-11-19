import os
import re
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
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

# Сессии пользователей
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
        "👉 <b>Как отправить видео:</b>\n"
        "• Файлом в чат (до 20 МБ из-за ограничений Telegram)\n"
        "• Или ссылкой на диск/видео (Google Drive, Яндекс.Диск, YouTube — без ограничений по размеру!)\n"
        "• Также можете прикрепить ссылку на референс (TikTok/Reels)."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    help_text = (
        "ℹ️ <b>Как пользоваться студией:</b>\n\n"
        "1. <b>Исходное видео:</b> отправьте файл до 20 МБ прямо в чат ИЛИ пришлите ссылку на видео (Google Диск, YouTube, Яндекс.Диск).\n"
        "2. <b>Референс (опционально):</b> ссылка на TikTok / Reels для повторения темпа.\n"
        "3. Нажмите <b>«🚀 Запустить монтаж»</b>.\n"
        "4. Получите готовый смонтированный ролик!"
    )
    await callback.message.answer(help_text, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.in_(["preset_reels", "preset_reference", "settings"]))
async def cb_presets(callback: CallbackQuery):
    if callback.data == "preset_reels":
        await callback.message.answer(
            "⚡ <b>Выбран пресет: Быстрый Reels / Shorts</b>\n"
            "Авто-удаление пауз + динамические зумы 1.1x.\n"
            "Отправьте видео или ссылку на него!",
            parse_mode="HTML"
        )
    elif callback.data == "preset_reference":
        await callback.message.answer(
            "🔗 Отправьте ссылку на видео-референс (TikTok, Reels или Shorts):",
            parse_mode="HTML"
        )
    elif callback.data == "settings":
        await callback.message.answer(
            "⚙️ <b>Текущие настройки:</b>\n"
            "• Порог тишины: <code>-30 dB</code>\n"
            "• Мин. пауза: <code>0.5 сек</code>\n"
            "• Динамический зум: <code>1.1x</code>\n"
            "• Лимит прямого файла Telegram: <code>20 МБ</code> (ссылки без лимита)",
            parse_mode="HTML"
        )
    await callback.answer()

@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot, state: FSMContext):
    document = message.video or message.document
    if message.document and not (message.document.mime_type and "video" in message.document.mime_type):
        await message.answer("Пожалуйста, отправьте видеофайл (mp4, mov, avi).")
        return

    file_size = getattr(document, "file_size", 0) or 0
    # Telegram Bot API имеет жесткий лимит 20 МБ на скачивание файлов ботом
    max_size_bytes = 20 * 1024 * 1024

    if file_size > max_size_bytes:
        size_mb = round(file_size / (1024 * 1024), 1)
        warning_text = (
            f"⚠️ <b>Файл слишком большой ({size_mb} МБ)!</b>\n\n"
            "Telegram Bot API официально запрещает ботам напрямую скачивать файлы тяжелее <b>20 МБ</b>.\n\n"
            "💡 <b>Как обработать это видео:</b>\n"
            "1. Загрузите его на <b>Google Диск</b>, <b>Яндекс.Диск</b> или <b>YouTube</b> и отправьте боту ссылку — скачаем без ограничений!\n"
            "2. Либо отправьте более короткий/сжатый фрагмент видео (до 20 МБ, около 1–2 минут)."
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
            "Теперь вы можете:\n"
            "• Отправить ссылку на референс (TikTok / Reels / Shorts)\n"
            "• Написать текстовые пожелания к монтажу\n"
            "• Или сразу нажать <b>«🚀 Запустить монтаж»</b>:",
            reply_markup=get_process_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Не удалось скачать файл: {e}\n"
            "Попробуйте отправить файл меньшего размера или ссылкой на облако/YouTube.",
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("set_link_"))
async def cb_set_link_type(callback: CallbackQuery):
    action = callback.data.replace("set_link_", "")
    user_id = callback.from_user.id
    session = get_session(user_id)
    url = session.get("pending_url")

    if not url:
        await callback.message.edit_text("Ссылка устарела. Отправьте ее снова.")
        await callback.answer()
        return

    if action == "input":
        # Скачиваем по ссылке как исходник для монтажа
        msg = await callback.message.edit_text(f"⏳ Скачиваю исходное видео по ссылке...\n<code>{url}</code>", parse_mode="HTML")
        try:
            downloaded = await VideoDownloader.download_reference(url, f"user_{user_id}_input.mp4")
            session["input_video"] = downloaded
            await msg.edit_text(
                "✅ <b>Исходное видео успешно скачано!</b>\n\n"
                "Теперь можете прикрепить ссылку на референс, написать пожелания или запустить монтаж:",
                reply_markup=get_process_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка скачивания видео по ссылке: {e}")
    else:
        # Устанавливаем как референс стиля
        session["reference_url"] = url
        if session.get("input_video"):
            await callback.message.edit_text(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n"
                "Видео и референс готовы к обработке!",
                reply_markup=get_process_keyboard(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n\n"
                "👉 Теперь отправьте ваше исходное видео (файлом до 20 МБ или ссылкой)!",
                parse_mode="HTML"
            )
    await callback.answer()

@router.message(F.text)
async def handle_text_or_url(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    session = get_session(user_id)

    # Поиск URL (YouTube, TikTok, Google Drive и т.д.)
    url_pattern = re.compile(r'https?://[^\s]+')
    urls = url_pattern.findall(text)

    if urls:
        url = urls[0]
        session["pending_url"] = url

        # Если уже есть исходное видео, по умолчанию считаем ссылку референсом
        if session.get("input_video"):
            session["reference_url"] = url
            await message.answer(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n"
                "Все готово к монтажу!",
                reply_markup=get_process_keyboard(),
                parse_mode="HTML"
            )
        else:
            # Спрашиваем: это исходник для монтажа или референс стиля?
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
                reply_markup=get_process_keyboard(),
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
