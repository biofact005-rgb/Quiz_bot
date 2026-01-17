import logging
import asyncio
import random
import json
import os
from datetime import datetime, time, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
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

# LINKS
LINK_MAIN_CHANNEL = "@errorkid_05" # Bot must be admin here
LINK_BSEB_GROUP = "https://t.me/+orJX4chtA_EzNzk1"
LINK_NEET_GROUP = "https://t.me/+wttsW0EvoRZhMzNl"
LINK_BOT_UPDATES = "https://t.me/NM_INFO_1"

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
    return random.sample(all_q, min(len(all_q), count))

# --- VERIFICATION LOGIC ---
async def check_main_channel_join(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=LINK_MAIN_CHANNEL, user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
    except Exception as e:
        # logging.error(f"Verification Error: {e}") 
        # Fail safe: If bot is not admin or error, assume verified to not block users
        return False 
    return False

# --- START & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fname = update.effective_user.first_name
    
    # 1. MAIN CHANNEL VERIFICATION
    is_joined = await check_main_channel_join(user_id, context)
    if not is_joined:
        btns = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{LINK_MAIN_CHANNEL.replace('@','')}")],
            [InlineKeyboardButton("✅ I have Joined", callback_data='verify_main_start')]
        ]
        await update.message.reply_text(
            f"⛔ **Access Denied!**\n\nHello {fname}, Bot use karne ke liye hamara Main Channel join karein.",
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return

    # Init Stats
    if str(user_id) not in db["stats"]:
        db["stats"][str(user_id)] = {}
        save_db(db)

    # UI Selection
    buttons = [
        [InlineKeyboardButton("📚 BSEB (Bihar Board)", callback_data='chk_bseb')],
        [InlineKeyboardButton("🩺 NEET (Medical)", callback_data='chk_neet')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='menu_settings'),
         InlineKeyboardButton("❓ Help", callback_data='menu_help')],
        [InlineKeyboardButton("🔔 Bot Updates", url=LINK_BOT_UPDATES)]
    ]
    
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🛡️ Admin Panel", callback_data='menu_admin')])
        
    intro_text = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨  **W E L C O M E** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👋 **Hello {fname}!**\n"
        f"🚀 Select a Category to start quiz.\n\n"
        f"👇 _Tap a button below:_"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(intro_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')
    else:
        await update.message.reply_text(intro_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')

# --- STOP COMMAND ---
async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data.pop('quiz_queue', None)
    context.user_data.pop('current_poll_id', None)
    jobs = context.job_queue.get_jobs_by_name(str(user_id))
    for job in jobs: job.schedule_removal()
    await update.message.reply_text("🛑 **Quiz Stopped.**\nUse /start to go back to main menu.")

# --- HELP MENU ---
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ **How to Use This Bot**\n\n"
        "1. **Start Quiz:** Select BSEB or NEET from the menu.\n"
        "2. **Stop Quiz:** Send `/stop` anytime to end a running quiz.\n"
        "3. **Groups:** Add bot to your group, make admin, and type `/register`.\n"
        "4. **Stats:** Check your performance in Settings.\n\n"
        "💡 *Tip: Answer quickly to move to the next question instantly!*"
    )
    btn = [[InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btn), parse_mode='Markdown')

# --- MENU HANDLERS ---
async def handle_menus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # VERIFICATION HANDLERS
    if data == 'verify_main_start':
        is_joined = await check_main_channel_join(user_id, context)
        if is_joined:
            await query.answer("✅ Verified!", show_alert=True)
            await start(update, context)
        else:
            await query.answer("❌ You haven't joined yet!", show_alert=True)
        return

    # CHECK BSEB JOIN
    if data == 'chk_bseb':
        if context.user_data.get('verified_bseb'):
            data = 'menu_bseb'
        else:
            btns = [
                [InlineKeyboardButton("📢 Join BSEB Group", url=LINK_BSEB_GROUP)],
                [InlineKeyboardButton("✅ Joined", callback_data='ver_bseb_confirm')]
            ]
            await query.edit_message_text("🔒 **Unlock BSEB Section**\nPlease join our BSEB group to proceed.", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
            return

    if data == 'ver_bseb_confirm':
        context.user_data['verified_bseb'] = True
        await query.answer("✅ Access Granted!")
        data = 'menu_bseb'

    # CHECK NEET JOIN
    if data == 'chk_neet':
        if context.user_data.get('verified_neet'):
            data = 'menu_neet'
        else:
            btns = [
                [InlineKeyboardButton("📢 Join NEET Group", url=LINK_NEET_GROUP)],
                [InlineKeyboardButton("✅ Joined", callback_data='ver_neet_confirm')]
            ]
            await query.edit_message_text("🔒 **Unlock NEET Section**\nPlease join our NEET group to proceed.", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')
            return

    if data == 'ver_neet_confirm':
        context.user_data['verified_neet'] = True
        await query.answer("✅ Access Granted!")
        data = 'menu_neet'

    # BSEB MENU
    if data == 'menu_bseb':
        btns = []
        subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
        for sub in subjects:
            btns.append([InlineKeyboardButton(f"📖 {sub}", callback_data=f'bseb_sub_{sub}')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
        await query.edit_message_text("📚 **BSEB Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # NEET MENU
    elif data == 'menu_neet':
        btns = [
            [InlineKeyboardButton("⚛️ Physics", callback_data='neet_sub_Physics')],
            [InlineKeyboardButton("🧪 Chemistry", callback_data='neet_sub_Chemistry')],
            [InlineKeyboardButton("🧬 Biology", callback_data='neet_sub_Biology')],
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await query.edit_message_text("🩺 **NEET Section**\n\nSelect Subject:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    # SETTINGS
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

    elif data == 'menu_help':
        await show_help(update, context)

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
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("⏱️ **Select Time per Question:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ask_count(query):
    counts = [15, 30, 45, 60, 90, 120]
    btns = [InlineKeyboardButton(f"📝 {c} Qs", callback_data=f"count_{c}") for c in counts]
    keyboard = [btns[i:i+2] for i in range(0, len(btns), 2)]
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await query.edit_message_text("🔢 **How many questions?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- NEW QUIZ ENGINE (INSTANT NEXT) ---
async def start_private_quiz(query, context):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    chap = context.user_data.get('quiz_chap', None)
    time_limit = context.user_data.get('quiz_time')
    requested_count = context.user_data.get('quiz_count')

    questions = get_random_questions(cat, sub, chap, requested_count)
    if not questions:
        await query.edit_message_text("❌ No questions found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
        return

    context.user_data['quiz_queue'] = questions
    context.user_data['quiz_index'] = 0
    context.user_data['quiz_meta'] = {'c': cat, 's': sub, 't': time_limit}
    
    await query.edit_message_text(f"🚀 **Starting Quiz!**\nQs: {len(questions)}\n\n_Sending first question..._", parse_mode='Markdown')
    await send_next_question(query.message.chat_id, context)

async def send_next_question(chat_id, context):
    try:
        queue = context.user_data.get('quiz_queue', [])
        idx = context.user_data.get('quiz_index', 0)
        meta = context.user_data.get('quiz_meta', {})

        if idx >= len(queue):
            await context.bot.send_message(chat_id, "🏁 **Quiz Completed!**\nCheck stats in Settings.")
            context.user_data.pop('quiz_queue', None)
            return

        q = queue[idx]
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=q['question'],
            options=q['options'],
            correct_option_id=q['correct'],
            type='quiz',
            open_period=meta['t'],
            is_anonymous=False
        )
        context.user_data['current_poll_id'] = str(msg.poll.id)
        context.user_data['quiz_index'] = idx + 1
        context.job_queue.run_once(force_next_job, meta['t'], chat_id=chat_id, name=str(chat_id), data=chat_id)
        
        if "current_polls" not in db: db["current_polls"] = {}
        db["current_polls"][str(msg.poll.id)] = {"cat": meta['c'], "sub": meta['s'], "user": chat_id}
        
    except Exception as e:
        logging.error(f"Send Q Error: {e}")

async def force_next_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    await send_next_question(chat_id, context)

# --- ADMIN PANEL ---
async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    if data == 'menu_admin':
        btns = [
            [InlineKeyboardButton("➕ Add to BSEB", callback_data='adm_sel_BSEB')],
            [InlineKeyboardButton("➕ Add to NEET", callback_data='adm_sel_NEET')],
            [InlineKeyboardButton("⏱️ Manage Groups (ON/OFF)", callback_data='adm_manage_groups')],
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await query.edit_message_text("🛡️ **Admin Panel**", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data == 'adm_manage_groups':
        if not db["groups"]:
            await query.answer("No active groups found.", show_alert=True)
            return
        btns = []
        for gid, info in db["groups"].items():
            title = info.get('title', f"Group {gid}")
            # Mark status with emoji
            status = "🟢" if context.job_queue.get_jobs_by_name(gid) else "🔴"
            btns.append([InlineKeyboardButton(f"{status} {title}", callback_data=f'mng_grp_{gid}')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await query.edit_message_text("⏱️ **Group Control Center**\nSelect a Group to Manage:", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data.startswith('mng_grp_'):
        gid = data.split('_')[2]
        context.user_data['target_grp'] = gid
        
        group_info = db["groups"].get(gid, {})
        curr_int = group_info.get("interval", 600)
        title = group_info.get("title", "Unknown")
        mode = group_info.get("mode", "Not Set")
        
        # Check if running
        is_running = bool(context.job_queue.get_jobs_by_name(gid))
        status_text = "🟢 Active" if is_running else "🔴 Stopped"
        
        toggle_btn_text = "🔴 Turn OFF" if is_running else "🟢 Turn ON"
        toggle_action = "stop" if is_running else "start"
        
        btns = [
            [InlineKeyboardButton(toggle_btn_text, callback_data=f'toggle_grp_{toggle_action}_{gid}')],
            [InlineKeyboardButton("⏱️ Set Time Gap (Interval)", callback_data='edit_int_grp')],
            [InlineKeyboardButton("⬅️ Back", callback_data='adm_manage_groups')]
        ]
        
        await query.edit_message_text(
            f"⚙️ **Managing Group:** {title}\n"
            f"📂 Mode: `{mode}`\n"
            f"📡 Status: **{status_text}**\n"
            f"⏳ Time Gap: `{curr_int}s` (Bot stays silent for this time)\n\n"
            f"👇 **Control Panel:**",
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode='Markdown'
        )

    # TOGGLE ON/OFF
    elif data.startswith('toggle_grp_'):
        action, gid = data.split('_')[1], data.split('_')[2]
        
        if action == "stop":
            # Remove jobs
            jobs = context.job_queue.get_jobs_by_name(gid)
            for job in jobs: job.schedule_removal()
            await query.answer("🔴 Quiz Stopped for this group!")
        else:
            # Start job
            group_data = db["groups"].get(gid)
            if not group_data or not group_data.get("mode"):
                await query.answer("❌ Mode not set! Group admin must use /register.", show_alert=True)
            else:
                interval = group_data.get("interval", 600)
                # Remove existing if any
                jobs = context.job_queue.get_jobs_by_name(gid)
                for job in jobs: job.schedule_removal()
                
                context.job_queue.run_repeating(auto_group_quiz_job, interval=interval, first=5, name=gid, data=gid)
                await query.answer("🟢 Quiz Started!", show_alert=True)
        
        # Refresh Dashboard
        await asyncio.sleep(0.5) # Wait for job update
        # Re-trigger manager view
        data = f"mng_grp_{gid}"
        # We recursively call handle_admin logic for mng_grp (simplified by sending new message or editing)
        # For simplicity, we just show a text confirmation and a back button to refresh
        btns = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data=f'mng_grp_{gid}')]]
        await query.edit_message_text(f"✅ **Action Complete!**\nQuiz is now {'ACTIVE' if action=='start' else 'STOPPED'}.", reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

    elif data == 'edit_int_grp':
        gid = context.user_data.get('target_grp')
        context.user_data['awaiting_grp_interval'] = True
        await query.edit_message_text(
            f"⌨️ **Set Custom Time Gap**\nTarget Group ID: `{gid}`\n\n"
            f"👇 **Type the time in seconds.**\n(e.g., `300` for 5 mins, `3600` for 1 hour)\n"
            f"_Bot will wait this long between questions._",
            parse_mode='Markdown'
        )

    # ... (Add Questions Logic) ...
    elif data.startswith('adm_sel_'):
        cat = data.split('_')[2]
        context.user_data['adm_cat'] = cat
        if cat == "BSEB":
            btns = []
            for sub in db["questions"]["BSEB"]:
                btns.append([InlineKeyboardButton(sub, callback_data=f'adm_sub_{sub}')])
            btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
            await query.edit_message_text("Select BSEB Subject:", reply_markup=InlineKeyboardMarkup(btns))
        else:
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
        else:
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

    elif data == 'add_admin_prompt':
        await query.edit_message_text("🆔 Send the **User ID** to promote to Admin.", parse_mode='Markdown')
        context.user_data['awaiting_admin_id'] = True
    elif data == 'get_backup':
        if os.path.exists(DB_FILE):
             await context.bot.send_document(chat_id=update.effective_chat.id, document=open(DB_FILE, 'rb'), filename="backup.json")
        else: await query.answer("No DB found.")
    elif data == 'restore_prompt':
        await query.edit_message_text("📤 **Send the `backup.json` file now** to restore.", parse_mode='Markdown')

# --- MESSAGE HANDLERS ---
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    # 1. Custom Group Interval Input
    if context.user_data.get('awaiting_grp_interval'):
        gid = context.user_data.get('target_grp')
        try:
            val = int(text.strip())
            if gid and gid in db["groups"]:
                db["groups"][gid]["interval"] = val
                save_db(db)
                
                # Restart job if running to apply new time
                if context.job_queue.get_jobs_by_name(gid):
                    for job in context.job_queue.get_jobs_by_name(gid): job.schedule_removal()
                    context.job_queue.run_repeating(auto_group_quiz_job, interval=val, first=5, name=gid, data=gid)
                    msg_add = "\n🔄 **Job Restarted with new time!**"
                else:
                    msg_add = ""
                
                await update.message.reply_text(f"✅ Time Gap set to **{val} seconds**.{msg_add}")
            else:
                await update.message.reply_text("❌ Group not found.")
        except:
            await update.message.reply_text("❌ Invalid number. Please enter integer seconds (e.g., 100).")
        
        context.user_data['awaiting_grp_interval'] = False
        return

    # 2. Add Admin
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

    # 3. New Chapter
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

# --- GROUP HANDLERS ---
async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    title = update.effective_chat.title
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
    interval = group_data.get("interval", 600)
    if not mode:
        await update.message.reply_text("❌ Mode not selected.")
        return
    current_jobs = context.job_queue.get_jobs_by_name(chat_id)
    for job in current_jobs: job.schedule_removal()
    context.job_queue.run_repeating(auto_group_quiz_job, interval=interval, first=5, name=chat_id, data=chat_id)
    await update.message.reply_text(f"🚀 **Quiz Cycle Started!**\nMode: {mode}\nInterval: {interval}s")

async def auto_group_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    group_data = db["groups"].get(chat_id)
    if not group_data: return
    mode = group_data["mode"]
    questions = get_random_questions(mode, count=1)
    if not questions: return
    q = questions[0]
    try:
        msg = await context.bot.send_poll(chat_id=chat_id, question=q['question'], options=q['options'], correct_option_id=q['correct'], type='quiz', is_anonymous=False)
        if "current_polls" not in db: db["current_polls"] = {}
        db["current_polls"][str(msg.poll.id)] = {"cat": mode, "sub": "Mixed"}
    except Exception as e:
        logging.error(f"Group Quiz Error: {e}")

# --- STATS & INSTANT NEXT LOGIC ---
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = str(answer.poll_id)
    user_id = str(answer.user.id)
    
    # 1. Update Stats
    if poll_id in db.get("current_polls", {}):
        p_data = db["current_polls"][poll_id]
        cat = p_data.get("cat")
        sub = p_data.get("sub")
        if str(user_id) not in db["stats"]: db["stats"][str(user_id)] = {}
        if cat not in db["stats"][str(user_id)]: db["stats"][str(user_id)][cat] = {}
        if sub not in db["stats"][str(user_id)][cat]: db["stats"][str(user_id)][cat][sub] = {"correct": 0, "total": 0}
        db["stats"][str(user_id)][cat][sub]["total"] += 1
        save_db(db)

    # 2. Instant Next Question (Private)
    if str(user_id) == str(user_id):
        current_active_poll = context.user_data.get('current_poll_id')
        if current_active_poll == poll_id:
            chat_id = user_id
            jobs = context.job_queue.get_jobs_by_name(str(chat_id))
            for job in jobs: job.schedule_removal()
            await send_next_question(chat_id, context)

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
        app.add_handler(CommandHandler("stop", stop_quiz))
        app.add_handler(CommandHandler("register", register_group))
        app.add_handler(CommandHandler("start_quiz", start_group_quiz))
        app.add_handler(CommandHandler("cancel", cancel_op))
        
        # Callbacks
        app.add_handler(CallbackQueryHandler(handle_menus, pattern='^main_menu|menu_(bseb|neet|settings|help)|chk_|ver_|verify_|bseb_|neet_|time_|count_|view_stats|req_admin'))
        app.add_handler(CallbackQueryHandler(handle_admin, pattern='^menu_admin|adm_|add_admin|get_backup|restore_prompt|mng_grp_|toggle_grp_|edit_int_grp'))
        app.add_handler(CallbackQueryHandler(set_group_mode, pattern='^g_set_'))
        
        # Messages
        app.add_handler(MessageHandler(filters.POLL, handle_poll_upload))
        app.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_file_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        print("Bot is Live!")
        app.run_polling()
