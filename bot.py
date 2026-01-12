import logging
import asyncio
import random
import os
from datetime import datetime, time, timezone, timedelta
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PollAnswerHandler
import pymongo 

# --- CONFIGURATION ---
TOKEN = '8578006548:AAFb9bjUBZAmkIfYvrpFpWS2c0YIw-2baBI'

# ⚠️ YAHAN APNA MONGODB URL DALEIN (Password ke sath)
MONGO_URL = "mongodb+srv://YOUR_USER:YOUR_PASSWORD@cluster0.mongodb.net/?retryWrites=true&w=majority"

DEV_USERNAME = '@errorkidk'

# --- TIMEZONE (India +5:30) ---
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- MONGODB CONNECTION ---
try:
    client = pymongo.MongoClient(MONGO_URL)
    db_cloud = client["QuizBotDB"]
    collection = db_cloud["data"]
    logging.info("✅ Connected to MongoDB Atlas!")
except Exception as e:
    logging.error(f"❌ MongoDB Connection Failed: {e}")

# --- DATABASE HANDLING (CLOUD) ---
def load_db():
    try:
        data = collection.find_one({"_id": "bot_data"})
        if data: return data
    except: pass
    return {"_id": "bot_data", "questions": [], "groups": {}, "current_polls": {}, "scores": {}}

def save_db(data):
    try:
        collection.replace_one({"_id": "bot_data"}, data, upsert=True)
    except Exception as e:
        logging.error(f"Save Error: {e}")

db = load_db()

# --- UI & INTRO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏆 Live Leaderboard", callback_data='leaderboard')],
        [InlineKeyboardButton("📱 Active Groups", callback_data='active_groups')],
        [InlineKeyboardButton("📝 Add Questions", callback_data='add_q'),
         InlineKeyboardButton("📢 Group Setup", callback_data='reg_g')],
        [InlineKeyboardButton("📊 Status", callback_data='status')],
        [InlineKeyboardButton("🚀 Start Cycle", callback_data='start_cycle')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    intro_text = f"🌟 **Cloud Quiz Bot** 🌟\n━━━━━━━━━━━━━━━━━━━━\n☁️ **Storage:** MongoDB (Permanent)\n👇 **Menu:**"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(intro_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(intro_text, reply_markup=reply_markup, parse_mode='Markdown')

# --- BUTTON HANDLER ---
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    back_btn = [[InlineKeyboardButton("⬅️ Main Menu", callback_data='main_menu')]]
    
    if query.data == 'leaderboard':
        if "scores" not in db or not db["scores"]:
            await query.edit_message_text("📉 Koi data nahi hai.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        sorted_scores = sorted(db["scores"].values(), key=lambda x: x['correct'], reverse=True)[:10]
        text = "🏆 **TOP 10 PLAYERS** 🏆\n\n"
        for i, p in enumerate(sorted_scores):
            text += f"#{i+1} **{p['name']}** - ✅ {p['correct']}\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_btn), parse_mode='Markdown')

    elif query.data == 'active_groups':
        if not db["groups"]:
            await query.edit_message_text("📱 Koi group active nahi.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        text = "📱 **Active Groups:**\n\n"
        for _, data in db["groups"].items():
            if isinstance(data, dict):
                text += f"📢 {data.get('title', 'Unknown')} (Sent: {data.get('count', 0)})\n"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(back_btn), parse_mode='Markdown')

    elif query.data == 'add_q':
        await query.edit_message_text("📥 **Add:** Quiz forward karein.", reply_markup=InlineKeyboardMarkup(back_btn))
    elif query.data == 'reg_g':
        await query.edit_message_text("📢 **Setup:** Group mein `/register` likhein.", reply_markup=InlineKeyboardMarkup(back_btn))
    elif query.data == 'status':
        btns = [[InlineKeyboardButton("🗑 Clear DB", callback_data='clear')], [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]]
        await query.edit_message_text(f"📊 Questions: `{len(db['questions'])}`", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
    elif query.data == 'start_cycle':
        await query.edit_message_text("🚀 Group mein `/start_quiz` karein.", reply_markup=InlineKeyboardMarkup(back_btn))
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

# --- HANDLERS ---
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

async def send_daily_results(context: ContextTypes.DEFAULT_TYPE):
    if "scores" not in db or not db["scores"]: return
    sorted_scores = sorted(db["scores"].values(), key=lambda x: x['correct'], reverse=True)[:3]
    text = "🏆 **DAILY RESULTS** 🏆\n"
    for p in sorted_scores: text += f"👤 {p['name']} - ✅ {p['correct']}\n"
    for chat_id in db["groups"]:
        try: await context.bot.send_message(chat_id, text, parse_mode='Markdown')
        except: pass
    db["scores"] = {}
    db["current_polls"] = {}
    save_db(db)

async def extract_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.poll and update.message.poll.type == 'quiz':
        p = update.message.poll
        db["questions"].append({"question": p.question, "options": [o.text for o in p.options], "correct": p.correct_option_id})
        save_db(db)
        await update.message.reply_text(f"✅ Saved! Total: {len(db['questions'])}")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db["groups"][str(update.effective_chat.id)] = {"last_msg": None, "title": update.effective_chat.title, "count": 0}
    save_db(db)
    await update.message.reply_text("✅ Registered!")

async def start_quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.run_repeating(auto_quiz_job, interval=600, first=5, chat_id=update.effective_chat.id)
    await update.message.reply_text("🚀 Started!")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("start_quiz", start_quiz_cmd))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.POLL, extract_quiz))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.job_queue.run_daily(send_daily_results, time=time(hour=0, minute=0, tzinfo=IST))
    app.run_polling()
