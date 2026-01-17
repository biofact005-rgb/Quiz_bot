import logging
import asyncio
import random
import json
import os
from datetime import datetime, time, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# Import error correctly
from telegram.error import BadRequest 
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
IST = timezone(timedelta(hours=5, minutes=30))

# --- LINKS ---
LINK_MAIN_CHANNEL = "https://t.me/errorkid_05"
LINK_BSEB_GROUP = "https://t.me/+orJX4chtA_EzNzk1"
LINK_NEET_GROUP = "https://t.me/+wttsW0EvoRZhMzNl"
LINK_BOT_UPDATE = "https://t.me/NM_INFO_1"

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Global Live User Tracking
active_users = {}

# --- DATABASE HANDLING ---
def load_db():
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
                if "groups" not in data: data["groups"] = default_db["groups"]
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
    active_users[user_id] = datetime.now()

def get_live_count():
    cutoff = datetime.now() - timedelta(minutes=10)
    return sum(1 for time in active_users.values() if time > cutoff)

def get_random_questions(category, subject, chapters_list, count=10):
    all_q = []
    for chap in chapters_list:
        qs = db["questions"][category][subject].get(chap, [])
        all_q.extend(qs)
    if not all_q: return []
    return random.sample(all_q, min(len(all_q), count))

# --- SAFE EDIT MESSAGE ---
async def safe_edit_message(query, text, reply_markup, parse_mode='Markdown'):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass 
        else:
            logging.error(f"Edit Error: {e}")

# --- VERIFICATION GATEKEEPER ---
async def send_join_prompt(update, link, callback_success):
    btns = [
        [InlineKeyboardButton("🚀 Join Channel", url=link)],
        [InlineKeyboardButton("✅ I have Joined", callback_data=callback_success)]
    ]
    text = "⚠️ **Verification Required!**\n\nYou must join our channel to access this section."
    
    if update.callback_query:
        await safe_edit_message(update.callback_query, text, InlineKeyboardMarkup(btns))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='Markdown')

# --- START & MENUS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_live_user(user_id)
    
    # Start Verification
    if not context.user_data.get('verified_start'):
        btns = [
            [InlineKeyboardButton("🚀 Join Official Channel", url=LINK_MAIN_CHANNEL)],
            [InlineKeyboardButton("✅ Verified Access", callback_data='verify_start_done')]
        ]
        await update.message.reply_text(
            "🔒 **Access Locked**\n\nPlease join our official channel to use this bot.",
            reply_markup=InlineKeyboardMarkup(btns),
            parse_mode='Markdown'
        )
        return

    await show_main_menu(update, context)

