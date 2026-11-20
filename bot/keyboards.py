from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

MODE_NAMES = {
    "edit_tiktok": "⚡ Эдит (Shorts/TikTok)",
    "youtube_long": "📺 YouTube (Длинное)",
    "clean_silence": "✂️ Чистка пауз (Без зумов)"
}

def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="⚡ Клиповый Эдит / Shorts", callback_data="mode_edit_tiktok"),
        ],
        [
            InlineKeyboardButton(text="📺 Длинное видео для YouTube", callback_data="mode_youtube_long"),
        ],
        [
            InlineKeyboardButton(text="✂️ Просто убрать паузы и тишину", callback_data="mode_clean_silence")
        ],
        [
            InlineKeyboardButton(text="⚙️ Музыка и звуки", callback_data="music_settings"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_mode_selected_keyboard(current_mode: str = "edit_tiktok") -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🔄 Сменить режим монтажа", callback_data="change_mode")
        ],
        [
            InlineKeyboardButton(text="🎵 Музыка и звуки", callback_data="music_settings"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_process_keyboard(
    mode: str = "edit_tiktok",
    has_custom_music: bool = False,
    use_ai_music: bool = True,
    add_sfx: bool = True
) -> InlineKeyboardMarkup:
    mode_label = MODE_NAMES.get(mode, "⚡ Эдит")
    
    if has_custom_music:
        music_status = "Своя 🎧"
    elif use_ai_music:
        music_status = "AI-подбор 🤖"
    else:
        music_status = "Выкл ❌"

    sfx_status = "ВКЛ ✅" if add_sfx else "ВЫКЛ ❌"

    keyboard = [
        [
            InlineKeyboardButton(text="🚀 Запустить монтаж", callback_data="start_render")
        ],
        [
            InlineKeyboardButton(text=f"Режим: {mode_label} (сменить)", callback_data="change_mode")
        ],
        [
            InlineKeyboardButton(text=f"🎵 Музыка: {music_status}", callback_data="music_settings"),
            InlineKeyboardButton(text=f"🔊 Whoosh: {sfx_status}", callback_data="toggle_sfx")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_mode_selection_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="⚡ Клиповый Эдит (Shorts/TikTok)", callback_data="mode_edit_tiktok")
        ],
        [
            InlineKeyboardButton(text="📺 Длинное для YouTube (16:9)", callback_data="mode_youtube_long")
        ],
        [
            InlineKeyboardButton(text="✂️ Чистка пауз (без зумов и музыки)", callback_data="mode_clean_silence")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_process")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_music_settings_keyboard(has_custom_music: bool = False, use_ai_music: bool = True) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🤖 AI-подбор (нейросеть выберет сама)", callback_data="music_ai")
        ],
        [
            InlineKeyboardButton(text="🔥 Phonk / Драйв (Gaming/GTA)", callback_data="music_phonk"),
            InlineKeyboardButton(text="☕ Lo-Fi / Chill", callback_data="music_lofi")
        ],
        [
            InlineKeyboardButton(text="⚡ Upbeat (Энергичный)", callback_data="music_upbeat"),
            InlineKeyboardButton(text="❌ Без музыки", callback_data="music_off")
        ],
        [
            InlineKeyboardButton(text="📁 Как загрузить свою музыку?", callback_data="music_how_to_upload")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_process")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
