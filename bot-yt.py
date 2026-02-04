# bot-yt.py
# Downloads YouTube audio → converts to MP3 → sends via Telegram
# Supports searches in all languages
# Personal/test use only

import os
import re
import logging
import asyncio
from datetime import timedelta
from urllib.parse import quote

# Windows asyncio compatibility fix
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

import yt_dlp

# ────────────────────────────────────────────────
BOT_TOKEN = "8144804132:AAEf-LWIt_IPuXekmztV4OJzx1G2HmIfpIk"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)



logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# yt-dlp options for audio only → mp3
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'continuedl': True,
    'noplaylist': True,
    'windowsfilenames': True,
    'ignoreerrors': True,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
}


def clean_filename(title: str) -> str:
    """Clean filename to be safe for all supported languages"""
    # Keep Khmer, Chinese, English characters and basic punctuation
    return re.sub(r'[^\w\s\-\(\)\[\]\.,\u1780-\u17FF\u4e00-\u9fff]', '', title, flags=re.UNICODE).strip()[:100]


def format_duration(seconds: int) -> str:
    if not seconds:
        return ""
    td = timedelta(seconds=seconds)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    welcome_text = """
🎵 *Music Downloader Bot*

Supports searches in all languages! 🇺🇸🇰🇭🇨🇳🌍

Send me a song name, artist, or lyrics in any language and I'll find it on YouTube!

👇 Just send text to start searching
    """

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown"
    )





