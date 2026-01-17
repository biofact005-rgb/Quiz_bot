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

# --- DATABASE HANDLING ---
def load_db():
    default_db = {
        "questions": {
            "BSEB": {subj: [] for subj in ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]},
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
                # Ensure structure integrity
                if "questions" not in data: data["questions"] = default_db["questions"]
                if "admins" not in data: data["admins"] = default_db["admins"]
                if "stats" not in data: data["stats"] = default_db["stats"]
                if "groups" not in data: data["groups"] = default_db["groups"]
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

def get_random_questions(category, subject=None, chapter=None, count=10):
    all_q = []
    
    if category == "BSEB":
        if subject:
            all_q = db["questions"]["BSEB"].get(subject, [])
        else:
            for sub in db["questions"]["BSEB"]:
                all_q.extend(db["questions"]["BSEB"][sub])
                
    elif category == "NEET":
        if subject and chapter:
            all_q = db["questions"]["NEET"].get(subject, {}).get(chapter, [])
        elif subject:
             for chap in db["questions"]["NEET"][subject]:
                 all_q.extend(db["questions"]["NEET"][subject][chap])
        else:
            for sub in db["questions"]["NEET"]:
                for chap in db["questions"]["NEET"][sub]:
                    all_q.extend(db["questions"]["NEET"][sub][chap])
    
    if not all_q: return []
    # Logic: If requested 45 but have 30, return 30. No error.
    return random.sample(all_q, min(len(all_q), count))

# --- START & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fname = update.effective_user.first_name
    
    # Init Stats
    if str(user_id) not in db["stats"]:
        db["stats"][str(user_id)] = {}
        save_db(db)

    # UI Selection (Professional English)
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
        f"👋 **Hello {fname}!**\n\n"
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
    
    # 1. BSEB MENU
    if data == 'menu_bseb':
        btns = []
        subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
        for sub in subjects:
            btns.append([InlineKeyboardButton(f"📖 {sub}", callback_data=f'bseb_sub_{sub}')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
        await query.edit_message_text("📚 **BSEB Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # 2. NEET MENU
    elif data == 'menu_neet':
        btns = [
            [InlineKeyboardButton("⚛️ Physics", callback_data='neet_sub_Physics')],
            [InlineKeyboardButton("🧪 Chemistry", callback_data='neet_sub_Chemistry')],
            [InlineKeyboardButton("🧬 Biology", callback_data='neet_sub_Biology')],
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await query.edit_message_text("🩺 **NEET Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # 3. SETTINGS MENU
    elif data == 'menu_settings':
        stats_btn = InlineKeyboardButton("📊 My Stats", callback_data='view_stats')
        req_btn = InlineKeyboardButton("✋ Request Admin", callback_data='req_admin')
        admin_btns = []
        
        if user_id == OWNER_ID:
            admin_btns.append(InlineKeyboardButton("➕ Add Admin", callback_data='add_admin_prompt'))
            admin_btns.append(InlineKeyboardButton("💾 Backup Data", callback_data='get_backup'))
            admin_btns.append(InlineKeyboardButton("♻️ Restore Data", callback_data='restore_prompt'))

        keyboard = [[stats_btn], [req_btn]] 
        for btn in admin_btns: keyboard.append([btn])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
        
        await query.edit_message_text("⚙️ **Settings & Tools**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    # --- STATS & REQUEST HANDLERS (Fixed) ---
    elif data == 'view_stats':
        await view_stats(update, context)
        
    elif data == 'req_admin':
        await req_admin(update, context)

    # --- BACK / CANCEL ---
    elif data == 'main_menu':
        await start(update, context)

    # --- QUIZ SELECTION ---
    elif data.startswith('bseb_sub_'):
        subject = data.split('_')[2]
        context.user_data['quiz_cat'] = 'BSEB'
        context.user_data['quiz_sub'] = subject
        await ask_time(query)

    elif data.startswith('neet_sub_'):
        subject = data.split('_')[2]
        context.user_data['quiz_cat'] = 'NEET'
        context.user_data['quiz_sub'] = subject
        
        chapters = db["questions"]["NEET"].get(subject, {}).keys()
        btns = []
        for chap in chapters:
            btns.append([InlineKeyboardButton(chap, callback_data=f'neet_chap_{chap}')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_neet')])
        
        if not chapters:
            await query.edit_message_text(f"❌ No chapters found in {subject}.", reply_markup=InlineKeyboardMarkup(btns))
        else:
            await query.edit_message_text(f"📖 Select Chapter for {subject}:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith('neet_chap_'):
        chapter = data.split('_')[2]
        context.user_data['quiz_chap'] = chapter
        await ask_time(query)

    elif data.startswith('time_'):
        seconds = int(data.split('_')[1])
        context.user_data['quiz_time'] = seconds
        await ask_count(query)

    elif data.startswith('count_'):
        count = int(data.split('_')[1])
        context.user_data['quiz_count'] = count
        await start_private_quiz(query, context)

# --- QUIZ HELPERS ---
async def ask_time(query):
    times = [15, 30, 45, 60]
    btns = [InlineKeyboardButton(f"⏱️ {t} sec", callback_data=f"time_{t}") for t in times]
    keyboard = [btns[i:i+2] for i in range(0, len(btns), 2)]
    # Cancel Button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("⏱️ **Select Time per Question:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ask_count(query):
    counts = [15, 30, 45, 60, 90, 120]
    btns = [InlineKeyboardButton(f"📝 {c} Qs", callback_data=f"count_{c}") for c in counts]
    keyboard = [btns[i:i+2] for i in range(0, len(btns), 2)]
    # Cancel Button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("🔢 **How many questions?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def start_private_quiz(query, context):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    chap = context.user_data.get('quiz_chap', None)
    time_limit = context.user_data.get('quiz_time')
    requested_count = context.user_data.get('quiz_count')

    questions = get_random_questions(cat, sub, chap, requested_count)
    
    # Logic: Use available questions if less than requested
    if not questions:
        await query.edit_message_text("❌ No questions found in this section.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
        return

    msg_text = f"🚀 **Starting Quiz!**\n\n📂 **Category:** {cat}\n📘 **Subject:** {sub}\n"
    if len(questions) < requested_count:
        msg_text += f"⚠️ **Note:** Only {len(questions)} questions available (Requested: {requested_count}).\n"
    else:
        msg_text += f"❓ **Questions:** {len(questions)}\n"
        
    msg_text += "\n_Bot will send questions shortly..._"

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

    # Admin Main Menu
    if data == 'menu_admin':
        btns = [
            [InlineKeyboardButton("➕ Add to BSEB", callback_data='adm_sel_BSEB')],
            [InlineKeyboardButton("➕ Add to NEET", callback_data='adm_sel_NEET')],
            [InlineKeyboardButton("⏱️ Manage Group Intervals", callback_data='adm_manage_groups')], # New
            [InlineKeyboardButton("⬅️ Back to Main", callback_data='main_menu')]
        ]
        await query.edit_message_text("🛡️ **Admin Panel**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # --- GROUP MANAGEMENT (TIME) ---
    elif data == 'adm_manage_groups':
        if not db["groups"]:
            await query.answer("No active groups found.", show_alert=True)
            return
        
        btns = []
        for gid, info in db["groups"].items():
            # Button for each group
            title = info.get('title', f"Group {gid}")
            btns.append([InlineKeyboardButton(f"📢 {title}", callback_data=f'mng_grp_{gid}')])
        
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await query.edit_message_text("⏱️ **Select a Group to manage interval:**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data.startswith('mng_grp_'):
        gid = data.split('_')[2]
        context.user_data['target_grp'] = gid
        curr_int = db["groups"][gid].get("interval", 600)
        
        btns = [
            [InlineKeyboardButton("30 Sec", callback_data=f'set_int_30')],
            [InlineKeyboardButton("1 Min", callback_data=f'set_int_60')],
            [InlineKeyboardButton("5 Min", callback_data=f'set_int_300')],
            [InlineKeyboardButton("10 Min", callback_data=f'set_int_600')],
            [InlineKeyboardButton("⬅️ Back", callback_data='adm_manage_groups')]
        ]
        await query.edit_message_text(f"⚙️ **Managing:** `{gid}`\n⏱️ Current Interval: `{curr_int}s`\n\nSelect new interval:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data.startswith('set_int_'):
        seconds = int(data.split('_')[2])
        gid = context.user_data.get('target_grp')
        
        if gid and gid in db["groups"]:
            db["groups"][gid]["interval"] = seconds
            save_db(db)
            await query.edit_message_text(f"✅ **Success!**\nNew Interval: `{seconds}s`\n\nThe group will use this interval from the next `/start_quiz`.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')]]), parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Group not found.", parse_mode='Markdown')

    # --- ADD QUESTIONS FLOW ---
    elif data.startswith('adm_sel_'):
        cat = data.split('_')[2]
        context.user_data['adm_cat'] = cat
        
        if cat == "BSEB":
            btns = []
            for sub in db["questions"]["BSEB"]:
                btns.append([InlineKeyboardButton(sub, callback_data=f'adm_sub_{sub}')])
            btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
            await query.edit_message_text("Select BSEB Subject:", reply_markup=InlineKeyboardMarkup(btns))
        else: # NEET
            btns = [
                [InlineKeyboardButton("Physics", callback_data='adm_sub_Physics')],
                [InlineKeyboardButton("Chemistry", callback_data='adm_sub_Chemistry')],
                [InlineKeyboardButton("Biology", callback_data='adm_sub_Biology')],
                [InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')]
            ]
            await query.edit_message_text("Select NEET Subject:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith('adm_sub_'):
        sub = data.split('_')[2]
        context.user_data['adm_sub'] = sub
        cat = context.user_data.get('adm_cat')
        
        if cat == "BSEB":
            context.user_data['adm_mode'] = 'active'
            await query.edit_message_text(f"📂 **Selected:** BSEB > {sub}\n\n👇 **Forward Quiz Polls/Questions Now.**\nType /cancel to stop.", parse_mode='Markdown')
        else: # NEET
            chapters = db["questions"]["NEET"].get(sub, {}).keys()
            btns = []
            for chap in chapters:
                btns.append([InlineKeyboardButton(chap, callback_data=f'adm_chap_{chap}')])
            
            btns.append([InlineKeyboardButton("➕ Add New Chapter", callback_data='adm_new_chap')])
            btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
            await query.edit_message_text(f"Select Chapter for {sub}:", reply_markup=InlineKeyboardMarkup(btns))

    elif data == 'adm_new_chap':
        await query.edit_message_text("⌨️ **Type the New Chapter Name:**")
        context.user_data['awaiting_chap_name'] = True

    elif data.startswith('adm_chap_'):
        chap = data.split('_')[2]
        context.user_data['adm_chap'] = chap
        context.user_data['adm_mode'] = 'active'
        await query.edit_message_text(f"📂 **Selected:** NEET > {context.user_data['adm_sub']} > {chap}\n\n👇 **Forward Quiz Polls Now.**\nType /cancel to stop.", parse_mode='Markdown')

    # Owner Commands
    elif data == 'add_admin_prompt':
        await query.edit_message_text("🆔 Send the **User ID** to promote to Admin.", parse_mode='Markdown')
        context.user_data['awaiting_admin_id'] = True
    
    elif data == 'get_backup':
        if os.path.exists(DB_FILE):
             await context.bot.send_document(chat_id=update.effective_chat.id, document=open(DB_FILE, 'rb'), filename="backup.json")
        else:
            await query.answer("No DB found.")

    elif data == 'restore_prompt':
        await query.edit_message_text("📤 **Send the `backup.json` file now** to restore.", parse_mode='Markdown')

# --- MESSAGE HANDLERS ---
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_admin_id') and user_id == OWNER_ID:
        try:
            new_admin = int(text)
            if new_admin not in db["admins"]:
                db["admins"].append(new_admin)
                save_db(db)
                await update.message.reply_text(f"✅ User {new_admin} is now an Admin.")
            else:
                await update.message.reply_text("Already an admin.")
        except:
            await update.message.reply_text("❌ Invalid ID.")
        context.user_data['awaiting_admin_id'] = False
        return

    if context.user_data.get('awaiting_chap_name') and is_admin(user_id):
        new_chap = text.strip()
        sub = context.user_data.get('adm_sub')
        if new_chap not in db["questions"]["NEET"][sub]:
            db["questions"]["NEET"][sub][new_chap] = []
            save_db(db)
            await update.message.reply_text(f"✅ Chapter **'{new_chap}'** added to {sub}.\nGo back to Admin Panel to add questions.")
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
    
    q_data = {
        "question": poll.question,
        "options": [o.text for o in poll.options],
        "correct": poll.correct_option_id
    }

    if cat == "BSEB":
        db["questions"]["BSEB"][sub].append(q_data)
        count = len(db["questions"]["BSEB"][sub])
    else: # NEET
        chap = context.user_data.get('adm_chap')
        db["questions"]["NEET"][sub][chap].append(q_data)
        count = len(db["questions"]["NEET"][sub][chap])

    save_db(db)
    await update.message.reply_text(f"✅ Saved! Total in this section: {count}")

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    if user_id == OWNER_ID and doc.file_name == 'backup.json':
        file = await doc.get_file()
        await file.download_to_drive(DB_FILE)
        global db
        db = load_db()
        await update.message.reply_text("♻️ **Database Restored Successfully!**")

# --- GROUP HANDLERS (Time Managed) ---
async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    title = update.effective_chat.title
    
    # Store title for Admin UI
    if chat_id not in db["groups"]:
        db["groups"][chat_id] = {"mode": None, "interval": 600, "title": title}
    else:
        db["groups"][chat_id]["title"] = title
    save_db(db)
    
    btns = [[InlineKeyboardButton("BSEB Mode", callback_data='g_set_BSEB')], [InlineKeyboardButton("NEET Mode", callback_data='g_set_NEET')]]
    await update.message.reply_text("📢 **Group Registered!**\nNow select which questions to run:", reply_markup=InlineKeyboardMarkup(btns))

async def set_group_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    chat_id = str(query.message.chat_id)
    mode = data.split('_')[2]
    
    if chat_id in db["groups"]:
        db["groups"][chat_id]["mode"] = mode
        save_db(db)
        await query.edit_message_text(f"✅ **Setup Complete!**\nMode: {mode}\nDefault Interval: 600s\nUse `/start_quiz` to begin.")
    else:
        await query.answer("Please /register first.")

async def start_group_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in db["groups"]:
        await update.message.reply_text("❌ Not registered. Use `/register` first.")
        return
    
    group_data = db["groups"][chat_id]
    mode = group_data.get("mode")
    interval = group_data.get("interval", 600) # Default 600s
    
    if not mode:
        await update.message.reply_text("❌ Mode not selected. Re-register to select mode.")
        return

    # Pass chat_id to job_queue (using job context)
    # Removing existing jobs to prevent duplicates
    current_jobs = context.job_queue.get_jobs_by_name(chat_id)
    for job in current_jobs:
        job.schedule_removal()
        
    context.job_queue.run_repeating(auto_group_quiz_job, interval=interval, first=5, name=chat_id, data=chat_id)
    await update.message.reply_text(f"🚀 **Quiz Cycle Started!**\nMode: {mode}\nInterval: {interval}s")

async def auto_group_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    group_data = db["groups"].get(chat_id)
    
    if not group_data: return

    mode = group_data["mode"]
    questions = get_random_questions(mode, count=1)
    
    if not questions:
        return # No Qs to send

    q = questions[0]
    try:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=q['question'],
            options=q['options'],
            correct_option_id=q['correct'],
            type='quiz',
            is_anonymous=False
        )
        if "current_polls" not in db: db["current_polls"] = {}
        db["current_polls"][str(msg.poll.id)] = {"cat": mode, "sub": "Mixed"}
    except Exception as e:
        logging.error(f"Group Quiz Error: {e}")

# --- STATS HANDLING ---
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = str(answer.poll_id)
    user_id = str(answer.user.id)
    if poll_id in db.get("current_polls", {}):
        p_data = db["current_polls"][poll_id]
        cat = p_data.get("cat")
        sub = p_data.get("sub")
        if str(user_id) not in db["stats"]: db["stats"][str(user_id)] = {}
        if cat not in db["stats"][str(user_id)]: db["stats"][str(user_id)][cat] = {}
        if sub not in db["stats"][str(user_id)][cat]: db["stats"][str(user_id)][cat][sub] = {"correct": 0, "total": 0}
        db["stats"][str(user_id)][cat][sub]["total"] += 1
        save_db(db)

async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    stats = db["stats"].get(user_id, {})
    if not stats:
        await query.answer("No stats yet!", show_alert=True)
        return
    text = "📊 **Your Performance**\n\n"
    for cat in stats:
        text += f"🔹 **{cat}**\n"
        for sub in stats[cat]:
            data = stats[cat][sub]
            text += f"   - {sub}: {data['total']} Attempts\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]), parse_mode='Markdown')

async def req_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await context.bot.send_message(chat_id=OWNER_ID, text=f"🔔 **Admin Request**\nUser: {user.first_name}\nID: `{user.id}`\nUsername: @{user.username}")
    await query.answer("Request sent to Owner!", show_alert=True)

async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['adm_mode'] = None
    context.user_data['awaiting_chap_name'] = False
    await update.message.reply_text("❌ Operation Cancelled.")

if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("❌ TOKEN MISSING")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("register", register_group))
        app.add_handler(CommandHandler("start_quiz", start_group_quiz))
        app.add_handler(CommandHandler("cancel", cancel_op))
        # Updated Regex Pattern for Handlers
        app.add_handler(CallbackQueryHandler(handle_menus, pattern='^main_menu|menu_(bseb|neet|settings)|bseb_|neet_|time_|count_|view_stats|req_admin'))
        app.add_handler(CallbackQueryHandler(handle_admin, pattern='^menu_admin|adm_|add_admin|get_backup|restore_prompt|mng_grp_|set_int_'))
        app.add_handler(CallbackQueryHandler(set_group_mode, pattern='^g_set_'))
        app.add_handler(MessageHandler(filters.POLL, handle_poll_upload))
        app.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_file_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        print("Bot is Live!")
        app.run_polling()
