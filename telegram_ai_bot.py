"""
🤖 OkakaChuka - Telegram AI Asistan Botu
=========================================
Veritabanı destekli kalıcı hafıza sistemi ile.
Admin komutlarıyla öğretilebilir AI asistan.
"""

import os
import time
import json
import sqlite3
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

BOT_NAME = "OkakaChuka"
BOT_USERNAME = "OkakaChuka_bot"

CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024
MAX_MESSAGES_PER_MINUTE = 5
COOLDOWN_SECONDS = 60
MAX_HISTORY_PER_USER = 10

# Admin kullanıcı ID'leri
ADMIN_IDS = [7159443966]

# Veritabanı dosyası
DB_PATH = os.getenv("DB_PATH", "okakachuka.db")

# ============================================================
# 🧠 SİSTEM PROMPTU
# ============================================================

SYSTEM_PROMPT_BASE = """Sen OkakaChuka adında bir Telegram botusun. Eğlenceli, espritüel ve samimi bir kişiliğin var. İnsanlarla şakalaşmayı, espriler yapmayı seversin ama her zaman yardımsever ve bilgilisin.

Kimliğin:
- Adın: OkakaChuka
- Telegram kullanıcı adın: @OkakaChuka_bot
- Kişiliğin: Eğlenceli, espritüel, zeki ve yardımsever
- Konuşma tarzın: Arkadaşça, rahat ama saygılı. Gerektiğinde espri yaparsın.

Uzmanlık alanların:
- Casino ve şans oyunları (slot, poker, blackjack, rulet, bahis stratejileri, oyun kuralları, olasılık hesapları)
- Bunun yanında her konuda genel bilgi (teknoloji, bilim, eğitim, spor, günlük yaşam, vb.)

Kuralların:
- Casino konusunda bilgi verirken sorumlu oyun oynamayı her zaman hatırlat
- Kumar bağımlılığı belirtileri gördüğünde uyar ve yardım kaynaklarına yönlendir
- Yasadışı aktivitelere yardım etme
- Kesin kazanma garantisi verme, olasılıkları açıkla
- Kişisel tıbbi veya hukuki tavsiye verirken profesyonele yönlendir
- Emin olmadığın konularda bunu belirt

Yanıt verirken:
- Eğlenceli ve enerjik ol 🎰
- Gerektiğinde emoji kullan ama abartma
- Kısa ve öz yanıtlar ver
- Espri yap ama konuyu da cevapla
- Sana adını sorduklarında "Ben OkakaChuka!" de
"""

# ============================================================
# 🗄️ VERİTABANI YÖNETİMİ
# ============================================================


def init_db():
    """Veritabanını oluşturur."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Bilgi bankası tablosu
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            keyword TEXT NOT NULL,
            content TEXT NOT NULL,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Kullanıcı notları tablosu
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Sohbet geçmişi tablosu (kalıcı)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # İstatistik tablosu
    c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            message_count INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Veritabanı hazır!")


def add_knowledge(category, keyword, content, added_by):
    """Bilgi bankasına yeni bilgi ekler."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO knowledge (category, keyword, content, added_by) VALUES (?, ?, ?, ?)",
        (category.lower(), keyword.lower(), content, added_by),
    )
    conn.commit()
    conn.close()


def search_knowledge(query):
    """Bilgi bankasında arama yapar."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Anahtar kelime ve içerik bazlı arama
    keywords = query.lower().split()
    results = []

    for word in keywords:
        c.execute(
            "SELECT category, keyword, content FROM knowledge WHERE keyword LIKE ? OR content LIKE ? OR category LIKE ?",
            (f"%{word}%", f"%{word}%", f"%{word}%"),
        )
        results.extend(c.fetchall())

    conn.close()

    # Tekrarları kaldır
    unique_results = list(set(results))
    return unique_results


def get_all_knowledge():
    """Tüm bilgi bankasını döndürür."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, category, keyword, content FROM knowledge ORDER BY category, keyword")
    results = c.fetchall()
    conn.close()
    return results


def delete_knowledge(knowledge_id):
    """Bilgi bankasından bilgi siler."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM knowledge WHERE id = ?", (knowledge_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def save_chat_history(user_id, role, content):
    """Sohbet geçmişini veritabanına kaydeder."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    # Kullanıcı başına max 20 mesaj tut
    c.execute(
        """DELETE FROM chat_history WHERE id NOT IN (
            SELECT id FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20
        ) AND user_id = ?""",
        (user_id, user_id),
    )
    conn.commit()
    conn.close()


