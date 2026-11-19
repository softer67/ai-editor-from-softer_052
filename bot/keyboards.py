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
            InlineKeyboardButton(text="⚙️ Настройки монтажа", callback_data="settings"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_process_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="🚀 Запустить монтаж", callback_data="start_render")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
