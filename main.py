import sys
import subprocess
import os
import re
import time
import sqlite3
import shutil
import platform
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- RENDER PORT TEKSHIRUVI UCHUN DUMMY SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# Veb-serverni alohida oqimda (thread) ishga tushiramiz
threading.Thread(target=run_health_check_server, daemon=True).start()

# --- SIZNING MAVJUD KODINGIZ SHUYERDAN DVOAM ETADI ---
# import sys, subprocess, os...

# --- 1. AVTOMATIK O'RNATISH TIZIMI ---

def install_system_requirements():
    os_name = platform.system()
    
    # FFmpeg tekshiruvi
    if not shutil.which("ffmpeg"):
        print("📦 FFmpeg topilmadi. O'rnatish boshlandi...")
        if os_name == "Linux":
            print("Linux tizimi aniqlandi. (Agar parol so'rasa, kompyuter parolini kiriting)")
            subprocess.run(["sudo", "apt-get", "update"])
            subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
        elif os_name == "Windows":
            print("Windows tizimi aniqlandi. Winget orqali o'rnatilmoqda...")
            subprocess.run(["winget", "install", "ffmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"])
        else:
            print(f"⚠️ {os_name} tizimida FFmpeg ni avtomatik o'rnatib bo'lmadi. Qo'lda o'rnating.")

    # Node.js tekshiruvi
    if not shutil.which("node"):
        print("📦 Node.js topilmadi. O'rnatish boshlandi...")
        if os_name == "Linux":
            subprocess.run(["sudo", "apt-get", "install", "-y", "nodejs"])
        elif os_name == "Windows":
            subprocess.run(["winget", "install", "OpenJS.NodeJS", "-e", "--accept-source-agreements", "--accept-package-agreements"])
        else:
            print(f"⚠️ {os_name} tizimida Node.js ni avtomatik o'rnatib bo'lmadi. Qo'lda o'rnating.")

def install_python_packages():
    required_packages = {
        'pyTelegramBotAPI': 'telebot',
        'yt-dlp': 'yt_dlp'
    }
    
    for package, import_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"📦 '{package}' kutubxonasi topilmadi. O'rnatilmoqda...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ '{package}' muvaffaqiyatli o'rnatildi!\n")

# Dastur ishlashidan oldin hamma narsani tekshirish va o'rnatish
print("🔍 Tizim va kutubxonalar tekshirilmoqda...")
install_system_requirements()
install_python_packages()
print("✅ Barcha kerakli dastur va kutubxonalar mavjud!\n")

# Endi xotirjam import qilishimiz mumkin
import telebot
from telebot import types
import yt_dlp

# --- SOZLAMALAR ---
BOT_TOKEN = "8737032771:AAEMhkvI4epPXb-rMK9AhOTuWy8UuSB-WG0"
ADMIN_ID = 8274938812  # O'zingizning Telegram ID raqamingizni yozing!

bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}
last_progress_update = {}

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, invite_link TEXT)''')
    conn.commit()
    conn.close()

init_db()

def db_add_user(user_id, first_name, username):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, first_name, username))
    conn.commit()
    conn.close()

def db_get_users_count():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def db_get_all_users():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [u[0] for u in cursor.fetchall()]
    conn.close()
    return users

def db_add_channel(channel_id, invite_link):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (channel_id, invite_link))
    conn.commit()
    conn.close()

def db_remove_channel(channel_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def db_get_channels():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, invite_link FROM channels")
    channels = cursor.fetchall()
    conn.close()
    return channels

# --- OBUNA TEKSHIRISH ---
def check_sub(user_id):
    unsubscribed = []
    channels = db_get_channels()
    for ch_id, link in channels:
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                unsubscribed.append((ch_id, link))
        except Exception:
            unsubscribed.append((ch_id, link))
    return unsubscribed

def build_sub_keyboard(unsubscribed_channels):
    markup = types.InlineKeyboardMarkup()
    for idx, (ch_id, link) in enumerate(unsubscribed_channels, 1):
        markup.add(types.InlineKeyboardButton(f"➕ {idx}-kanalga obuna bo'lish", url=link))
    markup.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription"))
    return markup

# --- PROGRESS BAR ---
def make_progress_bar(percent):
    filled = int(percent // 10)
    bar = "#" * filled + "." * (10 - filled)
    return f"[{bar}]"

def progress_hook(d, status_msg):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            percent = (downloaded / total) * 100
            now = time.time()
            msg_id = status_msg.message_id
            if now - last_progress_update.get(msg_id, 0) > 3.0:
                last_progress_update[msg_id] = now
                text = f"⏳ Yuklanmoqda...\nProgress: [ {int(percent)}% ]\n{make_progress_bar(percent)}"
                try:
                    bot.edit_message_text(text, status_msg.chat.id, msg_id)
                except Exception:
                    pass

# --- /START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    db_add_user(user_id, message.from_user.first_name, message.from_user.username)

    unsub = check_sub(user_id)
    if unsub:
        bot.send_message(user_id, "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=build_sub_keyboard(unsub))
    else:
        send_welcome_message(user_id, message.from_user.first_name)

def send_welcome_message(user_id, first_name):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📹 Video qanday olinadi?", callback_data="how_to_use"))
    bot.send_message(user_id, f"Assalomu alaykum, {first_name}!\n\nID: `{user_id}`\n\n📥 Link yuboring yoki qo'shiq nomini yozing!", parse_mode="Markdown", reply_markup=markup)

# --- ADMIN PANEL (/admin) ---
@bot.message_handler(commands=['admin'])
def handle_admin(message):
    if message.from_user.id != ADMIN_ID:
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📊 Statistika", callback_data="admin_stat"),
               types.InlineKeyboardButton("📢 Reklama", callback_data="admin_bc"))
    markup.add(types.InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_ch"),
               types.InlineKeyboardButton("🗑 Kanal o'chirish", callback_data="admin_del_ch"))
    markup.add(types.InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data="admin_list_ch"))

    bot.send_message(message.chat.id, "🛠 **Admin paneli:**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_") or call.data.startswith("delch_"))
def callback_admin_actions(call):
    if call.from_user.id != ADMIN_ID:
        return

    chat_id = call.message.chat.id
    action = call.data

    if action == "admin_stat":
        bot.send_message(chat_id, f"📊 **Foydalanuvchilar soni:** {db_get_users_count()} ta")

    elif action == "admin_bc":
        user_states[chat_id] = "WAITING_BROADCAST"
        bot.send_message(chat_id, "📢 Barchaga yuboriladigan reklama xabarini yuboring (Matn, rasm yoki video):")

    elif action == "admin_add_ch":
        user_states[chat_id] = "WAITING_CHANNEL_DATA"
        bot.send_message(chat_id, "➕ Kanal ID si va Havolasini quyidagi shaklda yuboring:\n`@username https://t.me/link`", parse_mode="Markdown")

    elif action == "admin_list_ch":
        channels = db_get_channels()
        if not channels:
            bot.send_message(chat_id, "📋 Kanallar yo'q.")
        else:
            msg = "📋 **Majburiy kanallar:**\n\n"
            for ch_id, link in channels:
                msg += f"• `{ch_id}` - {link}\n"
            bot.send_message(chat_id, msg, parse_mode="Markdown")

    elif action == "admin_del_ch":
        channels = db_get_channels()
        if not channels:
            bot.send_message(chat_id, "O'chirish uchun kanallar yo'q.")
            return
        markup = types.InlineKeyboardMarkup()
        for ch_id, link in channels:
            markup.add(types.InlineKeyboardButton(f" ❌ {ch_id}", callback_data=f"delch_{ch_id}"))
        bot.send_message(chat_id, "🗑 O'chirmoqchi bo'lgan kanalingizni tanlang:", reply_markup=markup)

    elif action.startswith("delch_"):
        ch_id = action.replace("delch_", "")
        db_remove_channel(ch_id)
        bot.answer_callback_query(call.id, "Kanal o'chirildi!", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data in ["check_subscription", "how_to_use"])
def callback_basics(call):
    if call.data == "check_subscription":
        unsub = check_sub(call.from_user.id)
        if unsub:
            bot.answer_callback_query(call.id, "❌ Hali obuna bo'lmadingiz!", show_alert=True)
        else:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            send_welcome_message(call.from_user.id, call.from_user.first_name)
    elif call.data == "how_to_use":
        bot.send_message(call.message.chat.id, "📹 YouTube, TikTok yoki Instagram havolasini yuboring va sifatni tanlang.")

# --- BARCHA XABARLARNI QABUL QILISH ---
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'video'])
ydl_opts = {
    'extract_flat': True, 
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios']
        }
    }
}


    # ADMIN HOLATLARI
    state = user_states.get(chat_id)
    if state == "WAITING_BROADCAST" and user_id == ADMIN_ID:
        user_states[chat_id] = None
        users = db_get_all_users()
        bot.send_message(chat_id, "🚀 Reklama yuborilmoqda...")
        sent = 0
        for u_id in users:
            try:
                bot.copy_message(u_id, chat_id, message.message_id)
                sent += 1
                time.sleep(0.05)
            except Exception:
                pass
        bot.send_message(chat_id, f"✅ Reklama {sent} ta odamga yetib bordi.")
        return

    elif state == "WAITING_CHANNEL_DATA" and user_id == ADMIN_ID:
        user_states[chat_id] = None
        try:
            ch_id, link = text.split()
            db_add_channel(ch_id, link)
            bot.send_message(chat_id, f"✅ Kanal qo'shildi: {ch_id}")
        except Exception:
            bot.send_message(chat_id, "❌ Format xato! Bunday yuboring: `@username https://t.me/link`")
        return

    # MAJBURIY OBUNA TEKSHIRUVI
    if check_sub(user_id) and user_id != ADMIN_ID:
        bot.send_message(user_id, "⚠️ Oldin obuna bo'ling!", reply_markup=build_sub_keyboard(check_sub(user_id)))
        return

    url_pattern = re.compile(r'https?://[^\s]+')
    if url_pattern.match(text):
        # YUKLASH UCHUN HAVOLA
        user_states[f"url_{user_id}"] = text
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(types.InlineKeyboardButton("📹 720p", callback_data="dl_720p"),
                   types.InlineKeyboardButton("📹 360p", callback_data="dl_360p"),
                   types.InlineKeyboardButton("🎵 MP3", callback_data="dl_mp3"))
        bot.send_message(chat_id, "🎬 Formatni tanlang:", reply_markup=markup)
    elif text:
        # MUSIQA QIDIRISH
        status_msg = bot.send_message(chat_id, "🔍 Izlanmoqda...")
        ydl_opts = {'extract_flat': True, 'quiet': True, 'js_runtimes': ['node']}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(f"ytsearch10:{text}", download=False)
                entries = results.get('entries', [])

                if not entries:
                    bot.edit_message_text("❌ Hech narsa topilmadi.", chat_id, status_msg.message_id)
                    return

                markup = types.InlineKeyboardMarkup()
                for entry in entries:
                    title = entry.get('title')[:35]
                    v_id = entry.get('id')
                    markup.add(types.InlineKeyboardButton(f"🎵 {title}", callback_data=f"play_{v_id}"))

                bot.delete_message(chat_id, status_msg.message_id)
                bot.send_message(chat_id, "🔎 Qidiruv natijalari:", reply_markup=markup)
        except Exception:
            bot.edit_message_text("❌ Qidiruvda xatolik yuz berdi.", chat_id, status_msg.message_id)

# --- YUKLAB OLISH (CALLBACK) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("dl_") or call.data.startswith("play_"))
def callback_download_media(call):
base_opts = {
    'outtmpl': f'{out_filename}.%(ext)s',
    'progress_hooks': [lambda d: progress_hook(d, status_msg)],
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios']
        }
    }
}


    if data.startswith("play_"):
        url = f"https://www.youtube.com/watch?v={data.replace('play_', '')}"
        fmt = "mp3"
    else:
        fmt = data.replace("dl_", "")
        url = user_states.get(f"url_{user_id}")

    if not url:
        bot.send_message(chat_id, "❌ Havola topilmadi, iltimos qaytadan yuboring.")
        return

    bot.delete_message(chat_id, call.message.message_id)
    status_msg = bot.send_message(chat_id, "⏳ Yuklanmoqda...\nProgress: [ 0% ]\n[..........]")

    out_filename = f"downloads/{user_id}_{int(time.time())}"
    os.makedirs("downloads", exist_ok=True)

    base_opts = {
        'outtmpl': f'{out_filename}.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, status_msg)],
        'quiet': True,
        'js_runtimes': ['node'] # Node.js ulanishi
    }

    if fmt == "mp3":
        ydl_opts = {
            **base_opts,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192'
            }]
        }
    elif fmt == "720p":
        ydl_opts = {**base_opts, 'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'}
    else:
        ydl_opts = {**base_opts, 'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if fmt == "mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"

        bot.delete_message(chat_id, status_msg.message_id)

        with open(filename, 'rb') as file:
            if fmt == "mp3":
                bot.send_audio(chat_id, file, caption="🤖 Bot orqali yuklab olindi")
            else:
                bot.send_video(chat_id, file, caption="🤖 Bot orqali yuklab olindi")

        if os.path.exists(filename):
            os.remove(filename)

    except Exception as e:
        try:
            bot.edit_message_text("❌ Yuklab olishda xatolik yuz berdi.", chat_id, status_msg.message_id)
        except Exception:
            pass

if __name__ == '__main__':
    print("🤖 Bot muvaffaqiyatli ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