async def show_main_menu(update, context):
    user_id = update.effective_user.id
    fname = update.effective_user.first_name
    
    if str(user_id) not in db["stats"]:
        db["stats"][str(user_id)] = {}
        save_db(db)

    buttons = [
        [InlineKeyboardButton("📚 BSEB (Bihar Board)", callback_data='gate_bseb')],
        [InlineKeyboardButton("🩺 NEET (Medical)", callback_data='gate_neet')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='menu_settings'),
         InlineKeyboardButton("ℹ️ Help", callback_data='show_help')],
        [InlineKeyboardButton("🔔 Bot Updates", url=LINK_BOT_UPDATE)]
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
        f"🩺 **NEET:** Medical Entrance\n\n"
        f"👇 _Tap a button below to begin:_"
    )
    
    if update.callback_query:
        await safe_edit_message(update.callback_query, intro_text, InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(intro_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='Markdown')

# --- MENU HANDLERS ---
async def handle_menus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    update_live_user(user_id)
    
    # --- VERIFICATION GATES ---
    if data == 'verify_start_done':
        context.user_data['verified_start'] = True
        await show_main_menu(update, context)
        return

    if data == 'gate_bseb':
        if context.user_data.get('verified_bseb'):
            await open_bseb_menu(query)
        else:
            await send_join_prompt(update, LINK_BSEB_GROUP, 'verify_bseb_done')
        return

    if data == 'verify_bseb_done':
        context.user_data['verified_bseb'] = True
        await open_bseb_menu(query)
        return

    if data == 'gate_neet':
        if context.user_data.get('verified_neet'):
            await open_neet_menu(query)
        else:
            await send_join_prompt(update, LINK_NEET_GROUP, 'verify_neet_done')
        return

    if data == 'verify_neet_done':
        context.user_data['verified_neet'] = True
        await open_neet_menu(query)
        return

    # --- MAIN MENUS ---
    if data == 'show_help':
        text = (
            "ℹ️ **How to Use:**\n\n"
            "1. **Select Category:** Choose BSEB or NEET.\n"
            "2. **Select Subject:** Pick your subject.\n"
            "3. **Select Mode:** \n"
            "   - **Chapter Wise:** Pick one chapter.\n"
            "   - **Mix Mode:** Select multiple chapters.\n"
            "4. **Start Quiz:** Choose time and question count.\n"
            "5. **Controls:**\n"
            "   - `/stop` - Stop quiz immediately.\n"
            "   - Tap option to skip timer (Instant Next)."
        )
        await safe_edit_message(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]]))

    elif data == 'main_menu':
        await show_main_menu(update, context)

    # ... (Quiz Selection) ...
    elif data.startswith('sel_sub_'):
        parts = data.split('_')
        cat = parts[2]
        sub = parts[3]
        context.user_data['quiz_cat'] = cat
        context.user_data['quiz_sub'] = sub
        
        btns = [
            [InlineKeyboardButton("📖 Chapter Wise", callback_data='mode_single')],
            [InlineKeyboardButton("🔀 Custom Mix", callback_data='mode_mix')],
            [InlineKeyboardButton("⬅️ Back", callback_data='gate_bseb' if cat=='BSEB' else 'gate_neet')]
        ]
        await safe_edit_message(query, f"📂 **{cat} > {sub}**\n\nSelect Quiz Mode:", InlineKeyboardMarkup(btns))

    elif data == 'mode_single':
        await show_chapter_selection(query, context, multi=False)
    elif data == 'mode_mix':
        context.user_data['selected_chapters'] = []
        await show_chapter_selection(query, context, multi=True)
    elif data.startswith('tgl_'):
        chap = data.split('tgl_')[1]
        sel = context.user_data.get('selected_chapters', [])
        if chap in sel: sel.remove(chap)
        else: sel.append(chap)
        context.user_data['selected_chapters'] = sel
        await show_chapter_selection(query, context, multi=True)
    elif data == 'confirm_mix':
        sel = context.user_data.get('selected_chapters', [])
        if not sel: 
            await query.answer("Select at least one!", show_alert=True)
            return
        context.user_data['final_chapters'] = sel
        await ask_time(query)
    elif data.startswith('sng_'):
        chap = data.split('sng_')[1]
        context.user_data['final_chapters'] = [chap]
        await ask_time(query)
    elif data.startswith('time_'):
        context.user_data['quiz_time'] = int(data.split('_')[1])
        await ask_count(query)
    elif data.startswith('count_'):
        context.user_data['quiz_count'] = int(data.split('_')[1])
        await start_private_quiz(query, context)

async def open_bseb_menu(query):
    btns = []
    subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
    for sub in subjects:
        btns.append([InlineKeyboardButton(f"📖 {sub}", callback_data=f'sel_sub_BSEB_{sub}')])
    btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
    await safe_edit_message(query, "📚 **BSEB Section**\n\nSelect Subject:", InlineKeyboardMarkup(btns))

