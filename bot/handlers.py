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
from bot.keyboards import (
    get_main_keyboard,
    get_mode_selected_keyboard,
    get_process_keyboard,
    get_mode_selection_keyboard,
    get_music_settings_keyboard,
    MODE_NAMES
)
from core.downloader import VideoDownloader
from core.telegram_downloader import TelegramDownloader
from core.video_analyzer import VideoAnalyzer
from core.audio_analyzer import AudioAnalyzer
from core.video_processor import VideoProcessor
from core.music_selector import MusicSelector, PRESET_TRACKS

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
            "mode": "edit_tiktok",             # "edit_tiktok" | "youtube_long" | "clean_silence"
            "custom_music_path": None,
            "use_ai_music": True,
            "add_sfx": True
        }
    return user_sessions[user_id]

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "🎬 <b>Добро пожаловать в AI-Editor Studio (from softer_052)!</b>\n\n"
        "Выберите желаемый <b>режим монтажа</b>:\n"
        "• ⚡ <b>Клиповый Эдит (Shorts/TikTok)</b> — ультрадинамика, зумы 1.15x, Whoosh, драйв\n"
        "• 📺 <b>YouTube (Длинное видео)</b> — плавный темп 16:9, без резких скачков, мягкий фон\n"
        "• ✂️ <b>Чистка пауз и тишины</b> — чистый оригинальный ракурс без эффектов и зумов\n\n"
        "🚀 <b>Видео до 2 ГБ можно отправлять прямо файлом в чат!</b>\n"
        "🌐 Для гигантских видео <b>от 2 до 10 ГБ</b> есть прямая веб-страница загрузки.\n\n"
        "👉 <b>Выберите режим ниже:</b>"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await callback.answer()
    help_text = (
        "ℹ️ <b>Возможности студии:</b>\n\n"
        "1. <b>Прямая отправка видео любого размера:</b>\n"
        "• До 2 ГБ — прямо в чат Telegram с таймером в скобочках.\n"
        "• До 10 ГБ — через веб-сайт быстрой загрузки по локальной сети.\n\n"
        "2. <b>Режимы:</b>\n"
        "• <code>Эдит</code> — быстрый нарезной клип с зумами и звуками.\n"
        "• <code>YouTube</code> — полноформатное длинное видео с мягкой чисткой пауз.\n"
        "• <code>Чистка</code> — вырезает немые паузы, вздохи и заминки без изменения картинки.\n\n"
        "3. <b>Музыка:</b>\n"
        "• Отправьте любой <b>аудиофайл или голосовое</b> в чат, и бот возьмет его как фоновый трек!\n"
        "• Либо выберите <b>AI-подбор</b> — бот сам выберет трек под видео."
    )
    await callback.message.answer(help_text, parse_mode="HTML")

@router.callback_query(F.data == "open_web_uploader")
async def cb_open_web_uploader(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    local_ip = "192.168.0.108"
    web_url = f"http://{local_ip}:8080/upload?user_id={user_id}"
    
    msg_text = (
        "🌐 <b>Студия загрузки видео до 10 ГБ:</b>\n\n"
        "Если ваше видео весит больше 2 ГБ (или 4K 60fps), откройте страницу загрузки:\n\n"
        f"👉 <a href=\"{web_url}\"><b>{web_url}</b></a>\n\n"
        "• 📱 <b>С телефона:</b> откройте ссылку в мобильном браузере (при подключении к домашнему Wi-Fi)\n"
        "• 💻 <b>С компьютера:</b> <a href=\"http://localhost:8080/upload\"><b>http://localhost:8080/upload</b></a>\n"
        "• ⏱️ На странице работает живая шкала, скорость и <b>время загрузки в скобочках</b>!\n"
        "• После загрузки бот мгновенно получит видео и напишет вам в этот чат."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Открыть сайт загрузки (до 10 ГБ)", url=web_url)
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_process")
        ]
    ])
    await callback.message.answer(msg_text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "change_mode")
async def cb_change_mode(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🎛️ <b>Выберите новый режим монтажа:</b>",
        reply_markup=get_mode_selection_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("mode_"))
async def cb_set_mode(callback: CallbackQuery):
    await callback.answer()
    mode = callback.data.replace("mode_", "")
    session = get_session(callback.from_user.id)
    session["mode"] = mode

    mode_title = MODE_NAMES.get(mode, mode)
    
    if session.get("input_video"):
        kb = get_process_keyboard(
            mode=session["mode"],
            has_custom_music=session.get("custom_music_path") is not None,
            use_ai_music=session.get("use_ai_music", True),
            add_sfx=session.get("add_sfx", True)
        )
        await callback.message.edit_text(
            f"✅ Режим изменен на: <b>{mode_title}</b>\n\nГотовы к монтажу:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"✅ Выбран режим: <b>{mode_title}</b>\n\n"
            "👉 Теперь <b>отправьте видео</b> (файлом прямо в чат или через кнопку загрузки до 10 ГБ):",
            reply_markup=get_mode_selected_keyboard(session["mode"]),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "music_settings")
