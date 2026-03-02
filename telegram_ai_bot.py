"""
🤖 Telegram AI Asistan Botu
"""

import os
import time
import logging
from collections import defaultdict
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import anthropic

# ============================================================
# ⚙️ YAPILANDIRMA
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "BURAYA_BOT_TOKEN_YAZIN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "BURAYA_API_KEY_YAZIN")

BOT_NAME = "AI Asistan"
BOT_USERNAME = ""  # Botunuzun @kullanıcı_adı

CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024
MAX_MESSAGES_PER_MINUTE = 5
COOLDOWN_SECONDS = 60
MAX_HISTORY_PER_USER = 10
ADMIN_IDS = []

SYSTEM_PROMPT = """Sen bir Telegram grubunda görev yapan yardımsever, bilgili ve samimi bir AI asistansın.

Görevlerin:
- Kullanıcıların sorularını Türkçe olarak yanıtlamak
- Her konuda bilgi ve fikir vermek (teknoloji, bilim, sağlık, eğitim, günlük yaşam, vb.)
- Nazik, saygılı ve yapıcı olmak
- Gerektiğinde farklı bakış açıları sunmak
- Karmaşık konuları basit ve anlaşılır şekilde açıklamak

Kuralların:
- Yasadışı aktivitelere yardım etme
- Nefret söylemi veya ayrımcılık yapma
- Kişisel tıbbi veya hukuki tavsiye verirken dikkatli ol, profesyonele yönlendir
- Yanıtlarını kısa ve öz tut (Telegram mesajları için uygun uzunlukta)
- Emin olmadığın konularda bunu belirt
"""

# ============================================================
# 🔧 TEKNİK KOD
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
conversation_history = defaultdict(list)
user_message_times = defaultdict(list)
stats = {"total_messages": 0, "total_users": set(), "start_time": datetime.now()}


def check_rate_limit(user_id):
    now = time.time()
    user_message_times[user_id] = [
        t for t in user_message_times[user_id] if now - t < COOLDOWN_SECONDS
    ]
    if len(user_message_times[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    user_message_times[user_id].append(now)
    return True


def get_ai_response(user_id, user_message):
    conversation_history[user_id].append({"role": "user", "content": user_message})
    if len(conversation_history[user_id]) > MAX_HISTORY_PER_USER * 2:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_PER_USER * 2:]

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id],
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
        return assistant_message
    except anthropic.RateLimitError:
        return "⏳ Şu anda çok fazla istek var, lütfen birkaç saniye bekleyin."
    except anthropic.APIError as e:
        logger.error(f"Anthropic API hatası: {e}")
        return "❌ Bir hata oluştu. Lütfen tekrar deneyin."
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {e}")
        return "❌ Bir hata oluştu. Lütfen tekrar deneyin."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        f"👋 Merhaba! Ben {BOT_NAME}.\n\n"
        "Size her konuda yardımcı olabilirim:\n"
        "💡 Bilgi ve tavsiye\n"
        "📚 Eğitim ve öğrenme\n"
        "💻 Teknoloji soruları\n"
        "🤔 Fikir ve öneri\n\n"
        "Sadece mesaj yazın, hemen yanıtlayacağım.\n\n"
        "/help - Yardım | /reset - Sıfırla | /about - Hakkında"
    )
    await update.message.reply_text(welcome)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Nasıl Kullanılır?\n\n"
        "🔹 Bana direkt mesaj yazabilirsiniz\n"
        "🔹 Grupta @mention ile sorabilirsiniz\n"
        "🔹 Her konuda soru sorabilirsiniz\n\n"
        "Komutlar:\n"
        "/start - Botu başlat\n"
        "/help - Yardım menüsü\n"
        "/reset - Sohbet geçmişini sıfırla\n"
        "/about - Bot hakkında bilgi"
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history[update.effective_user.id] = []
    await update.message.reply_text("🔄 Sohbet geçmişiniz sıfırlandı!")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - stats["start_time"]
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    await update.message.reply_text(
        f"🤖 {BOT_NAME}\n\n"
        f"📊 Toplam mesaj: {stats['total_messages']}\n"
        f"👥 Toplam kullanıcı: {len(stats['total_users'])}\n"
        f"⏱ Çalışma süresi: {hours}s {minutes}dk\n\n"
        "Claude AI tarafından desteklenmektedir."
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return
    uptime = datetime.now() - stats["start_time"]
    active = len([u for u, h in conversation_history.items() if len(h) > 0])
    await update.message.reply_text(
        f"📊 Bot İstatistikleri\n\n"
        f"Toplam mesaj: {stats['total_messages']}\n"
        f"Toplam kullanıcı: {len(stats['total_users'])}\n"
        f"Aktif sohbet: {active}\n"
        f"Çalışma süresi: {uptime}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Kullanıcı"
    message_text = update.message.text.strip()
    chat_type = update.message.chat.type

    if chat_type in ("group", "supergroup"):
        bot_mentioned = False
        if BOT_USERNAME and f"@{BOT_USERNAME}" in message_text:
            message_text = message_text.replace(f"@{BOT_USERNAME}", "").strip()
            bot_mentioned = True
        if (
            update.message.reply_to_message
            and update.message.reply_to_message.from_user
            and update.message.reply_to_message.from_user.id == context.bot.id
        ):
            bot_mentioned = True
        if not bot_mentioned:
            return

    if not message_text:
        return

    if not check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok hızlı mesaj gönderiyorsunuz. Lütfen biraz bekleyin.")
        return

    stats["total_messages"] += 1
    stats["total_users"].add(user_id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    logger.info(f"[{user_name}] ({user_id}): {message_text[:100]}")
    response = get_ai_response(user_id, message_text)

    if len(response) > 4000:
        for i in range(0, len(response), 4000):
            await update.message.reply_text(response[i:i + 4000])
    else:
        await update.message.reply_text(response)


async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Hata: {context.error}")


def main():
    print(f"🤖 {BOT_NAME} başlatılıyor...")

    if TELEGRAM_BOT_TOKEN == "BURAYA_BOT_TOKEN_YAZIN":
        print("❌ HATA: TELEGRAM_BOT_TOKEN ayarlanmamış!")
        return
    if ANTHROPIC_API_KEY == "BURAYA_API_KEY_YAZIN":
        print("❌ HATA: ANTHROPIC_API_KEY ayarlanmamış!")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    print(f"✅ {BOT_NAME} çalışıyor!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
