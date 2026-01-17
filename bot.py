import logging
import asyncio
import random
import json
import os
from datetime import datetime, time, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Global Dictionary to track Live Users (in-memory)
active_users = {}

# --- DATABASE HANDLING ---
def load_db():
    # Unified Structure for both BSEB and NEET
    default_db = {
        "questions": {
            "BSEB": {subj: {} for subj in ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]},
            "NEET": {subj: {} for subj in ["Physics", "Chemistry", "Biology"]}
        },
        "groups": {},
        "admins": [OWNER_ID],
        "stats": {},
        "user_data": {}
    }
    
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                if "questions" not in data: data["questions"] = default_db["questions"]
                if "admins" not in data: data["admins"] = default_db["admins"]
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

# --- HELPER FUNCTIONS ---
def is_admin(user_id):
    return user_id in db["admins"] or user_id == OWNER_ID

def update_live_user(user_id):
    """Updates the timestamp for a user to track them as 'Live'"""
    active_users[user_id] = datetime.now()

def get_live_count():
    """Returns count of users active in the last 10 minutes"""
    cutoff = datetime.now() - timedelta(minutes=10)
    # Remove old users from memory dict
    expired = [uid for uid, time in active_users.items() if time < cutoff]
    for uid in expired:
        del active_users[uid]
    return len(active_users)

def get_random_questions(category, subject, chapters_list, count=10):
    all_q = []
    # Loop through selected chapters and gather questions
    for chap in chapters_list:
        qs = db["questions"][category][subject].get(chap, [])
        all_q.extend(qs)
    
    if not all_q: return []
    return random.sample(all_q, min(len(all_q), count))