async def cb_music_settings(callback: CallbackQuery):
    await callback.answer()
    session = get_session(callback.from_user.id)
    has_custom = session.get("custom_music_path") is not None
    use_ai = session.get("use_ai_music", True)

    await callback.message.edit_text(
        "🎵 <b>Управление музыкой:</b>\n\n"
        "Вы можете доверить выбор нейросети, выбрать жанр вручную или прислать свой трек файлом в чат:",
        reply_markup=get_music_settings_keyboard(has_custom, use_ai),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("music_"))
async def cb_select_music_preset(callback: CallbackQuery):
    m_type = callback.data.replace("music_", "")
    user_id = callback.from_user.id
    session = get_session(user_id)

    if m_type == "how_to_upload":
        await callback.answer()
        await callback.message.answer(
            "💡 <b>Как добавить свою музыку:</b>\n"
            "Просто отправьте в чат боту любой <b>MP3 файл, трек или голосовое</b>. "
            "Бот автоматически подстроит его громкость и наложит на видео!",
            parse_mode="HTML"
        )
        return

    if m_type == "ai":
        session["use_ai_music"] = True
        session["custom_music_path"] = None
        await callback.answer("Включен AI-подбор музыки 🤖")
    elif m_type == "off":
        session["use_ai_music"] = False
        session["custom_music_path"] = None
        await callback.answer("Музыка выключена ❌")
    elif m_type in PRESET_TRACKS:
        session["use_ai_music"] = False
        session["custom_music_path"] = PRESET_TRACKS[m_type]["file"]
        await callback.answer(f"Выбран трек: {PRESET_TRACKS[m_type]['name']}")

    if session.get("input_video"):
        kb = get_process_keyboard(
            mode=session["mode"],
            has_custom_music=session.get("custom_music_path") is not None,
            use_ai_music=session.get("use_ai_music", True),
            add_sfx=session.get("add_sfx", True)
        )
        await callback.message.edit_text("⚙️ Настройки музыки сохранены!", reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"⚙️ Настройки музыки сохранены!\nРежим: <b>{MODE_NAMES.get(session['mode'])}</b>\n\n👉 Отправьте видео для старта:",
            reply_markup=get_mode_selected_keyboard(session["mode"]),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "back_to_process")