async def search_and_show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search queries in all languages"""
    if not update.message or not update.message.text:
        return

    query = update.message.text.strip()
    if len(query) < 2:
        await update.message.reply_text("❌ Please type at least 2 characters.")
        return

    searching_msg = await update.message.reply_text(
        f"🔍 *Searching for:* `{query}`\n⏳ Please wait...",
        parse_mode="Markdown"
    )

    try:
        # Enhanced search with language preference
        ydl_search_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        }
        
        # Encode search query for URL safety, add language hints for better results
        if any('\u4e00' <= char <= '\u9fff' for char in query):  # Chinese characters
            search_query = quote(query + " 歌曲")
        else:
            search_query = quote(query)

        with yt_dlp.YoutubeDL(ydl_search_opts) as ydl:
            search_info = ydl.extract_info(
                f"ytsearch15:{search_query}",
                download=False
            )

        entries = search_info.get('entries', [])
        if not entries:
            await searching_msg.edit_text("❌ No results found.")
            return

        context.user_data['search_results'] = []

        text = "🎵 *Search Results*\n\n"
        buttons = []
        valid_count = 0

        for entry in entries:
            if not entry or entry.get('age_limit', 0) >= 18:
                continue

            video_id = entry.get('id')
            title = entry.get('title', 'Unknown')
            channel = entry.get('uploader', 'Unknown')
            duration = format_duration(entry.get('duration'))

            if not video_id:
                continue

            context.user_data['search_results'].append({
                'id': video_id,
                'title': title,
                'channel': channel,
                'duration': duration,
                'url': f"https://youtu.be/{video_id}"
            })

            valid_count += 1

            text += (
                f"*{valid_count}. {title}*\n"
                f"_{channel} • {duration if duration else 'Unknown duration'}_\n\n"
            )

            button_text = f"🎧 {valid_count}. {title[:35]}{'…' if len(title) > 35 else ''}"
            if duration:
                button_text += f" ({duration})"

            buttons.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"dl_{valid_count - 1}"
                )
            ])

            if valid_count >= 10:
                break

        if valid_count == 0:
            await searching_msg.edit_text(
                "❌ Found videos but all are age-restricted or unavailable."
            )
            return

        text += f"👇 Found {valid_count} tracks - Tap to download"

        await searching_msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.exception(f"Search error: {e}")
        await searching_msg.edit_text("❌ An error occurred during search.\nPlease try again later.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle download button clicks"""
    query = update.callback_query
    await query.answer()

    index = int(query.data.split("_")[1])
    video = context.user_data['search_results'][index]

    video_id = video['id']
    title = video['title']
    channel = video['channel']
    url = video['url']

    mp3_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")

    # Check if already downloaded
    if os.path.exists(mp3_path):
        await send_audio(query.message, mp3_path, title, channel, context)
        return

    msg = await query.message.reply_text(
        f"⏬ *Downloading:* `{title}`",
        parse_mode="Markdown"
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await send_audio(query.message, mp3_path, title, channel, context)
        await msg.delete()

    except Exception as e:
        logger.exception(e)
        await msg.edit_text("❌ Download failed.")


async def send_audio(target_message, file_path: str, title: str, artist: str = "", context: ContextTypes.DEFAULT_TYPE = None):
    """Send MP3"""
    try:
        if not os.path.isfile(file_path):
            return

        clean_title = safe_title_filename(title)
        final_path = os.path.join(
            os.path.dirname(file_path),
            f"{clean_title}.mp3"
        )

        # Rename only if needed
        if file_path != final_path:
            try:
                os.rename(file_path, final_path)
            except FileExistsError:
                final_path = file_path  # fallback if same name exists
            except Exception as e:
                logger.error(f"Renaming error: {e}")
                final_path = file_path

        with open(final_path, "rb") as audio_file:
            await target_message.reply_audio(
                audio=audio_file,
                title=clean_title[:64],
                performer=artist[:64] if artist else None
            )

    except Exception as e:
        logger.exception(f"Send audio error: {e}")
        await target_message.reply_text("❌ Failed to send MP3.")


def safe_title_filename(title: str) -> str:
    """Make a safe filename from title (supports Khmer and Chinese)"""
    # Allow Khmer and Chinese characters along with safe English characters
    title = re.sub(r'[\\/:*?"<>|]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title[:80] if title else "audio"


async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to change language"""
    keyboard = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇰🇭 Khmer", callback_data="lang_km")],
        [InlineKeyboardButton("🇨🇳 Chinese", callback_data="lang_zh")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🌐 *Select your preferred language:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Multilingual help command"""
    lang_code = context.user_data.get('language', 'en')
    
    help_texts = {
        'en': """
🤖 *How to use this bot:*

1. Start by selecting a language with /language
2. Send any song name, artist, or lyrics
3. Choose from search results
4. Download as MP3

📌 *Commands:*
/start - Start the bot
/language - Change language
/help - Show this message

⚠️ *Note:* For personal use only
        """,
        'km': """
🤖 *របៀបប្រើប្រាស់ bot នេះ:*

1. ចាប់ផ្តើមដោយជ្រើសរើសភាសាជាមួយ /language
2. ផ្ញើឈ្មោះចម្រៀង អ្នកចម្រៀង ឬវិចិត្រសិល្ប៍
3. ជ្រើសរើសពីលទ្ធផលស្វែងរក
4. ទាញយកជា MP3

📌 *ពាក្យបញ្ជា:*
/start - ចាប់ផ្តើម bot
/language - ផ្លាស់ប្តូរភាសា
/help - បង្ហាញសារនេះ

⚠️ *ចំណាំ:* សម្រាប់ប្រើប្រាស់ផ្ទាល់ខ្លួនតែប៉ុណ្ណោះ
        """,
        'zh': """
🤖 *如何使用此机器人:*

1. 首先使用 /language 选择语言
2. 发送任何歌曲名称、艺术家或歌词
3. 从搜索结果中选择
4. 下载为MP3格式

📌 *命令:*
/start - 启动机器人
/language - 更改语言
/help - 显示此消息

⚠️ *注意:* 仅限个人使用
        """
    }
    
    await update.message.reply_text(
        help_texts.get(lang_code, help_texts['en']),
        parse_mode="Markdown"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_and_show_results))

    # Download callback
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^dl_"))

    print("🎵 Music Downloader Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()