# --- START & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_live_user(user_id) # Track Live
    
    # Init Stats
    if str(user_id) not in db["stats"]:
        db["stats"][str(user_id)] = {}
        save_db(db)

    # UI Selection
    buttons = [
        [InlineKeyboardButton("📚 BSEB (Bihar Board)", callback_data='menu_bseb')],
        [InlineKeyboardButton("🩺 NEET (Medical)", callback_data='menu_neet')],
        [InlineKeyboardButton("⚙️ Settings & Stats", callback_data='menu_settings')]
    ]
    
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🛡️ Admin Panel", callback_data='menu_admin')])
        
    intro_text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨  **W E L C O M E** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 **Hello {update.effective_user.first_name}!**\n\n"
        f"🚀 **Select a Category:**\n"
        f"📚 **BSEB:** State Board Exams\n"
        f"🩺 **NEET:** Medical Entrance\n"
        f"⚙️ **Settings:** Profile & Stats\n\n"
        f"👇 _Tap a button below to begin:_"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(intro_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')
    else:
        await update.message.reply_text(intro_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')

# --- MENU HANDLERS ---
async def handle_menus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    update_live_user(user_id)
    
    # 1. SUBJECT SELECTION (BSEB & NEET)
    if data == 'menu_bseb':
        btns = []
        subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
        for sub in subjects:
            btns.append([InlineKeyboardButton(f"📖 {sub}", callback_data=f'sel_sub_BSEB_{sub}')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
        await query.edit_message_text("📚 **BSEB Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data == 'menu_neet':
        btns = [
            [InlineKeyboardButton("⚛️ Physics", callback_data='sel_sub_NEET_Physics')],
            [InlineKeyboardButton("🧪 Chemistry", callback_data='sel_sub_NEET_Chemistry')],
            [InlineKeyboardButton("🧬 Biology", callback_data='sel_sub_NEET_Biology')],
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await query.edit_message_text("🩺 **NEET Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # 2. MODE SELECTION (Chapter Wise vs Mix)
    elif data.startswith('sel_sub_'):
        parts = data.split('_')
        cat = parts[2]
        sub = parts[3]
        
        context.user_data['quiz_cat'] = cat
        context.user_data['quiz_sub'] = sub
        
        btns = [
            [InlineKeyboardButton("📖 Chapter Wise (Select One)", callback_data='mode_single')],
            [InlineKeyboardButton("🔀 Custom Mix (Select Multiple)", callback_data='mode_mix')],
            [InlineKeyboardButton("⬅️ Back", callback_data=f'menu_{cat.lower()}')]
        ]
        await query.edit_message_text(f"📂 **{cat} > {sub}**\n\nSelect Quiz Mode:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # 3. CHAPTER SELECTION (Logic split for Single vs Mix)
    elif data == 'mode_single':
        await show_chapter_selection(query, context, multi=False)
        
    elif data == 'mode_mix':
        # Initialize selection list
        context.user_data['selected_chapters'] = [] 
        await show_chapter_selection(query, context, multi=True)

    # 4. TOGGLE LOGIC (For Mix Mode)
    elif data.startswith('tgl_'):
        chap_name = data.split('tgl_')[1]
        selected = context.user_data.get('selected_chapters', [])
        
        if chap_name in selected:
            selected.remove(chap_name)
        else:
            selected.append(chap_name)
            
        context.user_data['selected_chapters'] = selected
        # Refresh buttons without new message
        await show_chapter_selection(query, context, multi=True)

    # 5. CONFIRM MIX SELECTION
    elif data == 'confirm_mix':
        selected = context.user_data.get('selected_chapters', [])
        if not selected:
            await query.answer("❌ Select at least one chapter!", show_alert=True)
            return
        # Proceed to Time
        context.user_data['final_chapters'] = selected
        await ask_time(query)

    # 6. SINGLE CHAPTER CLICK
    elif data.startswith('sng_'):
        chap_name = data.split('sng_')[1]
        context.user_data['final_chapters'] = [chap_name]
        await ask_time(query)

    # 7. TIME & COUNT
    elif data.startswith('time_'):
        context.user_data['quiz_time'] = int(data.split('_')[1])
        await ask_count(query)

    elif data.startswith('count_'):
        context.user_data['quiz_count'] = int(data.split('_')[1])
        await start_private_quiz(query, context)
        
    # --- ADMIN & SETTINGS ---
    elif data == 'menu_settings':
        await show_settings(update, context)

    elif data == 'main_menu':
        await start(update, context)

async def show_chapter_selection(query, context, multi):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    
    # Get all chapters for this subject
    chapters_data = db["questions"][cat].get(sub, {})
    
    if not chapters_data:
        btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f'sel_sub_{cat}_{sub}')]]
        text = f"❌ No chapters found in **{sub}**."
        if query.message.text != text: # Prevent edit error if same
             await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
        return

    btns = []
    selected = context.user_data.get('selected_chapters', [])
    
    for chap, q_list in chapters_data.items():
        q_count = len(q_list)
        
        if multi:
            # Checkbox Style
            icon = "✅" if chap in selected else "⬜"
            btns.append([InlineKeyboardButton(f"{icon} {chap} [{q_count}]", callback_data=f'tgl_{chap}')])
        else:
            # Simple Button
            btns.append([InlineKeyboardButton(f"📄 {chap} [{q_count}]", callback_data=f'sng_{chap}')])

    # Footer Buttons
    if multi:
        btns.append([InlineKeyboardButton(f"▶️ Start Quiz ({len(selected)})", callback_data='confirm_mix')])
    
    btns.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    
    mode_text = "Custom Mix (Tap to select)" if multi else "Chapter Wise (Tap to start)"
    text = f"📖 **{sub} - {mode_text}**"
    
    # Check if we need to edit (to avoid API error on same content)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')


# --- QUIZ FLOW HELPERS ---
async def ask_time(query):
    times = [15, 30, 45, 60]
    btns = [InlineKeyboardButton(f"⏱️ {t} sec", callback_data=f"time_{t}") for t in times]
    keyboard = [btns[i:i+2] for i in range(0, len(btns), 2)]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("⏱️ **Select Time per Question:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ask_count(query):
    counts = [15, 30, 45, 60, 90, 120]
    btns = [InlineKeyboardButton(f"📝 {c} Qs", callback_data=f"count_{c}") for c in counts]
    keyboard = [btns[i:i+2] for i in range(0, len(btns), 2)]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("🔢 **How many questions?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def start_private_quiz(query, context):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    selected_chaps = context.user_data.get('final_chapters')
    time_limit = context.user_data.get('quiz_time')
    requested_count = context.user_data.get('quiz_count')

    questions = get_random_questions(cat, sub, selected_chaps, requested_count)
    
    if not questions:
        await query.edit_message_text("❌ No questions found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
        return

    msg_text = f"🚀 **Starting Quiz!**\n\n📂 **Category:** {cat}\n📘 **Subject:** {sub}\n📑 **Chapters:** {len(selected_chaps)}\n"
    if len(questions) < requested_count:
        msg_text += f"⚠️ **Note:** Only {len(questions)} questions available.\n"
    else:
        msg_text += f"❓ **Questions:** {len(questions)}\n"
        
    await query.edit_message_text(msg_text, parse_mode='Markdown')
    context.job_queue.run_once(run_quiz_sequence, 1, chat_id=query.message.chat_id, data={'q': questions, 't': time_limit, 'u': query.from_user.id, 'c': cat, 's': sub})

async def run_quiz_sequence(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    questions = job_data['q']
    time_limit = job_data['t']
    chat_id = context.job.chat_id
    
    for q in questions:
        try:
            msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=q['question'],
                options=q['options'],
                correct_option_id=q['correct'],
                type='quiz',
                open_period=time_limit,
                is_anonymous=False
            )
            if "current_polls" not in db: db["current_polls"] = {}
            db["current_polls"][str(msg.poll.id)] = {"cat": job_data['c'], "sub": job_data['s'], "user": job_data['u']}
            await asyncio.sleep(time_limit + 2) 
        except Exception as e:
            logging.error(f"Quiz Error: {e}")
            break
    
    await context.bot.send_message(chat_id, "🏁 **Quiz Completed!** Check stats in Settings.")
    save_db(db)

# --- ADMIN PANEL ---
async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    if data == 'menu_admin':
        # Live User Count Button Added
        live_count = get_live_count()
        btns = [
            [InlineKeyboardButton(f"🟢 Live Users: {live_count}", callback_data='refresh_live')],
            [InlineKeyboardButton("➕ Add to BSEB", callback_data='adm_sel_BSEB')],
            [InlineKeyboardButton("➕ Add to NEET", callback_data='adm_sel_NEET')],
            [InlineKeyboardButton("⏱️ Manage Groups", callback_data='adm_manage_groups')],
            [InlineKeyboardButton("⬅️ Back to Main", callback_data='main_menu')]
        ]
        await query.edit_message_text("🛡️ **Admin Panel**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data == 'refresh_live':
        # Just refresh the admin menu
        await handle_admin(update, context)

    # Unified Add Question Logic (Since structure is now same for BSEB/NEET)
    elif data.startswith('adm_sel_'):
        cat = data.split('_')[2]
        context.user_data['adm_cat'] = cat
        
        # Show subjects
        subjects = db["questions"][cat].keys()
        btns = [[InlineKeyboardButton(sub, callback_data=f'adm_sub_{sub}')] for sub in subjects]
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await query.edit_message_text(f"Select {cat} Subject:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith('adm_sub_'):
        sub = data.split('_')[2]
        context.user_data['adm_sub'] = sub
        cat = context.user_data.get('adm_cat')
        
        # Show Chapters + Add New
        chapters = db["questions"][cat].get(sub, {}).keys()
        btns = [[InlineKeyboardButton(chap, callback_data=f'adm_chap_{chap}')] for chap in chapters]
        
        btns.append([InlineKeyboardButton("➕ Add New Chapter", callback_data='adm_new_chap')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        
        await query.edit_message_text(f"Select Chapter for {cat} > {sub}:", reply_markup=InlineKeyboardMarkup(btns))

    elif data == 'adm_new_chap':
        await query.edit_message_text("⌨️ **Type the New Chapter Name:**")
        context.user_data['awaiting_chap_name'] = True

    elif data.startswith('adm_chap_'):
        chap = data.split('_')[2]
        context.user_data['adm_chap'] = chap
        context.user_data['adm_mode'] = 'active'
        await query.edit_message_text(f"📂 **Active:** {context.user_data['adm_cat']} > {context.user_data['adm_sub']} > {chap}\n\n👇 **Forward Quiz Polls Now.**\nType /cancel to stop.", parse_mode='Markdown')

    # ... (Group Time Management - Keeping logic same as previous) ...
    elif data == 'adm_manage_groups':
        if not db["groups"]:
            await query.answer("No active groups.", show_alert=True)
            return
        btns = [[InlineKeyboardButton(f"📢 {info.get('title','Group')}", callback_data=f'mng_grp_{gid}')] for gid, info in db["groups"].items()]
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await query.edit_message_text("⏱️ **Select Group:**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data.startswith('mng_grp_'):
        gid = data.split('_')[2]
        context.user_data['target_grp'] = gid
        btns = [[InlineKeyboardButton("1 Min", callback_data='set_int_60')], [InlineKeyboardButton("10 Min", callback_data='set_int_600')], [InlineKeyboardButton("⬅️ Back", callback_data='adm_manage_groups')]]
        await query.edit_message_text("Select Interval:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith('set_int_'):
        sec = int(data.split('_')[2])
        gid = context.user_data.get('target_grp')
        if gid in db["groups"]:
            db["groups"][gid]["interval"] = sec
            save_db(db)
            await query.edit_message_text("✅ Updated!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')]]))

# --- MESSAGE HANDLERS ---
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_chap_name') and is_admin(user_id):
        new_chap = text.strip()
        cat = context.user_data.get('adm_cat')
        sub = context.user_data.get('adm_sub')
        
        if new_chap not in db["questions"][cat][sub]:
            db["questions"][cat][sub][new_chap] = []
            save_db(db)
            await update.message.reply_text(f"✅ Chapter **'{new_chap}'** added to {cat} > {sub}.\nNow select it to add questions.")
        else:
            await update.message.reply_text("Chapter already exists.")
        context.user_data['awaiting_chap_name'] = False
        return

async def handle_poll_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) or context.user_data.get('adm_mode') != 'active': return

    poll = update.message.poll
    cat = context.user_data.get('adm_cat')
    sub = context.user_data.get('adm_sub')
    chap = context.user_data.get('adm_chap')
    
    q_data = {
        "question": poll.question,
        "options": [o.text for o in poll.options],
        "correct": poll.correct_option_id
    }

    db["questions"][cat][sub][chap].append(q_data)
    save_db(db)
    count = len(db["questions"][cat][sub][chap])
    await update.message.reply_text(f"✅ Saved! Chapter Total: {count}")

async def show_settings(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    stats_btn = InlineKeyboardButton("📊 My Stats", callback_data='view_stats')
    req_btn = InlineKeyboardButton("✋ Request Admin", callback_data='req_admin')
    
    btns = [[stats_btn], [req_btn]]
    
    if user_id == OWNER_ID:
        btns.append([InlineKeyboardButton("➕ Add Admin", callback_data='add_admin_prompt')])
        btns.append([InlineKeyboardButton("💾 Backup", callback_data='get_backup')])
        
    btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
    await query.edit_message_text("⚙️ **Settings**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

# --- STATS, GROUP & OTHERS ---
# (Keeping basic functions compact for brevity, Logic remains same)
async def view_stats(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    stats = db["stats"].get(user_id, {})
    if not stats:
        await query.answer("No stats yet!", show_alert=True)
        return
    text = "📊 **Your Stats**\n"
    for cat in stats:
        text += f"\n🔹 {cat}:\n"
        for sub, data in stats[cat].items():
            text += f"   - {sub}: {data['total']} Qs\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]))

async def req_admin(update, context):
    await context.bot.send_message(OWNER_ID, f"🔔 Req: {update.effective_user.first_name}")
    await update.callback_query.answer("Sent!")

async def register_group(update, context):
    chat_id = str(update.effective_chat.id)
    if chat_id not in db["groups"]: db["groups"][chat_id] = {"title": update.effective_chat.title, "mode": None, "interval": 600}
    save_db(db)
    await update.message.reply_text("✅ Registered! Use /start_quiz")

async def start_group_quiz(update, context):
    chat_id = str(update.effective_chat.id)
    if chat_id not in db["groups"]: return
    interval = db["groups"][chat_id]["interval"]
    context.job_queue.run_repeating(auto_group_job, interval=interval, first=5, data=chat_id)
    await update.message.reply_text(f"🚀 Started! Interval: {interval}s")

async def auto_group_job(context):
    chat_id = context.job.data
    # For group mix, we pick random from all. Simplified logic:
    # In real mix, you'd iterate all. Here we assume mixed for now.
    pass # Add group random logic if needed specific to mode

async def handle_poll_answer(update, context):
    poll_id = str(update.poll_answer.poll_id)
    user_id = str(update.poll_answer.user.id)
    if poll_id in db.get("current_polls", {}):
        p = db["current_polls"][poll_id]
        if str(user_id) not in db["stats"]: db["stats"][str(user_id)] = {}
        if p['cat'] not in db["stats"][str(user_id)]: db["stats"][str(user_id)][p['cat']] = {}
        if p['sub'] not in db["stats"][str(user_id)][p['cat']]: db["stats"][str(user_id)][p['cat']][p['sub']] = {'total':0}
        db["stats"][str(user_id)][p['cat']][p['sub']]['total'] += 1
        save_db(db)

async def cancel_op(update, context):
    context.user_data['adm_mode'] = None
    context.user_data['awaiting_chap_name'] = False
    await update.message.reply_text("❌ Cancelled.")

if __name__ == '__main__':
    keep_alive()
    if not TOKEN: print("❌ TOKEN MISSING")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("register", register_group))
        app.add_handler(CommandHandler("start_quiz", start_group_quiz))
        app.add_handler(CommandHandler("cancel", cancel_op))
        
        # Callbacks
        app.add_handler(CallbackQueryHandler(handle_menus, pattern='^main_menu|menu_|sel_sub_|mode_|tgl_|confirm_mix|sng_|time_|count_'))
        app.add_handler(CallbackQueryHandler(handle_admin, pattern='^menu_admin|refresh_live|adm_|mng_|set_int_'))
        app.add_handler(CallbackQueryHandler(show_settings, pattern='^menu_settings|view_stats|req_admin'))
        
        # Messages
        app.add_handler(MessageHandler(filters.POLL, handle_poll_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        
        print("Bot is Live!")
        app.run_polling()