async def cb_back_to_process(callback: CallbackQuery):
    await callback.answer()
    session = get_session(callback.from_user.id)
    if session.get("input_video"):
        kb = get_process_keyboard(
            mode=session["mode"],
            has_custom_music=session.get("custom_music_path") is not None,
            use_ai_music=session.get("use_ai_music", True),
            add_sfx=session.get("add_sfx", True)
        )
        await callback.message.edit_text("Готовы к запуску монтажа:", reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(
            f"Текущий режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n\n👉 Отправьте видео для монтажа:",
            reply_markup=get_mode_selected_keyboard(session["mode"]),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "toggle_sfx")
async def cb_toggle_sfx(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = get_session(user_id)
    session["add_sfx"] = not session.get("add_sfx", True)
    status = "включен ✅" if session["add_sfx"] else "выключен ❌"
    await callback.answer(f"Whoosh {status}")

    kb = get_process_keyboard(
        mode=session["mode"],
        has_custom_music=session.get("custom_music_path") is not None,
        use_ai_music=session.get("use_ai_music", True),
        add_sfx=session["add_sfx"]
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

# Прием пользовательской музыки (Audio / Voice)
@router.message(F.audio | F.voice)
async def handle_custom_audio(message: Message, bot: Bot):
    user_id = message.from_user.id
    session = get_session(user_id)

    file_obj = message.audio or message.voice
    status_msg = await message.answer("⏳ Сохраняю ваш музыкальный трек...")

    file_info = await bot.get_file(file_obj.file_id)
    music_ext = Path(file_info.file_path).suffix or ".mp3"
    music_dest = TEMP_DIR / f"user_{user_id}_custom_music{music_ext}"

    await bot.download_file(file_info.file_path, destination=music_dest)
    session["custom_music_path"] = music_dest
    session["use_ai_music"] = False

    track_title = getattr(message.audio, "title", "Пользовательский трек") if message.audio else "Голосовая дорожка"

    if session.get("input_video"):
        kb = get_process_keyboard(
            mode=session["mode"],
            has_custom_music=True,
            use_ai_music=False,
            add_sfx=session.get("add_sfx", True)
        )
        await status_msg.edit_text(
            f"🎵 <b>Трек успешно установлен:</b> <i>{track_title}</i>\n"
            "Он будет сведен с видео на фоне голоса. Нажмите старт:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(
            f"🎵 <b>Трек успешно установлен:</b> <i>{track_title}</i>\n\n"
            f"Режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n"
            "👉 Теперь отправьте ваше видео (файл или ссылку)!",
            reply_markup=get_mode_selected_keyboard(session["mode"]),
            parse_mode="HTML"
        )

# Прием видео ЛЮБОГО размера (через Telegram MTProto без лимита 20 МБ)
@router.message(F.video | F.document)
async def handle_video(message: Message, bot: Bot, state: FSMContext):
    document = message.video or message.document
    if message.document and not (message.document.mime_type and "video" in message.document.mime_type):
        await message.answer("Пожалуйста, отправьте видеофайл (mp4, mov, avi).")
        return

    file_size = getattr(document, "file_size", 0) or 0
    size_mb = round(file_size / (1024 * 1024), 1)

    # Если файл больше 2 ГБ, отправляем ссылку на веб-загрузчик до 10 ГБ
    if file_size > 2000 * 1024 * 1024:
        user_id = message.from_user.id
        local_ip = "192.168.0.108"
        web_url = f"http://{local_ip}:8080/upload?user_id={user_id}"
        await message.answer(
            f"⚠️ <b>Видео превышает лимит Telegram ({size_mb} МБ > 2 ГБ)!</b>\n\n"
            "Сам Telegram не пропускает файлы больше 2 ГБ через чат.\n\n"
            "💡 <b>Загрузите его через нашу быструю веб-страницу (до 10 ГБ):</b>\n"
            f"👉 <a href=\"{web_url}\"><b>{web_url}</b></a>\n\n"
            "Там есть шкала с примерным временем в скобочках!",
            parse_mode="HTML"
        )
        return

    est_sec = max(3, int(file_size / (2.0 * 1024 * 1024)))
    if est_sec > 60:
        est_str = f"~{est_sec // 60} мин {est_sec % 60} сек"
    else:
        est_str = f"~{est_sec} сек"

    status_msg = await message.answer(
        f"⏳ <b>Начинаю загрузку видео ({size_mb} МБ)...</b>\n"
        f"Примерное время скачивания: <b>({est_str})</b>",
        parse_mode="HTML"
    )

    user_id = message.from_user.id
    file_ext = Path(document.file_name).suffix if hasattr(document, "file_name") and document.file_name else ".mp4"
    input_path = TEMP_DIR / f"user_{user_id}_input{file_ext}"

    async def update_status(text: str):
        try:
            await status_msg.edit_text(text, parse_mode="HTML")
        except Exception:
            pass

    try:
        tg_dl = TelegramDownloader.get_instance()
        await tg_dl.download_video(
            chat_id=message.chat.id,
            message_id=message.message_id,
            output_path=input_path,
            status_update_fn=update_status
        )

        session = get_session(user_id)
        session["input_video"] = input_path

        ref_status = f"\n🔗 <i>Прикреплен референс:</i> <code>{session['reference_url']}</code>" if session.get("reference_url") else ""

        await status_msg.edit_text(
            f"✅ <b>Видео успешно получено ({size_mb} МБ)!</b>{ref_status}\n\n"
            f"Текущий режим: <b>{MODE_NAMES.get(session['mode'], '⚡ Эдит')}</b>\n"
            "Нажмите <b>«🚀 Запустить монтаж»</b> или настройте параметры:",
            reply_markup=get_process_keyboard(
                mode=session["mode"],
                has_custom_music=session.get("custom_music_path") is not None,
                use_ai_music=session.get("use_ai_music", True),
                add_sfx=session.get("add_sfx", True)
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Ошибка скачивания видео: {e}\n"
            "Попробуйте отправить файл еще раз.",
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
                f"Режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n"
                "Нажмите запуск или настройте параметры:",
                reply_markup=get_process_keyboard(
                    mode=session["mode"],
                    has_custom_music=session.get("custom_music_path") is not None,
                    use_ai_music=session.get("use_ai_music", True),
                    add_sfx=session.get("add_sfx", True)
                ),
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
                reply_markup=get_process_keyboard(
                    mode=session["mode"],
                    has_custom_music=session.get("custom_music_path") is not None,
                    use_ai_music=session.get("use_ai_music", True),
                    add_sfx=session.get("add_sfx", True)
                ),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                f"🔗 <b>Референс стиля принят:</b> <code>{url}</code>\n\n"
                f"Режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n"
                "👉 Теперь отправьте ваше исходное видео файлом прямо в чат!",
                reply_markup=get_mode_selected_keyboard(session["mode"]),
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
                reply_markup=get_process_keyboard(
                    mode=session["mode"],
                    has_custom_music=session.get("custom_music_path") is not None,
                    use_ai_music=session.get("use_ai_music", True),
                    add_sfx=session.get("add_sfx", True)
                ),
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
        text_lower = text.lower()
        if "эдит" in text_lower or "shorts" in text_lower:
            session["mode"] = "edit_tiktok"
        elif "ютуб" in text_lower or "youtube" in text_lower or "длинн" in text_lower:
            session["mode"] = "youtube_long"
        elif "чистк" in text_lower or "убрать паузы" in text_lower or "тишин" in text_lower:
            session["mode"] = "clean_silence"

        session["prompt"] = text

        if session.get("input_video"):
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n"
                f"Режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n"
                "Нажмите кнопку ниже для запуска:",
                reply_markup=get_process_keyboard(
                    mode=session["mode"],
                    has_custom_music=session.get("custom_music_path") is not None,
                    use_ai_music=session.get("use_ai_music", True),
                    add_sfx=session.get("add_sfx", True)
                ),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"📝 <b>Пожелания приняты:</b> <i>{text}</i>\n"
                f"Режим: <b>{MODE_NAMES.get(session['mode'])}</b>\n\n"
                "👉 Теперь отправьте исходное видео прямо в чат!",
                reply_markup=get_mode_selected_keyboard(session["mode"]),
                parse_mode="HTML"
            )

@router.callback_query(F.data == "start_render")
async def process_video(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer("Запускаю монтаж...")
    
    user_id = callback.from_user.id
    session = get_session(user_id)

    if not session.get("input_video"):
        await callback.message.answer("⚠️ Сначала отправьте исходное видео в чат.")
        return

    input_video = session["input_video"]
    ref_url = session.get("reference_url")
    mode = session.get("mode", "edit_tiktok")
    custom_music = session.get("custom_music_path")
    use_ai_music = session.get("use_ai_music", True)
    add_sfx = session.get("add_sfx", True)
    prompt = session.get("prompt")
    
    status_msg = await callback.message.edit_text("🔍 <b>Шаг 1/3:</b> Анализирую структуру речи и пауз...", parse_mode="HTML")
    
    try:
        pace_info = None
        if ref_url:
            await status_msg.edit_text("📥 <b>Шаг 1/3:</b> Скачиваю и анализирую видео-референс...", parse_mode="HTML")
            try:
                ref_path = await VideoDownloader.download_reference(ref_url, f"ref_{user_id}.mp4")
                pace_info = await VideoAnalyzer.analyze_cuts(ref_path)
            except Exception as e:
                await callback.message.answer(f"⚠️ Не удалось распарсить референс ({e}), использую стандартный темп.")

        await status_msg.edit_text("✂️ <b>Шаг 2/3:</b> Нахожу паузы и неловкие заминки...", parse_mode="HTML")
        silences = await AudioAnalyzer.detect_silence(input_video, mode=mode)

        if custom_music:
            m_info = "Пользовательский трек 🎧"
        elif use_ai_music and mode != "clean_silence":
            sel_track = MusicSelector.ai_select_track(prompt, mode)
            m_info = f"AI-подбор ({sel_track.stem}) 🤖"
        else:
            m_info = "Без музыки"

        await status_msg.edit_text(
            f"🎬 <b>Шаг 3/3:</b> Монтирую ролик...\n"
            f"• Режим: <b>{MODE_NAMES.get(mode)}</b>\n"
            f"• Найдено пауз: <b>{len(silences)}</b>\n"
            f"• Музыка: <b>{m_info}</b>\n"
            f"• Whoosh-переходы: <b>{'Вкл' if add_sfx and mode == 'edit_tiktok' else 'Выкл'}</b>\n\n"
            f"Идет рендеринг через FFmpeg...",
            parse_mode="HTML"
        )
        
        output_name = f"result_{user_id}.mp4"
        result_path = await VideoProcessor.cut_silences_and_render(
            input_video=input_video,
            silences=silences,
            output_name=output_name,
            mode=mode,
            custom_music_path=custom_music,
            use_ai_music=use_ai_music,
            prompt=prompt,
            add_sfx_whoosh=add_sfx
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
        
        caption = (
            "✨ <b>Ваше видео готово!</b>\n\n"
            f"• Режим: <b>{MODE_NAMES.get(mode)}</b>\n"
            f"• Вырезано немых пауз: <b>{len(silences)}</b>\n"
            f"• Музыка: <b>{m_info}</b>\n\n"
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