async def open_neet_menu(query):
    btns = [
        [InlineKeyboardButton("⚛️ Physics", callback_data='sel_sub_NEET_Physics')],
        [InlineKeyboardButton("🧪 Chemistry", callback_data='sel_sub_NEET_Chemistry')],
        [InlineKeyboardButton("🧬 Biology", callback_data='sel_sub_NEET_Biology')],
        [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
    ]
    await safe_edit_message(query, "🩺 **NEET Section**\n\nSelect Subject:", InlineKeyboardMarkup(btns))

async def show_chapter_selection(query, context, multi):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    chapters_data = db["questions"][cat].get(sub, {})
    
    if not chapters_data:
        await safe_edit_message(query, f"❌ No chapters in {sub}.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]]))
        return

    btns = []
    selected = context.user_data.get('selected_chapters', [])
    for chap, q_list in chapters_data.items():
        q_count = len(q_list)
        if multi:
            icon = "✅" if chap in selected else "⬜"
            btns.append([InlineKeyboardButton(f"{icon} {chap} [{q_count}]", callback_data=f'tgl_{chap}')])
        else:
            btns.append([InlineKeyboardButton(f"📄 {chap} [{q_count}]", callback_data=f'sng_{chap}')])

    if multi: btns.append([InlineKeyboardButton(f"▶️ Start ({len(selected)})", callback_data='confirm_mix')])
    btns.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    
    mode = "Custom Mix" if multi else "Chapter Wise"
    await safe_edit_message(query, f"📖 **{sub} - {mode}**", InlineKeyboardMarkup(btns))

async def ask_time(query):
    times = [15, 30, 45, 60]
    btns = [InlineKeyboardButton(f"⏱️ {t}s", callback_data=f"time_{t}") for t in times]
    k = [btns[i:i+2] for i in range(0,len(btns),2)]
    k.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await safe_edit_message(query, "⏱️ **Select Time:**", InlineKeyboardMarkup(k))

async def ask_count(query):
    counts = [15, 30, 45, 60, 90, 120]
    btns = [InlineKeyboardButton(f"📝 {c} Qs", callback_data=f"count_{c}") for c in counts]
    k = [btns[i:i+2] for i in range(0,len(btns),2)]
    k.append([InlineKeyboardButton("❌ Cancel", callback_data='main_menu')])
    await safe_edit_message(query, "🔢 **Question Count:**", InlineKeyboardMarkup(k))

# --- QUIZ FLOW ---
async def start_private_quiz(query, context):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    chaps = context.user_data.get('final_chapters')
    time_limit = context.user_data.get('quiz_time')
    req_count = context.user_data.get('quiz_count')

    questions = get_random_questions(cat, sub, chaps, req_count)
    if not questions:
        await safe_edit_message(query, "❌ No questions found.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
        return

    context.user_data['stop_quiz'] = False
    
    msg_text = f"🚀 **Starting Quiz!**\n📂 {cat} > {sub}\n❓ Qs: {len(questions)}\n\n_Use /stop to end quiz anytime._"
    await safe_edit_message(query, msg_text, None) 
    
    context.job_queue.run_once(run_quiz_sequence, 1, chat_id=query.message.chat_id, data={
        'q': questions, 't': time_limit, 'u': query.from_user.id, 'c': cat, 's': sub
    })

async def run_quiz_sequence(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    questions = job_data['q']
    time_limit = job_data['t']
    chat_id = context.job.chat_id
    user_id = job_data['u']
    
    for i, q in enumerate(questions):
        if context.application.user_data[user_id].get('stop_quiz'):
            await context.bot.send_message(chat_id, "🛑 **Quiz Stopped.**")
            return

        future = asyncio.Future()
        context.application.user_data[user_id]['answer_future'] = future

        try:
            msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=f"[{i+1}/{len(questions)}] {q['question']}",
                options=q['options'],
                correct_option_id=q['correct'],
                type='quiz',
                open_period=time_limit,
                is_anonymous=False
            )
            
            if "current_polls" not in db: db["current_polls"] = {}
            db["current_polls"][str(msg.poll.id)] = {"cat": job_data['c'], "sub": job_data['s'], "user": user_id}

            try:
                await asyncio.wait_for(future, timeout=time_limit)
                await asyncio.sleep(0.5) 
            except asyncio.TimeoutError:
                pass

        except Exception as e:
            logging.error(f"Quiz Error: {e}")
            break
            
        context.application.user_data[user_id].pop('answer_future', None)

    await context.bot.send_message(chat_id, "🏁 **Quiz Completed!** Check stats in Settings.")
    save_db(db)

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stop_quiz'] = True
    await update.message.reply_text("🛑 Stopping...")

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
            [InlineKeyboardButton("⏱️ Manage Groups", callback_data='adm_manage_groups')],
            [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
        ]
        await safe_edit_message(query, f"🛡️ **Admin Panel**\nLive Users: {get_live_count()}", InlineKeyboardMarkup(btns))

    elif data == 'adm_manage_groups':
        if not db["groups"]:
            await query.answer("No groups.", show_alert=True)
            return
        btns = [[InlineKeyboardButton(f"📢 {v.get('title','Grp')}", callback_data=f'mng_grp_{k}')] for k, v in db["groups"].items()]
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await safe_edit_message(query, "⚙️ **Select Group:**", InlineKeyboardMarkup(btns))

    elif data.startswith('mng_grp_'):
        gid = data.split('_')[2]
        context.user_data['target_grp'] = gid
        grp = db["groups"][gid]
        status = "✅ ON" if grp.get("active", True) else "🔴 OFF"
        interval = grp.get("interval", 600)
        
        btns = [
            [InlineKeyboardButton(f"Power: {status}", callback_data=f'tgl_pwr_{gid}')],
            [InlineKeyboardButton(f"⏱️ Interval: {interval}s", callback_data='ask_cust_int')],
            [InlineKeyboardButton("⬅️ Back", callback_data='adm_manage_groups')]
        ]
        await safe_edit_message(query, f"⚙️ **Settings for Group:**\nID: `{gid}`", InlineKeyboardMarkup(btns))

    elif data.startswith('tgl_pwr_'):
        gid = data.split('_')[2]
        curr = db["groups"][gid].get("active", True)
        db["groups"][gid]["active"] = not curr
        save_db(db)
        await handle_admin(update, context)

    elif data == 'ask_cust_int':
        await safe_edit_message(query, "⌨️ **Type the Interval in seconds** (e.g. 120, 600):", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_interval'] = True
    
    # Owner Commands
    elif data == 'add_admin_prompt':
        await safe_edit_message(query, "🆔 **Send the User ID** to promote to Admin.", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='menu_settings')]]))
        context.user_data['awaiting_admin_id'] = True
    
    elif data == 'get_backup':
        if os.path.exists(DB_FILE):
             await context.bot.send_document(chat_id=update.effective_chat.id, document=open(DB_FILE, 'rb'), filename="backup.json")
        else:
            await query.answer("No DB found.")

    elif data == 'restore_prompt':
        await safe_edit_message(query, "📤 **Send the `backup.json` file now** to restore.", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='menu_settings')]]))

    # Add Questions
    elif data.startswith('adm_sel_'):
        cat = data.split('_')[2]
        context.user_data['adm_cat'] = cat
        subjects = db["questions"][cat].keys()
        btns = [[InlineKeyboardButton(sub, callback_data=f'adm_sub_{sub}')] for sub in subjects]
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await safe_edit_message(query, f"Select {cat} Subject:", InlineKeyboardMarkup(btns))
        
    elif data.startswith('adm_sub_'):
        sub = data.split('_')[2]
        context.user_data['adm_sub'] = sub
        cat = context.user_data.get('adm_cat')
        chapters = db["questions"][cat].get(sub, {}).keys()
        btns = [[InlineKeyboardButton(chap, callback_data=f'adm_chap_{chap}')] for chap in chapters]
        btns.append([InlineKeyboardButton("➕ Add New Chapter", callback_data='adm_new_chap')])
        btns.append([InlineKeyboardButton("⬅️ Back", callback_data='menu_admin')])
        await safe_edit_message(query, f"Select Chapter:", InlineKeyboardMarkup(btns))

    elif data == 'adm_new_chap':
        await safe_edit_message(query, "⌨️ **Type Chapter Name:**", InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_chap_name'] = True
        
    elif data.startswith('adm_chap_'):
        chap = data.split('_')[2]
        context.user_data['adm_chap'] = chap
        context.user_data['adm_mode'] = 'active'
        sub = context.user_data.get('adm_sub')
        await safe_edit_message(query, f"📂 **Active:** {context.user_data['adm_cat']} > {chap}\n\n👇 **Forward Quiz Polls.**\n/cancel to stop.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f'adm_sub_{sub}')]]))

# --- SETTINGS HANDLER ---
async def show_settings(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    btns = [[InlineKeyboardButton("📊 Stats", callback_data='view_stats')], 
            [InlineKeyboardButton("✋ Request Admin", callback_data='req_admin')]]
            
    if user_id == OWNER_ID:
        btns.append([InlineKeyboardButton("➕ Add Admin", callback_data='add_admin_prompt')])
        btns.append([InlineKeyboardButton("💾 Backup", callback_data='get_backup')])
        btns.append([InlineKeyboardButton("♻️ Restore", callback_data='restore_prompt')])

    btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
    await safe_edit_message(query, "⚙️ **Settings**", InlineKeyboardMarkup(btns))

async def view_stats(update, context):
    query = update.callback_query
    uid = str(query.from_user.id)
    stats = db["stats"].get(uid, {})
    text = "📊 **Stats**\n"
    if not stats: text += "No data."
    else:
        for c, s_data in stats.items():
            text += f"\n🔹 {c}:\n"
            for s, d in s_data.items(): text += f"   - {s}: {d['total']}\n"
    await safe_edit_message(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]))

async def req_admin(update, context):
    user = update.effective_user
    await context.bot.send_message(OWNER_ID, f"🔔 **Admin Request**\nUser: {user.first_name}\nID: `{user.id}`\nUser: @{user.username}")
    await update.callback_query.answer("Request sent to Owner!", show_alert=True)

# --- INPUT HANDLER ---
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_admin_id') and user_id == OWNER_ID:
        try:
            new_admin = int(text)
            if new_admin not in db["admins"]:
                db["admins"].append(new_admin)
                save_db(db)
                await update.message.reply_text(f"✅ User {new_admin} is now an Admin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]))
            else:
                await update.message.reply_text("Already an admin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]))
        except:
            await update.message.reply_text("❌ Invalid ID.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='menu_settings')]]))
        context.user_data['awaiting_admin_id'] = False
        return

    if context.user_data.get('awaiting_interval') and is_admin(user_id):
        try:
            sec = int(text)
            gid = context.user_data.get('target_grp')
            if gid and gid in db["groups"]:
                db["groups"][gid]["interval"] = sec
                save_db(db)
                await update.message.reply_text(f"✅ Interval set to {sec}s.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='adm_manage_groups')]]))
            else:
                await update.message.reply_text("❌ Group Error.")
        except:
            await update.message.reply_text("❌ Invalid number.")
        context.user_data['awaiting_interval'] = False
        return

    if context.user_data.get('awaiting_chap_name') and is_admin(user_id):
        new_chap = text.strip()
        cat = context.user_data.get('adm_cat')
        sub = context.user_data.get('adm_sub')
        if new_chap not in db["questions"][cat][sub]:
            db["questions"][cat][sub][new_chap] = []
            save_db(db)
            await update.message.reply_text(f"✅ Chapter '{new_chap}' added.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f'adm_sub_{sub}')]]))
        context.user_data['awaiting_chap_name'] = False
        return

# --- POLL UPLOAD ---
async def handle_poll_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) or context.user_data.get('adm_mode') != 'active': return
    
    poll = update.message.poll
    cat = context.user_data.get('adm_cat')
    sub = context.user_data.get('adm_sub')
    chap = context.user_data.get('adm_chap')
    
    q_data = {"question": poll.question, "options": [o.text for o in poll.options], "correct": poll.correct_option_id}
    db["questions"][cat][sub][chap].append(q_data)
    save_db(db)
    await update.message.reply_text(f"✅ Saved! Total: {len(db['questions'][cat][sub][chap])}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f'adm_sub_{sub}')]]))

# --- GROUP AUTOMATION ---
async def register_group(update, context):
    chat_id = str(update.effective_chat.id)
    if chat_id not in db["groups"]: 
        db["groups"][chat_id] = {"title": update.effective_chat.title, "mode": None, "interval": 600, "active": True}
    save_db(db)
    await update.message.reply_text("✅ Registered!")

async def start_group_quiz(update, context):
    chat_id = str(update.effective_chat.id)
    if chat_id not in db["groups"]: return
    if not db["groups"][chat_id].get("active", True):
        await update.message.reply_text("🔴 Quiz OFF.")
        return
    interval = db["groups"][chat_id]["interval"]
    context.job_queue.run_repeating(auto_group_job, interval=interval, first=5, data=chat_id, name=chat_id)
    await update.message.reply_text(f"🚀 Started! {interval}s")

async def auto_group_job(context):
    chat_id = context.job.data
    grp = db["groups"].get(chat_id)
    if not grp or not grp.get("active", True): return
    # Placeholder for group logic

async def cancel_op(update, context):
    context.user_data['adm_mode'] = None
    context.user_data['awaiting_chap_name'] = False
    context.user_data['awaiting_interval'] = False
    context.user_data['awaiting_admin_id'] = False
    await update.message.reply_text("❌ Cancelled.")

if __name__ == '__main__':
    keep_alive()
    if not TOKEN: print("❌ TOKEN MISSING")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stop", stop_quiz_command))
        app.add_handler(CommandHandler("register", register_group))
        app.add_handler(CommandHandler("start_quiz", start_group_quiz))
        app.add_handler(CommandHandler("cancel", cancel_op))

        # --- HANDLERS ---
        app.add_handler(CallbackQueryHandler(handle_admin, pattern='^menu_admin|adm_|mng_grp_|tgl_pwr_|ask_cust_int|add_admin|get_backup|restore_prompt'))
        app.add_handler(CallbackQueryHandler(show_settings, pattern='^menu_settings'))
        app.add_handler(CallbackQueryHandler(view_stats, pattern='^view_stats'))
        app.add_handler(CallbackQueryHandler(req_admin, pattern='^req_admin'))
        app.add_handler(CallbackQueryHandler(handle_menus, pattern='^main_menu|gate_|verify_|menu_(bseb|neet)|sel_sub_|mode_|tgl_|confirm_mix|sng_|time_|count_|show_help'))

        app.add_handler(MessageHandler(filters.POLL, handle_poll_upload))
        app.add_handler(MessageHandler(filters.Document.MimeType("application/json"), handle_file_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        
        print("Bot is Live!")
        app.run_polling()
