# ai-editor from softer_052 🎬

AI-ассистент и студия автоматического монтажа видео под Shorts, Reels и TikTok.

## Возможности
- ✂️ **Автоматическая вырезка пауз и вздохов** (Silencedetect).
- 🔍 **Динамический зум (Punch-in)** на спикере для удержания внимания.
- 🔗 **Анализ референса по ссылке** (YouTube Shorts / Reels / TikTok с помощью yt-dlp и PySceneDetect).
- 🤖 **Telegram-интерфейс**: отправка исходников, настройка параметров и получение готового видео прямо в чат.
- 🌐 **Готов к развертыванию** в облаке или локальном сервере.

## Установка и запуск

### 1. Требования
- Python 3.10+
- FFmpeg (установленный в системе)

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка
Создайте файл `.env` на основе `.env.example`:
```env
BOT_TOKEN=9032657932:AAGRlPMK3P7kVpkMKJMk_F-j8Grw2VPEKKY
FFMPEG_PATH=ffmpeg
TEMP_DIR=temp
```

### 4. Запуск
```bash
python main.py
```