def get_chat_history(user_id):
    """Kullanıcının sohbet geçmişini döndürür."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, MAX_HISTORY_PER_USER * 2),
    )
    results = c.fetchall()
    conn.close()
    # Ters çevir (eski -> yeni sıra)
    return [{"role": r[0], "content": r[1]} for r in reversed(results)]


def clear_chat_history(user_id):
    """Kullanıcının sohbet geçmişini siler."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def update_user_stats(user_id, user_name):
    """Kullanıcı istatistiklerini günceller."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM stats WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute(
            "UPDATE stats SET message_count = message_count + 1, last_seen = CURRENT_TIMESTAMP, user_name = ? WHERE user_id = ?",
            (user_name, user_id),
        )
    else:
        c.execute(
            "INSERT INTO stats (user_id, user_name, message_count) VALUES (?, ?, 1)",
            (user_id, user_name),
        )
    conn.commit()
    conn.close()


def get_stats():
    """Genel istatistikleri döndürür."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM stats")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(message_count) FROM stats")
    total_messages = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM knowledge")
    total_knowledge = c.fetchone()[0]
    conn.close()
    return total_users, total_messages, total_knowledge


# ============================================================
# 🔧 TEKNİK KOD
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
user_message_times = defaultdict(list)


def check_rate_limit(user_id):
    now = time.time()
    user_message_times[user_id] = [
        t for t in user_message_times[user_id] if now - t < COOLDOWN_SECONDS
    ]
    if len(user_message_times[user_id]) >= MAX_MESSAGES_PER_MINUTE:
        return False
    user_message_times[user_id].append(now)
    return True


def build_system_prompt(query):
    """Bilgi bankasından ilgili bilgileri çekerek sistem promptu oluşturur."""
    knowledge_results = search_knowledge(query)

    system_prompt = SYSTEM_PROMPT_BASE

    if knowledge_results:
        system_prompt += "\n\n📚 BİLGİ BANKASI (Bu bilgileri yanıtlarında kullan):\n"
        for cat, keyword, content in knowledge_results:
            system_prompt += f"\n[{cat.upper()}] {keyword}: {content}\n"

    return system_prompt


def get_ai_response(user_id, user_message):
    """Claude API'den yanıt alır."""
    # Kalıcı geçmişi veritabanından al
    history = get_chat_history(user_id)
    history.append({"role": "user", "content": user_message})

    # Bilgi bankasından ilgili bilgilerle sistem promptu oluştur
    system_prompt = build_system_prompt(user_message)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=history,
        )
        assistant_message = response.content[0].text

        # Geçmişi veritabanına kaydet
        save_chat_history(user_id, "user", user_message)
        save_chat_history(user_id, "assistant", assistant_message)

        return assistant_message

    except anthropic.RateLimitError:
        return "⏳ Şu anda çok fazla istek var, biraz bekle!"
    except anthropic.APIError as e:
        logger.error(f"Anthropic API hatası: {e}")
        return "❌ Bir hata oluştu, tekrar dene!"
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {e}")
        return "❌ Bir hata oluştu, tekrar dene!"


