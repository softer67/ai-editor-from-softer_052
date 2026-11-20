from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="⚡ Быстрый Reels/Shorts (зумы + вырезка пауз)", callback_data="preset_reels"),
        ],
        [
            InlineKeyboardButton(text="🎬 По референсу (пришлите ссылку)", callback_data="preset_reference"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки звука и монтажа", callback_data="settings"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_process_keyboard(add_sfx: bool = True, add_music: bool = False) -> InlineKeyboardMarkup:
    sfx_icon = "ВКЛ ✅" if add_sfx else "ВЫКЛ ❌"
    music_icon = "ВКЛ ✅" if add_music else "ВЫКЛ ❌"
    
    keyboard = [
        [
            InlineKeyboardButton(text="🚀 Запустить монтаж", callback_data="start_render")
        ],
        [
            InlineKeyboardButton(text=f"🔊 SFX Whoosh: {sfx_icon}", callback_data="toggle_sfx"),
            InlineKeyboardButton(text=f"🎵 Музыка: {music_icon}", callback_data="toggle_music")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_settings_keyboard(add_sfx: bool = True, add_music: bool = False) -> InlineKeyboardMarkup:
    sfx_icon = "ВКЛ ✅" if add_sfx else "ВЫКЛ ❌"
    music_icon = "ВКЛ ✅" if add_music else "ВЫКЛ ❌"

    keyboard = [
        [
            InlineKeyboardButton(text=f"🔊 Звук перехода Whoosh: {sfx_icon}", callback_data="toggle_sfx")
        ],
        [
            InlineKeyboardButton(text=f"🎵 Фоновая музыка (Lo-Fi): {music_icon}", callback_data="toggle_music")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
