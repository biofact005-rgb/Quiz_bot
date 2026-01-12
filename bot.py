import logging
import asyncio
import random
import json
import os
from datetime import datetime, time, timezone, timedelta
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PollAnswerHandler
from flask import Flask
from threading import Thread

# --- RENDER WEB SERVER (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running! 24/7"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURATION ---
TOKEN = os.getenv('TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

DB_FILE = 'database.json'
DEV_USERNAME = '@errorkidk'

# --- TIMEZONE (India +5:30) ---
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATABASE HANDLING ---
def load_db():
    default_db = {
        "questions": [], 
        "groups": {}, 
        "current_polls": {}, 
        "scores": {},
        "auth_users": [],
        "last_scores_backup": {} # Naya: Backup rakhne ke liye
    }
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                for key in default_db:
                    if key not in data: data[key] = default_db[key]
                return data
        except: pass
    return default_db

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Save Error: {e}")

db = load_db()

# --- SECURITY CHECK ---
def is_authorized(user_id):
    if user_id == OWNER_ID: return True
    if user_id in db.get("auth_users", []): return True
    return False

# --- UI & INTRO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # 🔒 CHECK PERMISSION
    if not is_authorized(user.id):
        keyboard = [[InlineKeyboardButton("✋ Request Access", callback_data='request_access')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        intro_text = (
            f"⛔ **Access Denied!**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"👋 Hi {user.first_name},\n"
            f"Yeh ek **Private Bot** hai. Owner se permission lene ke liye niche button dabayein."
        )
        await update.message.reply_text(intro_text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    # ✅ Authorized Menu
    keyboard = [
        [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard'),
         InlineKeyboardButton("📱 Active Groups", callback_data='active_groups')],
        [InlineKeyboardButton("📝 Add Qs", callback_data='add_q'),
         InlineKeyboardButton("📢 Register", callback_data='reg_g')],
        [InlineKeyboardButton("💾 Backup & Restore", callback_data='status')],
        [InlineKeyboardButton("🚀 Start Quiz", callback_data='start_cycle')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    intro_text = (
        f"🌟 **Advance Quiz Bot (Pro)** 🌟\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Creator:** {DEV_USERNAME}\n\n"
        f"✅ **Security:** Active (Owner Only)\n"
        f"✅ **Safe Mode:** Leaderboard Restore Feature Added!\n"
        f"☁️ **Server:** Render 24/7\n"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(intro_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(intro_text, reply_markup=reply_markup, parse_mode='Markdown')

# --- BUTTON HANDLER ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    # --- SECURITY LOGIC ---
    if query.data == 'request_access':
        if OWNER_ID == 0:
            await query.edit_message_text("❌ Owner ID set nahi hai.")
            return
        await query.edit_message_text("⏳ **Request Sent!** Wait for approval.")
        admin_btns = [[InlineKeyboardButton("✅ Accept", callback_data=f'auth_yes_{user.id}'), InlineKeyboardButton("❌ Reject", callback_data=f'auth_no_{user.id}')]]
        await context.bot.send_message(chat_id=OWNER_ID, text=f"🔔 **Request:**\n👤 {user.first_name}\n🆔 `{user.id}`", reply_markup=InlineKeyboardMarkup(admin_btns))
        return

    if query.data.startswith('auth_yes_'):
        new_uid = int(query.data.split('_')[2])
        if new_uid not in db["auth_users"]:
            db["auth_users"].append(new_uid)
            save_db(db)
        await query.edit_message_text(f"✅ User {new_uid} Accepted!")
        try: await context.bot.send_message(new_uid, "🎉 **Access Granted!** `/start` again.")
        except: pass
        return

    if query.data.startswith('auth_no_'):
        target_id = int(query.data.split('_')[2])
        await query.edit_message_text(f"❌ User {target_id} Rejected.")
        try: await context.bot.send_message(target_id, "❌ **Access Denied.**")
        except: pass
        return

    if not is_authorized(user.id):
        await query.edit_message_text("⛔ **Unauthorized!**")
        return

    # --- MAIN MENU ---
    back_btn = [[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]
    
    if query.data == 'leaderboard':
        if "scores" not in db or not db["scores"]:
            await query.edit_message_text("📉 No data.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        sorted_scores = sorted(db["scores"].values(), key=lambda x: x['correct'], reverse=True)[:10]
        text = "🏆 **TOP 10** 🏆\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(sorted_scores):
            rank = medals[i] if i < 3 else f"#{i+1}"
            text += f"{rank} **{p['name']}** - ✅ {p['correct']}\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_btn), parse_mode='Markdown')

    elif query.data == 'active_groups':
        if not db["groups"]:
            await query.edit_message_text("📱 No groups.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        text = "📱 **Active Groups:**\n"
        for _, data in db["groups"].items():
            if isinstance(data, dict):
                text += f"📢 {data.get('title', 'Unknown')} ({data.get('count', 0)})\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_btn), parse_mode='Markdown')

    elif query.data == 'add_q':
        await query.edit_message_text("📥 **Add:** Forward questions here.", reply_markup=InlineKeyboardMarkup(back_btn))
    elif query.data == 'reg_g':
        await query.edit_message_text("📢 **Setup:** Group me `/register` likhein.", reply_markup=InlineKeyboardMarkup(back_btn))
    
    elif query.data == 'status':
        # Status Menu with RESTORE Button
        users_count = len(db.get("auth_users", []))
        msg = f"📊 **Stats:**\nQs: `{len(db['questions'])}`\nUsers: `{users_count}`"
        btns = [
            [InlineKeyboardButton("♻️ Restore Leaderboard", callback_data='restore_scores')], # Naya Button
            [InlineKeyboardButton("📥 Backup File", callback_data='get_backup')], 
            [InlineKeyboardButton("🗑 Clear All", callback_data='clear')], 
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif query.data == 'restore_scores':
        # Restore Logic
        if "last_scores_backup" in db and db["last_scores_backup"]:
            db["scores"] = db["last_scores_backup"].copy()
            save_db(db)
            await query.edit_message_text("✅ **Success!** Purana Leaderboard wapas aa gaya hai.", reply_markup=InlineKeyboardMarkup(back_btn))
        else:
            await query.edit_message_text("❌ **Error:** Koi backup nahi mila (Shayad reset abhi hua hi nahi).", reply_markup=InlineKeyboardMarkup(back_btn))

    elif query.data == 'get_backup':
        if os.path.exists(DB_FILE):
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(DB_FILE, 'rb'), filename="backup.json")
        else: await query.edit_message_text("❌ Empty.", reply_markup=InlineKeyboardMarkup(back_btn))
    
    elif query.data == 'start_cycle':
        await query.edit_message_text("🚀 Group me `/start_quiz` karein.", reply_markup=InlineKeyboardMarkup(back_btn))
    elif query.data == 'clear':
        db['questions'] = []
        db['scores'] = {}
        db['groups'] = {}
        db['current_polls'] = {}
        save_db(db)
        await query.edit_message_text("✅ Cleared!", reply_markup=InlineKeyboardMarkup(back_btn))
    elif query.data == 'main_menu':
        await start(update, context)

# --- QUIZ LOGIC ---
async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    now = datetime.now(IST)
    if 18 <= now.hour < 22: return
    if not db["questions"]: return
    
    last_msg_id = None
    if str(chat_id) in db["groups"] and isinstance(db["groups"][str(chat_id)], dict):
        last_msg_id = db["groups"][str(chat_id)].get('last_msg')
    if last_msg_id:
        try: await context.bot.delete_message(chat_id, last_msg_id)
        except: pass

    q = random.choice(db["questions"])
    msg = await context.bot.send_poll(chat_id=chat_id, question=q["question"], options=q["options"], type='quiz', correct_option_id=q["correct"], is_anonymous=False)
    
    c_count = 0
    title = "Unknown"
    if str(chat_id) in db["groups"] and isinstance(db["groups"][str(chat_id)], dict):
        c_count = db["groups"][str(chat_id)].get('count', 0)
        title = db["groups"][str(chat_id)].get('title', 'Unknown')
    
    db["groups"][str(chat_id)] = {"last_msg": msg.message_id, "title": title, "count": c_count + 1}
    if "current_polls" not in db: db["current_polls"] = {}
    db["current_polls"][str(msg.poll.id)] = {"chat_id": chat_id, "correct_option": q["correct"]}
    save_db(db)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = str(answer.poll_id)
    user_id = str(answer.user.id)
    if "current_polls" not in db: db["current_polls"] = {}
    if "scores" not in db: db["scores"] = {}
    if poll_id in db["current_polls"]:
        correct = db["current_polls"][poll_id]["correct_option"]
        if user_id not in db["scores"]: db["scores"][user_id] = {"name": answer.user.first_name, "correct": 0, "attempted": 0}
        db["scores"][user_id]["attempted"] += 1
        if answer.option_ids[0] == correct: db["scores"][user_id]["correct"] += 1
        save_db(db)

# --- DAILY RESULTS (WITH AUTO-BACKUP) ---
async def send_daily_results(context: ContextTypes.DEFAULT_TYPE):
    if "scores" not in db or not db["scores"]: return
    
    # 💾 AUTO BACKUP BEFORE RESET
    db["last_scores_backup"] = db["scores"].copy()
    save_db(db) # Save backup immediately

    sorted_scores = sorted(db["scores"].values(), key=lambda x: x['correct'], reverse=True)[:3]
    text = "🏆 **DAILY LEADERBOARD** 🏆\n"
    for p in sorted_scores: text += f"👤 {p['name']} - ✅ {p['correct']}\n"
    for chat_id in db["groups"]:
        try: await context.bot.send_message(chat_id, text, parse_mode='Markdown')
        except: pass
    
    # Reset Scores
    db["scores"] = {}
    db["current_polls"] = {}
    save_db(db)

async def extract_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    if update.message.poll and update.message.poll.type == 'quiz':
        p = update.message.poll
        db["questions"].append({"question": p.question, "options": [o.text for o in p.options], "correct": p.correct_option_id})
        save_db(db)
        await update.message.reply_text(f"✅ Saved! Total: {len(db['questions'])}")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): 
        await update.message.reply_text("⛔ Owner Only!")
        return
    db["groups"][str(update.effective_chat.id)] = {"last_msg": None, "title": update.effective_chat.title, "count": 0}
    save_db(db)
    await update.message.reply_text("✅ Registered!")

async def start_quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    context.job_queue.run_repeating(auto_quiz_job, interval=600, first=5, chat_id=update.effective_chat.id)
    await update.message.reply_text("🚀 Started!")

async def handle_recovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id): return
    doc = update.message.document
    if doc.file_name.endswith('.json') and update.message.caption == '/recover':
        file = await doc.get_file()
        await file.download_to_drive(DB_FILE)
        global db
        db = load_db()
        await update.message.reply_text("♻️ Restored!")

if __name__ == '__main__':
    keep_alive()
    if not TOKEN: print("❌ TOKEN MISSING")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("register", register))
        app.add_handler(CommandHandler("start_quiz", start_quiz_cmd))
        app.add_handler(CallbackQueryHandler(handle_buttons))
        app.add_handler(MessageHandler(filters.POLL, extract_quiz))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        app.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_recovery))
        app.job_queue.run_daily(send_daily_results, time=time(hour=0, minute=0, tzinfo=IST))
        app.run_polling()