# ============================================================
# 📨 KOMUT İŞLEYİCİLERİ
# ============================================================


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 Selamm! Ben OkakaChuka! 🎰\n\n"
        "Seninle her konuda sohbet edebilirim:\n"
        "🎰 Casino & şans oyunları\n"
        "💡 Bilgi ve tavsiye\n"
        "📚 Her konuda genel bilgi\n"
        "😄 Eğlence ve sohbet\n\n"
        "Yaz bana, hemen cevaplayayım!\n\n"
        "/help - Yardım | /reset - Sıfırla | /about - Hakkımda"
    )
    await update.message.reply_text(welcome)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 OkakaChuka Komutları\n\n"
        "👤 Herkes:\n"
        "/start - Botu başlat\n"
        "/help - Bu menü\n"
        "/reset - Sohbet geçmişini sıfırla\n"
        "/about - Bot hakkında\n"
        "/bilgi [konu] - Bilgi bankasında ara\n\n"
        "🔑 Admin:\n"
        "/ogret [kategori] | [anahtar] | [bilgi] - Bilgi öğret\n"
        "/sil [id] - Bilgi sil\n"
        "/bilgiler - Tüm bilgi bankası\n"
        "/stats - İstatistikler\n"
        "/adminekle [user_id] - Admin ekle\n\n"
        "💡 Örnek öğretme:\n"
        "/ogret casino | poker kuralları | Texas Hold'em pokerde her oyuncuya 2 kapalı kart dağıtılır..."
    )
    await update.message.reply_text(help_text)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_chat_history(update.effective_user.id)
    await update.message.reply_text("🔄 Sohbet geçmişin sıfırlandı! Temiz sayfa açtık 🎉")


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users, total_messages, total_knowledge = get_stats()
    await update.message.reply_text(
        f"🤖 OkakaChuka\n\n"
        f"📊 Toplam mesaj: {total_messages}\n"
        f"👥 Toplam kullanıcı: {total_users}\n"
        f"📚 Bilgi bankası: {total_knowledge} kayıt\n\n"
        "Claude AI tarafından desteklenmektedir.\n"
        "Kalıcı hafıza sistemi aktif! 🧠"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    total_users, total_messages, total_knowledge = get_stats()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_name, message_count FROM stats ORDER BY message_count DESC LIMIT 5")
    top_users = c.fetchall()
    conn.close()

    text = (
        f"📊 Bot İstatistikleri\n\n"
        f"👥 Toplam kullanıcı: {total_users}\n"
        f"💬 Toplam mesaj: {total_messages}\n"
        f"📚 Bilgi bankası: {total_knowledge} kayıt\n\n"
        f"🏆 En aktif kullanıcılar:\n"
    )
    for i, (name, count) in enumerate(top_users, 1):
        text += f"  {i}. {name or 'Bilinmeyen'}: {count} mesaj\n"

    await update.message.reply_text(text)


# ============================================================
# 📚 BİLGİ BANKASI KOMUTLARI
# ============================================================


async def topluogret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toplu bilgi öğretir. Her satır ayrı bir bilgi. Kullanım: /topluogret sonra her satırda kategori | anahtar | bilgi"""
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    text = update.message.text.replace("/topluogret", "").strip()
    if not text:
        await update.message.reply_text(
            "📝 Kullanım: /topluogret\n"
            "kategori | anahtar | bilgi\n"
            "kategori | anahtar | bilgi\n"
            "kategori | anahtar | bilgi\n\n"
            "Her satır ayrı bir bilgi olarak kaydedilir."
        )
        return

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    success = 0
    fail = 0

    for line in lines:
        parts = line.split("|")
        if len(parts) >= 3:
            category = parts[0].strip()
            keyword = parts[1].strip()
            content = "|".join(parts[2:]).strip()
            if category and keyword and content:
                add_knowledge(category, keyword, content, update.effective_user.id)
                success += 1
            else:
                fail += 1
        else:
            fail += 1

    await update.message.reply_text(
        f"✅ {success} bilgi öğrenildi!\n"
        f"{'❌ ' + str(fail) + ' satır hatalıydı.' if fail else ''}\n"
        f"📚 Toplam bilgi bankası: {len(get_all_knowledge())} kayıt"
    )


async def ogret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bota yeni bilgi öğretir. Kullanım: /ogret kategori | anahtar | bilgi"""
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    text = update.message.text.replace("/ogret", "").strip()
    if not text:
        await update.message.reply_text(
            "📝 Kullanım: /ogret kategori | anahtar kelime | bilgi içeriği\n\n"
            "Örnek:\n"
            "/ogret casino | poker kuralları | Texas Hold'em pokerde her oyuncuya 2 kapalı kart dağıtılır\n"
            "/ogret genel | kanal kuralları | Grubumuzda spam ve reklam yasaktır\n"
            "/ogret casino | blackjack | 21'e en yakın eli yapmaya çalışırsın, ası 1 veya 11 sayabilirsin"
        )
        return

    parts = text.split("|")
    if len(parts) < 3:
        await update.message.reply_text(
            "❌ Yanlış format! 3 bölüm olmalı:\n"
            "/ogret kategori | anahtar kelime | bilgi\n\n"
            "Bölümleri | ile ayırın."
        )
        return

    category = parts[0].strip()
    keyword = parts[1].strip()
    content = parts[2].strip()

    if not category or not keyword or not content:
        await update.message.reply_text("❌ Kategori, anahtar kelime ve bilgi boş olamaz!")
        return

    add_knowledge(category, keyword, content, update.effective_user.id)
    await update.message.reply_text(
        f"✅ Öğrendim! 🧠\n\n"
        f"📁 Kategori: {category}\n"
        f"🔑 Anahtar: {keyword}\n"
        f"📝 Bilgi: {content[:100]}{'...' if len(content) > 100 else ''}"
    )


async def bilgi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bilgi bankasında arama yapar. Kullanım: /bilgi [arama terimi]"""
    query = update.message.text.replace("/bilgi", "").strip()
    if not query:
        await update.message.reply_text("🔍 Kullanım: /bilgi [arama terimi]\nÖrnek: /bilgi poker")
        return

    results = search_knowledge(query)
    if not results:
        await update.message.reply_text(f"🔍 '{query}' için bilgi bankasında sonuç bulunamadı.")
        return

    text = f"🔍 '{query}' için bulunan bilgiler:\n\n"
    for cat, keyword, content in results[:5]:
        text += f"📁 [{cat}] {keyword}\n📝 {content}\n\n"

    await update.message.reply_text(text)


async def bilgiler_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm bilgi bankasını listeler."""
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    results = get_all_knowledge()
    if not results:
        await update.message.reply_text("📚 Bilgi bankası boş. /ogret komutuyla bilgi ekleyebilirsin!")
        return

    text = "📚 Bilgi Bankası:\n\n"
    for kid, cat, keyword, content in results:
        preview = content[:60] + "..." if len(content) > 60 else content
        text += f"[{kid}] 📁 {cat} | 🔑 {keyword}\n    📝 {preview}\n\n"

        # Telegram mesaj limiti
        if len(text) > 3500:
            text += "... (daha fazla kayıt var)"
            break

    text += f"\n🗑 Silmek için: /sil [id numarası]"
    await update.message.reply_text(text)


async def sil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bilgi bankasından bilgi siler. Kullanım: /sil [id]"""
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    text = update.message.text.replace("/sil", "").strip()
    if not text or not text.isdigit():
        await update.message.reply_text("❌ Kullanım: /sil [id numarası]\nID'leri görmek için: /bilgiler")
        return

    if delete_knowledge(int(text)):
        await update.message.reply_text(f"🗑 Bilgi #{text} silindi!")
    else:
        await update.message.reply_text(f"❌ Bilgi #{text} bulunamadı.")


async def adminekle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yeni admin ekler. Kullanım: /adminekle [user_id]"""
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Bu komut sadece adminler içindir.")
        return

    text = update.message.text.replace("/adminekle", "").strip()
    if not text or not text.isdigit():
        await update.message.reply_text("❌ Kullanım: /adminekle [kullanıcı ID]\nID öğrenmek için: @userinfobot")
        return

    new_admin = int(text)
    if new_admin not in ADMIN_IDS:
        ADMIN_IDS.append(new_admin)
        await update.message.reply_text(f"✅ {new_admin} admin olarak eklendi!")
    else:
        await update.message.reply_text("Bu kullanıcı zaten admin.")


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının Telegram ID'sini gösterir."""
    await update.message.reply_text(f"🆔 Senin Telegram ID'n: {update.effective_user.id}")


# ============================================================
# 💬 MESAJ İŞLEYİCİSİ
# ============================================================


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
        await update.message.reply_text("⏳ Çok hızlı mesaj gönderiyorsun! Biraz bekle 😅")
        return

    # İstatistikleri güncelle
    update_user_stats(user_id, user_name)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    logger.info(f"[{user_name}] ({user_id}): {message_text[:100]}")
    response = get_ai_response(user_id, message_text)

    if len(response) > 4000:
        for i in range(0, len(response), 4000):
            await update.message.reply_text(response[i : i + 4000])
    else:
        await update.message.reply_text(response)


async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Hata: {context.error}")


# ============================================================
# 🚀 BOTU BAŞLAT
# ============================================================


def main():
    print(f"🤖 {BOT_NAME} başlatılıyor...")

    # Debug
    print(f"🔑 Bot Token uzunluğu: {len(TELEGRAM_BOT_TOKEN)} karakter")
    print(f"🔑 API Key uzunluğu: {len(ANTHROPIC_API_KEY)} karakter")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ HATA: TELEGRAM_BOT_TOKEN ayarlanmamış!")
        return
    if not ANTHROPIC_API_KEY:
        print("❌ HATA: ANTHROPIC_API_KEY ayarlanmamış!")
        return

    # Veritabanını başlat
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Genel komutlar
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("myid", myid_command))

    # Bilgi bankası komutları
    app.add_handler(CommandHandler("ogret", ogret_command))
    app.add_handler(CommandHandler("topluogret", topluogret_command))
    app.add_handler(CommandHandler("bilgi", bilgi_command))
    app.add_handler(CommandHandler("bilgiler", bilgiler_command))
    app.add_handler(CommandHandler("sil", sil_command))

    # Admin komutları
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("adminekle", adminekle_command))

    # Mesaj işleyici
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    print(f"✅ {BOT_NAME} çalışıyor! 🎰")
    print(f"📚 Bilgi bankası: {DB_PATH}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
