import logging
import asyncio
import random
import json
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler, PollAnswerHandler
)

# ==========================================
# 1. WEB SERVER (REPLIT/RENDER KEEP ALIVE)
# ==========================================
web_app = Flask('')

@web_app.route('/')
def home():
    return "Bot is Running! 24/7"

def run():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. CONFIGURATION
# ==========================================
TOKEN = os.getenv('TOKEN') 
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
DB_FILE = 'database.json'

IDS = {
    "MAIN": "@errorkid_05", 
    "BSEB": -1002398369446
}
LINKS = {
    "MAIN": "https://t.me/errorkid_05",
    "BSEB": "https://t.me/+orJX4chtA_EzNzk1",
    "UPDATE": "https://t.me/NM_INFO_1"
}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ==========================================
# 3. DATABASE FUNCTIONS
# ==========================================
def load_db():
    default_db = {
        "questions": {
            "BSEB": {
                "Hindi-Gadya": {}, "Hindi-Padya": {}, "Hindi-Grammar": {},
                "English-Prose": {}, "English-Poetry": {}, "English-Grammar": {},
                "Maths": {}, "Biology": {}, "Chemistry": {}, "Physics": {}
            }
        },
        "admins": [OWNER_ID],
        "stats": {},
        "user_data": {},
        "all_users": [],
        "current_polls": {},
        "maintenance_mode": False 
    }

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                
                if "questions" not in data: data["questions"] = default_db["questions"]
                if "BSEB" not in data["questions"]: data["questions"]["BSEB"] = default_db["questions"]["BSEB"]
                if "maintenance_mode" not in data: data["maintenance_mode"] = False
                
                base_subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
                for sub in base_subjects:
                    pyq_key = f"{sub}-PYQ"
                    yt_key = f"{sub}-YouTube"
                    if pyq_key not in data["questions"]["BSEB"]: data["questions"]["BSEB"][pyq_key] = {}
                    if yt_key not in data["questions"]["BSEB"]: data["questions"]["BSEB"][yt_key] = {}

                for k, v in default_db.items():
                    if k not in data: data[k] = v
                return data
        except Exception as e:
            print(f"DB Load Error: {e}")
            return default_db
    
    base_subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
    for sub in base_subjects:
        default_db["questions"]["BSEB"][f"{sub}-PYQ"] = {}
        default_db["questions"]["BSEB"][f"{sub}-YouTube"] = {}
        
    return default_db

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except: pass

db = load_db()
save_db(db)

# ==========================================
# 4. HELPER FUNCTIONS
# ==========================================
def is_admin(user_id):
    return user_id in db["admins"] or user_id == OWNER_ID

def esc(text):
    if not text: return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_random_questions(category, subject, chapters_list, count=10):
    all_q = []
    if not chapters_list:
        chapters_data = db["questions"].get(category, {}).get(subject, {})
        for chap in chapters_data:
            all_q.extend(chapters_data[chap])
    else:
        for chap in chapters_list:
            qs = db["questions"].get(category, {}).get(subject, {}).get(chap, [])
            all_q.extend(qs)
    
    if not all_q: return []
    unique_q = list({q['question']: q for q in all_q}.values())
    return random.sample(unique_q, min(len(unique_q), count))

def get_mistake_questions(user_id, category, subject):
    try:
        user_mistakes = db["user_data"].get(str(user_id), {}).get("mistakes", {}).get(category, {})
        all_mistakes = []
        targets = []
        
        if category == "BSEB" and subject == "Hindi":
            targets = ["Hindi-Gadya", "Hindi-Padya", "Hindi-Grammar", "Hindi-PYQ", "Hindi-YouTube"]
        elif category == "BSEB" and subject == "English":
            targets = ["English-Prose", "English-Poetry", "English-Grammar", "English-PYQ", "English-YouTube"]
        elif subject in ["Physics", "Chemistry", "Biology", "Maths"]:
             targets = [subject, f"{subject}-PYQ", f"{subject}-YouTube"]
        elif subject != "Any":
            targets = [subject]
        
        if targets:
            for t in targets:
                qs = user_mistakes.get(t, [])
                all_mistakes.extend(qs)
            return all_mistakes
        
        for sub, qs in user_mistakes.items():
            all_mistakes.extend(qs)
        return all_mistakes
    except: return []

async def check_membership(chat_id, user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if member.status in ['left', 'kicked', 'banned']: return False
        return True
    except: return False

async def check_gate(query, context, gid, link, success_cb, cb_data):
    if await check_membership(gid, query.from_user.id, context):
        await success_cb(query, context)
    else:
        btns = [[InlineKeyboardButton("🚀 Join Group", url=link)], [InlineKeyboardButton("✅ I have Joined", callback_data=cb_data)]]
        await query.edit_message_text("⚠️ <b>Verification Required!</b>\nJoin group to access.", reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')

async def send_force_join_msg(update, link):
    btns = [[InlineKeyboardButton("🚀 Join Channel", url=link), InlineKeyboardButton("✅ I have Joined", callback_data="recheck_main")]]
    text = "🚫 <b>Access Denied!</b>\n\nYou must join our main channel to use this bot."
    if update.callback_query: 
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')
    else: 
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')

async def send_main_menu_direct(context, chat_id, user_id):
    try:
        btns = [[InlineKeyboardButton("📚 BSEB (Bihar Board)", callback_data='gate_bseb')], [InlineKeyboardButton("⚙️ Menu", callback_data='main_menu')]]
        await context.bot.send_message(chat_id, "🏠 <b>Main Menu:</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')
    except: pass

async def safe_edit_message(query, text, reply_markup=None):
    try:
        if reply_markup:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await query.edit_message_text(text, parse_mode='HTML')
    except BadRequest: pass

async def send_maintenance_msg(update):
    msg = (
        "━━━━━━━━━━━━━━━━━━\n"
        "🚧  <b>UNDER MAINTENANCE</b>  🚧\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ The bot is currently being updated to serve you better.\n"
        "⏳ Please wait for some time.\n\n"
        "<i>We will be back soon!</i> 🚀"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode='HTML')
    elif update.message:
        await update.message.reply_text(msg, parse_mode='HTML')

# ==========================================
# 5. CORE QUIZ ENGINE
# ==========================================
async def run_quiz_sequence(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    job_data = job.data 
    chat_id = job.chat_id
    user_id = job_data['u']
    
    if not context.user_data and context.user_data is not {}: return
    if 'futures' not in context.user_data: context.user_data['futures'] = {}
        
    context.user_data['quiz_active'] = True

    for i, q in enumerate(job_data['q']):
        if context.user_data.get('stop_quiz_flag'): 
            await context.bot.send_message(chat_id, "🛑 <b>Quiz Aborted!</b>\nReturning to menu...", parse_mode='HTML')
            await send_main_menu_direct(context, chat_id, user_id)
            context.user_data['quiz_active'] = False
            context.user_data['stop_quiz_flag'] = False
            if context.user_data: context.user_data.pop('futures', None) 
            return

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        poll_id = None
        
        try:
            safe_options = [str(opt).replace('<', '').replace('>', '') for opt in q['options']]
            msg = await context.bot.send_poll(
                chat_id=chat_id, 
                question=f"[{i+1}/{len(job_data['q'])}] {esc(q['question'])}", 
                options=safe_options, 
                correct_option_id=q['correct'], 
                type='quiz', 
                open_period=job_data['t'], 
                is_anonymous=False,
                protect_content=True  # <--- FORWARDING DISABLED HERE
            )
            poll_id = str(msg.poll.id)
            context.user_data['futures'][poll_id] = future
            
            if "current_polls" not in db: db["current_polls"] = {}
            db["current_polls"][poll_id] = {
                "cat": job_data['c'], "sub": job_data['s'], "user": user_id, "mode": job_data['mode'], "q_data": q
            }
            
            try: await asyncio.wait_for(future, timeout=job_data['t'] + 2)
            except: pass
            await asyncio.sleep(0.5) 
        except Exception as e: 
            print(f"Quiz Loop Error: {e}")
            await asyncio.sleep(2)
            continue
        
        if poll_id and poll_id in context.user_data['futures']:
             context.user_data['futures'].pop(poll_id, None)

    await context.bot.send_message(chat_id, "🏁 <b>Quiz Completed!</b>\nCheck 'Improve Mistakes' if you got any wrong.", parse_mode='HTML')
    context.user_data['quiz_active'] = False
    if context.user_data: context.user_data.pop('futures', None)
    save_db(db)
    await send_main_menu_direct(context, chat_id, user_id)

async def start_private_quiz(query, context):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    time_limit = context.user_data.get('quiz_time', 30)
    req_count = context.user_data.get('quiz_count', 10)
    mode = context.user_data.get('quiz_mode', 'normal')
    
    context.user_data['stop_quiz_flag'] = False
    context.user_data['quiz_active'] = True
    
    questions = []
    
    if mode == 'improve':
        mistakes = get_mistake_questions(query.from_user.id, cat, sub)
        if not mistakes:
            await safe_edit_message(query, "🎉 <b>No mistakes found!</b>\nGood job!", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
            return
        random.shuffle(mistakes)
        questions = mistakes[:req_count]
        await safe_edit_message(query, esc(f"🚀 Improving Mistakes...\nTopic: {sub}\nCount: {len(questions)}"), None)
    else:
        chaps = context.user_data.get('final_chapters')
        questions = get_random_questions(cat, sub, chaps, req_count)
        disp_sub = sub.split('-')[-1] if '-' in sub else sub
        if not questions: 
            await safe_edit_message(query, esc("❌ No questions available."), InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu", callback_data='main_menu')]]))
            return
        await safe_edit_message(query, esc(f"🚀 Starting Quiz...\nTopic: {disp_sub}"), None)
    
    data_packet = {'q': questions, 't': time_limit, 'u': query.from_user.id, 'c': cat, 's': sub, 'mode': mode, 'stop': False}
    context.job_queue.run_once(run_quiz_sequence, 1, chat_id=query.message.chat_id, user_id=query.from_user.id, data=data_packet)

# ==========================================
# 6. POLL ANSWER HANDLER
# ==========================================
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update.poll_answer: return
        poll_id = str(update.poll_answer.poll_id)
        user_id = update.poll_answer.user.id
        selected = update.poll_answer.option_ids[0]

        if context.user_data and 'futures' in context.user_data:
            future = context.user_data['futures'].pop(poll_id, None)
            if future and not future.done():
                try: future.set_result(True)
                except: pass
                try: await context.bot.stop_poll(update.effective_chat.id, update.poll_answer.poll_id)
                except: pass

        if "current_polls" in db and poll_id in db["current_polls"]:
            p_data = db["current_polls"][poll_id]
            cat, sub, mode, q = p_data['cat'], p_data['sub'], p_data['mode'], p_data['q_data']
            uid_str = str(user_id)
            corr = q['correct']
            
            if uid_str not in db["stats"]: db["stats"][uid_str] = {}
            if cat not in db["stats"][uid_str]: db["stats"][uid_str][cat] = {}
            if sub not in db["stats"][uid_str][cat]: db["stats"][uid_str][cat][sub] = {'total':0, 'correct':0, 'wrong':0}
            
            stats_entry = db["stats"][uid_str][cat][sub]
            if 'correct' not in stats_entry: stats_entry['correct'] = 0
            if 'wrong' not in stats_entry: stats_entry['wrong'] = 0

            stats_entry['total'] += 1
            if selected == corr:
                stats_entry['correct'] += 1
                if mode == 'improve':
                    mistakes_list = db["user_data"].get(uid_str, {}).get("mistakes", {}).get(cat, {}).get(sub, [])
                    new_list = [mq for mq in mistakes_list if mq['question'] != q['question']]
                    db["user_data"][uid_str]["mistakes"][cat][sub] = new_list
            else:
                stats_entry['wrong'] += 1
                if mode == 'normal':
                    if uid_str not in db["user_data"]: db["user_data"][uid_str] = {}
                    if "mistakes" not in db["user_data"][uid_str]: db["user_data"][uid_str]["mistakes"] = {}
                    if cat not in db["user_data"][uid_str]["mistakes"]: db["user_data"][uid_str]["mistakes"][cat] = {}
                    if sub not in db["user_data"][uid_str]["mistakes"][cat]: db["user_data"][uid_str]["mistakes"][cat][sub] = []
                    mistakes_list = db["user_data"][uid_str]["mistakes"][cat][sub]
                    if not any(mq['question'] == q['question'] for mq in mistakes_list): mistakes_list.append(q)
            
            db["current_polls"].pop(poll_id, None)
            save_db(db)
    except Exception as e: print(f"Poll Answer Error: {e}")

# ==========================================
# 7. MENUS & CALLBACKS
# ==========================================
async def show_main_menu(update, context):
    user_id = update.effective_user.id
    fname = esc(update.effective_user.first_name)
    if "all_users" not in db: db["all_users"] = []
    if user_id not in db["all_users"]: db["all_users"].append(user_id); save_db(db)
    if str(user_id) not in db["stats"]: db["stats"][str(user_id)] = {}

    btns = [
        [InlineKeyboardButton("📚 BSEB (Bihar Board)", callback_data='gate_bseb')],
        [InlineKeyboardButton("🚀 Improve Mistakes", callback_data='menu_improve')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='menu_settings'), InlineKeyboardButton("ℹ️ Help", callback_data='show_help')]
    ]
    if user_id == OWNER_ID: btns.append([InlineKeyboardButton("👑 Owner Panel", callback_data='menu_owner')])
    if is_admin(user_id): btns.append([InlineKeyboardButton("🛡️ Content Admin", callback_data='menu_admin')])
    
    text = (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👋 <b>Namaste {fname}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Select Your Goal:</b>\n"
        f"👇 <i>Choose an option below to start:</i>"
    )
    if update.callback_query: await safe_edit_message(update.callback_query, text, InlineKeyboardMarkup(btns))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')

async def show_help(update, context):
    query = update.callback_query
    txt = (
        "━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ <b>HELP & GUIDE</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "1. <b>Start Quiz:</b> Select a Category > Subject > Source (Book/PYQ/YT).\n"
        "2. <b>PYQ:</b> Directly tests past questions.\n"
        "3. <b>YouTube:</b> Tests based on specific channels/videos.\n"
        "4. <b>Admin:</b> Only owners can add questions.\n\n"
        "👨‍💻 <b>Developer:</b> @errorkid_05"
    )
    await safe_edit_message(query, txt, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]]))

async def show_owner_panel(update, context):
    m_status = "🟢 ON" if db.get("maintenance_mode") else "🔴 OFF"
    btns = [
        [InlineKeyboardButton("➕ Add Admin", callback_data='add_admin_prompt'), InlineKeyboardButton("📜 Admin List", callback_data='view_admin_list')],
        [InlineKeyboardButton("💾 Backup", callback_data='get_backup'), InlineKeyboardButton("♻️ Restore", callback_data='restore_prompt')],
        [InlineKeyboardButton(f"Maintenance: {m_status}", callback_data='toggle_maint')],
        [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
    ]
    await safe_edit_message(update.callback_query, "👑 <b>Owner Control Panel</b>", InlineKeyboardMarkup(btns))

async def show_settings(update, context):
    query = update.callback_query
    btns = [
        [InlineKeyboardButton("📊 Stats", callback_data='view_stats')],
        [InlineKeyboardButton("🔔 Bot Updates", url=LINKS["UPDATE"])],
        [InlineKeyboardButton("✋ Request Admin", callback_data='req_admin')],
        [InlineKeyboardButton("⬅️ Back", callback_data='main_menu')]
    ]
    await safe_edit_message(query, "⚙️ <b>Settings</b>", InlineKeyboardMarkup(btns))

    
async def handle_admin(update, context):
    query = update.callback_query
    data = query.data
    
    # 1. Main Menu
    if data == 'menu_admin':
        btns = [
            [InlineKeyboardButton("➕ Add BSEB", callback_data='adm_main_BSEB')],
            [InlineKeyboardButton("🗑️ Delete Data", callback_data='adm_del_menu')],
            [InlineKeyboardButton("📢 Broadcast", callback_data='adm_broadcast_prompt')],
            [InlineKeyboardButton("Back", callback_data='main_menu')]
        ]
        await safe_edit_message(query, "🛡️ <b>Content Admin Panel</b>", InlineKeyboardMarkup(btns))
        return

    # 2. Select Subject
    if data == 'adm_main_BSEB':
        subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
        btns = [[InlineKeyboardButton(s, callback_data=f'adm_deep_{s}')] for s in subjects]
        btns.append([InlineKeyboardButton("Back", callback_data='menu_admin')])
        await safe_edit_message(query, "📂 <b>BSEB > Select Subject:</b>", InlineKeyboardMarkup(btns))
        return

    # 3. Handle Subject Click
    if data.startswith('adm_deep_'):
        sub = data.split('_')[2] 
        if sub == "Hindi":
            opts = ["Hindi-Gadya", "Hindi-Padya", "Hindi-Grammar", "Hindi-PYQ", "Hindi-YouTube"]
        elif sub == "English":
            opts = ["English-Prose", "English-Poetry", "English-Grammar", "English-PYQ", "English-YouTube"]
        else:
            opts = [sub, f"{sub}-PYQ", f"{sub}-YouTube"]
            
        btns = []
        for o in opts:
            label = o
            if o == sub: label = f"{sub} (Book)" 
            btns.append([InlineKeyboardButton(label, callback_data=f'adm_sub_{o}')])
            
        btns.append([InlineKeyboardButton("Back", callback_data='adm_main_BSEB')])
        await safe_edit_message(query, f"📂 <b>{sub} > Select Type:</b>", InlineKeyboardMarkup(btns))
        return

    # 4. Admin Tools (List, Backup, etc.)
    if data == 'view_admin_list':
        msg = "👮‍♂️ <b>Admin List:</b>\nLoading details..."
        await safe_edit_message(query, msg, None)
        final_txt = "👮‍♂️ <b>Admin List:</b>\n"
        for aid in db["admins"]:
            try:
                chat = await context.bot.get_chat(aid)
                name = chat.username if chat.username else chat.first_name
                final_txt += f"👤 @{esc(name)} ({aid})\n"
            except: final_txt += f"👤 Unknown User ({aid})\n"
        await safe_edit_message(query, final_txt, InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_owner')]]))
        return
        
    if data == 'restore_prompt':
        await safe_edit_message(query, "📤 <b>Send database.json:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_owner')]]))
        return
    if data == 'adm_broadcast_prompt':
        await safe_edit_message(query, "📢 <b>Send broadcast message:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_broadcast_msg'] = True
        return

    # 5. Delete Menu
    if data == 'adm_del_menu':
        btns = [[InlineKeyboardButton("BSEB", callback_data='del_sel_BSEB')], [InlineKeyboardButton("Back", callback_data='menu_admin')]]
        await safe_edit_message(query, "🗑️ <b>Select Category:</b>", InlineKeyboardMarkup(btns))
        return
    
    if data.startswith(('del_sel_', 'adm_sel_')): 
        mode = 'del' if 'del' in data else 'adm'
        cat = data.split('_')[2]; context.user_data[f'{mode}_cat'] = cat
        # Safe get keys
        subs = sorted(list(db["questions"].get(cat, {}).keys()))
        btns = [[InlineKeyboardButton(s, callback_data=f'{mode}_sub_{s}')] for s in subs]
        btns.append([InlineKeyboardButton("Back", callback_data='menu_admin')])
        await safe_edit_message(query, f"📂 <b>{cat} > Select Subject:</b>", InlineKeyboardMarkup(btns))
        return

    # ==================================================================
    # 6. PAGINATION & LISTING LOGIC (UPDATED FOR FIX)
    # ==================================================================
    if data.startswith(('del_sub_', 'adm_sub_', 'pg_adm_', 'pg_del_')):
        mode = 'del' if 'del' in data else 'adm'
        
        # --- Determine Page & Subject ---
        page = 0
        if data.startswith('pg_'):
            # Format: pg_adm_PAGE_SUB...
            parts = data.split('_')
            page = int(parts[2])
            sub = "_".join(parts[3:]) 
        else:
            # First load
            sub = data.replace(f'{mode}_sub_', '')
            page = 0

        context.user_data[f'{mode}_sub'] = sub
        cat = context.user_data.get(f'{mode}_cat', 'BSEB') 
        context.user_data[f'{mode}_cat'] = cat 
        
        # Get all chapters/channels and sort them
        all_keys = sorted(list(db["questions"].get(cat, {}).get(sub, {}).keys()))
        
        ITEMS_PER_PAGE = 10
        total_items = len(all_keys)
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        if total_pages == 0: total_pages = 1
        
        # Slice for current page
        start_idx = page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        chaps = all_keys[start_idx:end_idx]
        
        btns = []
        if mode == 'del':
            for i, c in enumerate(chaps):
                global_idx = start_idx + i
                # Save mapping: Index -> Real Name
                context.user_data[f'del_chap_idx_{global_idx}'] = c
                # Send Index in callback to save bytes
                btns.append([InlineKeyboardButton(f"❌ {c}", callback_data=f'del_idx_{global_idx}')])
            title = f"🗑️ <b>Delete ({page+1}/{total_pages}):</b>"
        else:
            for i, c in enumerate(chaps):
                global_idx = start_idx + i
                context.user_data[f'adm_chap_idx_{global_idx}'] = c
                btns.append([InlineKeyboardButton(c, callback_data=f'adm_idx_{global_idx}')])
            
            btns.append([InlineKeyboardButton("➕ Add New", callback_data='adm_new_chap')])
            title = f"📂 <b>{sub} ({page+1}/{total_pages}):</b>"

        # --- Pagination Buttons ---
        pag_btns = []
        if page > 0:
            pag_btns.append(InlineKeyboardButton("⬅️ Prev", callback_data=f'pg_{mode}_{page-1}_{sub}'))
        if page < total_pages - 1:
            pag_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f'pg_{mode}_{page+1}_{sub}'))
        if pag_btns: btns.append(pag_btns)

        # --- Back Button ---
        back_data = 'menu_admin'
        if mode == 'adm' and cat == 'BSEB':
             # Try to go back to deep selection if possible
             base_sub = sub.split('-')[0]
             back_data = f'adm_deep_{base_sub}'
        elif mode == 'del':
             back_data = f'del_sel_{cat}'
        
        btns.append([InlineKeyboardButton("Back", callback_data=back_data)])
        
        await safe_edit_message(query, title, InlineKeyboardMarkup(btns))
        return

    # ==================================================================
    # 7. INDEX HANDLERS (UPDATED)
    # ==================================================================
    if data.startswith('del_idx_'):
        idx = int(data.split('_')[2])
        chap = context.user_data.get(f'del_chap_idx_{idx}')
        if not chap:
             await query.answer("❌ Item missing/refresh needed", show_alert=True)
             return
        context.user_data['del_chap'] = chap
        btns = [[InlineKeyboardButton("✅ YES, DELETE", callback_data='confirm_del')], [InlineKeyboardButton("❌ CANCEL", callback_data=f'del_sub_{context.user_data["del_sub"]}')]]
        await safe_edit_message(query, f"⚠️ <b>Delete '{chap}'?</b>", InlineKeyboardMarkup(btns))
        return

    if data.startswith('adm_idx_'):
        idx = int(data.split('_')[2])
        chap = context.user_data.get(f'adm_chap_idx_{idx}')
        if not chap:
             await query.answer("❌ Item missing/refresh needed", show_alert=True)
             return
        context.user_data['adm_chap'] = chap; context.user_data['adm_mode'] = 'active'
        await safe_edit_message(query, f"📂 <b>Active:</b> {chap}\n\n👇 <b>Forward Polls / Send .txt</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f'adm_sub_{context.user_data["adm_sub"]}')]]))
        return

    # 8. Confirmation & Input Actions
    if data == 'confirm_del':
        try:
            del db["questions"][context.user_data['del_cat']][context.user_data['del_sub']][context.user_data['del_chap']]
            save_db(db)
            await query.answer("✅ Deleted!", show_alert=True)
            # Return to list
            await handle_admin(update, context) # This reloads the menu
        except: await query.answer("❌ Error", show_alert=True)
        return

    if data == 'adm_new_chap':
        await safe_edit_message(query, "⌨️ <b>Type Name (Chapter/Channel):</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_chap_name'] = True
        return
async def master_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # 1. MAINTENANCE CHECK
    if db.get("maintenance_mode", False) and not is_admin(user_id):
        await query.answer("🚧 Bot is under maintenance!", show_alert=True)
        await send_maintenance_msg(update)
        return
    
    # 2. JOIN CHECK
    if data == 'recheck_main':
        if await check_membership(IDS["MAIN"], user_id, context): await show_main_menu(update, context)
        else: await query.answer("❌ Join First!", show_alert=True)
        return
    
    if data == 'gate_bseb': 
        gid = IDS["BSEB"]; link = LINKS["BSEB"]
        await check_gate(query, context, gid, link, open_bseb_menu, data)

    # 3. BASIC MENUS
    if data == 'main_menu': await show_main_menu(update, context)
    elif data == 'menu_settings': await show_settings(update, context)
    elif data == 'show_help': await show_help(update, context)
    
    # 4. ADMIN ROUTING (UPDATED FOR PAGINATION)
    elif data == 'menu_owner' or data in ['view_admin_list', 'restore_prompt', 'get_backup', 'toggle_maint']: 
        if data == 'menu_owner': await show_owner_panel(update, context)
        elif data == 'get_backup': save_db(db); await context.bot.send_document(query.message.chat_id, document=open(DB_FILE, 'rb'), filename="backup.json")
        elif data == 'toggle_maint':
            db["maintenance_mode"] = not db.get("maintenance_mode", False)
            save_db(db)
            await show_owner_panel(update, context)
        else: await handle_admin(update, context)
    elif data == 'add_admin_prompt':
        context.user_data['awaiting_admin_id'] = True
        await safe_edit_message(query, "⌨️ <b>Send User ID to add as Admin:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_owner')]]))
    
    # *** IMPORTANT: Include new tags (pg_, idx_) here ***
    elif data.startswith(('menu_admin', 'adm_', 'del_', 'confirm_del', 'pg_adm_', 'pg_del_')): 
        await handle_admin(update, context)
    
    # 5. IMPROVE MISTAKES
    elif data == 'menu_improve':
        btns = [[InlineKeyboardButton("BSEB", callback_data='imp_cat_BSEB')], [InlineKeyboardButton("Back", callback_data='main_menu')]]
        await safe_edit_message(query, "🎯 <b>Select Category:</b>", InlineKeyboardMarkup(btns))
    elif data.startswith('imp_cat_'):
        cat = data.split('_')[2]
        if cat == 'BSEB': subjects = ["Hindi", "English", "Maths", "Biology", "Chemistry", "Physics"]
        else: subjects = db["questions"].get(cat, {}).keys()
        btns = [[InlineKeyboardButton(f"📖 {s}", callback_data=f'imp_run_{cat}_{s}')] for s in subjects]
        btns.append([InlineKeyboardButton("Back", callback_data='menu_improve')])
        await safe_edit_message(query, f"🛠️ <b>Improve {cat} > Select Subject:</b>", InlineKeyboardMarkup(btns))
    elif data.startswith('imp_run_'):
        parts = data.split('_')
        cat, sub = parts[2], parts[3]
        mistakes = get_mistake_questions(query.from_user.id, cat, sub)
        if not mistakes:
            await query.answer("🎉 No mistakes found!", show_alert=True); return
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = sub; context.user_data['quiz_mode'] = 'improve' 
        await ask_time(query)

    # 6. SUBJECT SELECTION
    elif data == 'section_BSEB_Hindi': await open_bseb_hindi_sections(query, context)
    elif data == 'section_BSEB_English': await open_bseb_english_sections(query, context)

    elif data.startswith('ask_src_'):
        full_sub = data.replace("ask_src_", "")
        await ask_source_menu(query, context, full_sub)

    elif data.startswith('src_book_'):
        parts = data.split('_')
        cat, sub = parts[2], parts[3]
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = sub; context.user_data['quiz_mode'] = 'normal'
        context.user_data['is_youtube_mode'] = False
        await safe_edit_message(query, f"📚 <b>{sub.split('-')[-1]} (Book)</b>", get_book_btns())

    elif data.startswith('src_pyq_'):
        parts = data.split('_')
        cat, sub_base = parts[2], parts[3]
        pyq_key = f"{sub_base}-PYQ"
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = pyq_key; context.user_data['quiz_mode'] = 'normal'
        context.user_data['final_chapters'] = []
        if not check_q_exists(cat, pyq_key): 
            await query.answer("⚠️ Not uploaded yet!", show_alert=True); return
        await ask_time(query)

    elif data.startswith('src_yt_'):
        parts = data.split('_')
        cat, sub_base = parts[2], parts[3]
        yt_key = f"{sub_base}-YouTube"
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = yt_key; context.user_data['quiz_mode'] = 'normal'
        context.user_data['is_youtube_mode'] = True
        if not check_q_exists(cat, yt_key): 
            await query.answer("⚠️ No channels added!", show_alert=True); return
        btns = [[InlineKeyboardButton("▶️ Channel Wise (Single)", callback_data='mode_single')], [InlineKeyboardButton("🔀 Mix Channels", callback_data='mode_mix')], [InlineKeyboardButton("Back", callback_data='main_menu')]]
        await safe_edit_message(query, f"▶️ <b>{sub_base} > YouTube</b>", InlineKeyboardMarkup(btns))

    elif data.startswith('sel_sub_'): 
        parts = data.split('_', 3)
        cat = parts[2]; sub = parts[3]
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = sub; context.user_data['quiz_mode'] = 'normal'
        context.user_data['is_youtube_mode'] = False
        await safe_edit_message(query, f"📂 <b>{sub.split('-')[-1]}</b>", get_book_btns())
    
    # 7. CHAPTER SELECTION (UPDATED FOR PAGINATION)
    elif data == 'mode_single': await show_chapter_selection(query, context, multi=False, page=0)
    elif data == 'mode_mix': context.user_data['selected_chapters'] = []; await show_chapter_selection(query, context, multi=True, page=0)
    
    # Pagination Handlers
    elif data.startswith('pg_sng_'):
        page = int(data.split('_')[2])
        await show_chapter_selection(query, context, multi=False, page=page)
    elif data.startswith('pg_mix_'):
        page = int(data.split('_')[2])
        await show_chapter_selection(query, context, multi=True, page=page)

    # Index Handlers (Toggle)
    elif data.startswith('tgl_'):
        idx = int(data.split('_')[1])
        chap = context.user_data.get(f'chap_idx_{idx}')
        
        if chap:
            sel = context.user_data.get('selected_chapters', [])
            if chap in sel: sel.remove(chap)
            else: sel.append(chap)
            context.user_data['selected_chapters'] = sel
            
            # Stay on same page
            ITEMS_PER_PAGE = 10
            current_page = idx // ITEMS_PER_PAGE
            await show_chapter_selection(query, context, multi=True, page=current_page)
        else:
            await query.answer("⚠️ Please refresh menu", show_alert=True)

    elif data == 'confirm_mix':
        if not context.user_data.get('selected_chapters'): await query.answer("Select one!", show_alert=True); return
        context.user_data['final_chapters'] = context.user_data['selected_chapters']; await ask_time(query)
    
    # Index Handlers (Single)
    elif data.startswith('sng_'):
        idx = int(data.split('_')[1])
        chap = context.user_data.get(f'chap_idx_{idx}')
        if chap:
            context.user_data['final_chapters'] = [chap]
            await ask_time(query)
        else:
            await query.answer("⚠️ Please refresh menu", show_alert=True)

    # 8. QUIZ SETTINGS & STATS
    elif data.startswith('time_'): context.user_data['quiz_time'] = int(data.split('_')[1]); await ask_count(query)
    elif data.startswith('count_'): context.user_data['quiz_count'] = int(data.split('_')[1]); await start_private_quiz(query, context)
    
    elif data == 'view_stats': 
        uid = str(query.from_user.id); stats = db["stats"].get(uid, {})
        txt = "━━━━━━━━━━━━━━━━━━\n📊 <b>USER STATS</b>\n━━━━━━━━━━━━━━━━━━\n"
        if stats:
            for cat, subs in stats.items():
                txt += f"\n📂 <b>{cat}:</b>"
                for sub, data in subs.items():
                    d_sub = sub.split('-')[-1]
                    correct = data.get('correct', 0); wrong = data.get('wrong', 0); total = data.get('total', 0)
                    txt += f"\n  - {d_sub}: {total} Qs (✅{correct} | ❌{wrong})"
        else: txt += "\n❌ No data found."
        await safe_edit_message(query, txt, InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_settings')]]))
    elif data == 'req_admin': 
        await context.bot.send_message(OWNER_ID, f"User {query.from_user.id} requested admin."); await query.answer("Request Sent!")


            


# ==========================================
# 8. MENU LOGIC FUNCTIONS
# ==========================================
def get_book_btns():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📖 Chapter Wise", callback_data='mode_single')], [InlineKeyboardButton("🔀 Mix / Custom", callback_data='mode_mix')], [InlineKeyboardButton("Back", callback_data='main_menu')]])

def check_q_exists(cat, sub):
    return bool(db["questions"].get(cat, {}).get(sub))

async def open_bseb_menu(query, context):
    btns = [
        [InlineKeyboardButton("📖 Hindi", callback_data='section_BSEB_Hindi'), InlineKeyboardButton("📖 English", callback_data='section_BSEB_English')],
        [InlineKeyboardButton("🔢 Maths", callback_data='ask_src_BSEB_Maths'), InlineKeyboardButton("🧬 Biology", callback_data='ask_src_BSEB_Biology')],
        [InlineKeyboardButton("🧪 Chemistry", callback_data='ask_src_BSEB_Chemistry'), InlineKeyboardButton("⚛️ Physics", callback_data='ask_src_BSEB_Physics')],
        [InlineKeyboardButton("Back", callback_data='main_menu')]
    ]
    await safe_edit_message(query, "📚 <b>BSEB Subjects</b>", InlineKeyboardMarkup(btns))

async def open_bseb_hindi_sections(query, context):
    btns = [
        [InlineKeyboardButton("📝 गद्य खण्ड", callback_data='sel_sub_BSEB_Hindi-Gadya')],
        [InlineKeyboardButton("📜 पद्य खण्ड", callback_data='sel_sub_BSEB_Hindi-Padya')],
        [InlineKeyboardButton("🔤 व्याकरण", callback_data='sel_sub_BSEB_Hindi-Grammar')],
        [InlineKeyboardButton("🧩 PYQ", callback_data='src_pyq_BSEB_Hindi')],
        [InlineKeyboardButton("▶️ YouTube", callback_data='src_yt_BSEB_Hindi')],
        [InlineKeyboardButton("Back", callback_data='gate_bseb')]
    ]
    await safe_edit_message(query, "📚 <b>Hindi Sections:</b>", InlineKeyboardMarkup(btns))

async def open_bseb_english_sections(query, context):
    btns = [
        [InlineKeyboardButton("📝 Prose", callback_data='sel_sub_BSEB_English-Prose')],
        [InlineKeyboardButton("📜 Poetry", callback_data='sel_sub_BSEB_English-Poetry')],
        [InlineKeyboardButton("🔤 Grammar", callback_data='sel_sub_BSEB_English-Grammar')],
        [InlineKeyboardButton("🧩 PYQ", callback_data='src_pyq_BSEB_English')],
        [InlineKeyboardButton("▶️ YouTube", callback_data='src_yt_BSEB_English')],
        [InlineKeyboardButton("Back", callback_data='gate_bseb')]
    ]
    await safe_edit_message(query, "📚 <b>English Sections:</b>", InlineKeyboardMarkup(btns))

async def ask_source_menu(query, context, subject):
    real_sub = subject.replace("BSEB_", "") 
    btns = [
        [InlineKeyboardButton("📚 Book", callback_data=f'src_book_{subject}')],
        [InlineKeyboardButton("🧩 PYQ", callback_data=f'src_pyq_{subject}')],
        [InlineKeyboardButton("▶️ YouTube", callback_data=f'src_yt_{subject}')],
        [InlineKeyboardButton("⬅️ Back", callback_data='gate_bseb')]
    ]
    await safe_edit_message(query, f"📂 <b>{real_sub} > Select Source:</b>", InlineKeyboardMarkup(btns))

async def show_chapter_selection(query, context, multi, page=0):
    cat = context.user_data.get('quiz_cat')
    sub = context.user_data.get('quiz_sub')
    
    # Database Initialization Check
    if cat not in db["questions"] or sub not in db["questions"][cat]:
        if cat in db["questions"]: db["questions"][cat][sub] = {}
        save_db(db)
    
    chapters = db["questions"][cat][sub]
    disp_sub = sub.split('-')[-1]
    is_yt = context.user_data.get('is_youtube_mode', False)
    
    if not chapters: 
        await query.answer(f"⚠️ No {'Channels' if is_yt else 'Chapters'} available!", show_alert=True)
        return
        
    btns = []
    sel = context.user_data.get('selected_chapters', [])
    
    # 1. SORTING & PAGINATION LOGIC
    # Always sort keys to ensure index stays consistent
    all_chaps = sorted(list(chapters.items()), key=lambda x: x[0]) 
    
    ITEMS_PER_PAGE = 10 
    total_items = len(all_chaps)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    # Bounds check
    if page < 0: page = 0
    if page >= total_pages: page = total_pages - 1
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_page_chaps = all_chaps[start_idx:end_idx]
    
    # 2. GENERATE BUTTONS WITH INDEX MAPPING
    for i, (chap, qs) in enumerate(current_page_chaps):
        count = len(qs)
        global_idx = start_idx + i  # Unique ID for this chapter across all pages
        
        # SAVE MAPPING: Index -> Real Name (Crucial Step)
        context.user_data[f'chap_idx_{global_idx}'] = chap
        
        if multi:
            icon = "✅" if chap in sel else "⬜"
            # Callback data is now short: tgl_0, tgl_1, etc.
            btns.append([InlineKeyboardButton(f"{icon} {chap} [{count}]", callback_data=f'tgl_{global_idx}')])
        else:
            icon = "▶️" if is_yt else "📄"
            # Callback data is now short: sng_0, sng_1, etc.
            btns.append([InlineKeyboardButton(f"{icon} {chap} [{count}]", callback_data=f'sng_{global_idx}')])
            
    # 3. NAVIGATION BUTTONS
    pag_btns = []
    mode_prefix = 'mix' if multi else 'sng' # Used in master_callback_router to route pagination
    
    if page > 0:
        pag_btns.append(InlineKeyboardButton("⬅️ Prev", callback_data=f'pg_{mode_prefix}_{page-1}'))
    
    # Center Indicator
    pag_btns.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data='noop'))
    
    if page < total_pages - 1:
        pag_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f'pg_{mode_prefix}_{page+1}'))
    
    if len(all_chaps) > ITEMS_PER_PAGE:
        btns.append(pag_btns)
            
    # 4. ACTION BUTTONS
    if multi: 
        btns.append([InlineKeyboardButton(f"🚀 Start Quiz ({len(sel)})", callback_data='confirm_mix')])
        
    btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
    
    title = f"<b>Select {'Channel' if is_yt else 'Chapter'} ({disp_sub})</b>"
    await safe_edit_message(query, title, InlineKeyboardMarkup(btns))


            
async def ask_time(query):
    btns = [InlineKeyboardButton(f"{t}s", callback_data=f"time_{t}") for t in [15, 30, 45, 60]]
    await safe_edit_message(query, "⏱️ <b>Per Question Time:</b>", InlineKeyboardMarkup([btns, [InlineKeyboardButton("Cancel", callback_data='main_menu')]]))

async def ask_count(query):
    counts = [10, 20, 30, 50, 100, 150, 200, 300, 400, 500]
    btns = [[InlineKeyboardButton(f"{c} Qs", callback_data=f"count_{c}") for c in counts[i:i+3]] for i in range(0, len(counts), 3)]
    btns.append([InlineKeyboardButton("Cancel", callback_data='main_menu')])
    await safe_edit_message(query, "🔢 <b>Question Count:</b>", InlineKeyboardMarkup(btns))

# ==========================================
# 9. HANDLERS (COMMANDS)
# ==========================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message or not update.message.text: return
    user_id = update.effective_user.id
    text = update.message.text
    
    # MAINTENANCE CHECK (Allow admins)
    if db.get("maintenance_mode", False) and not is_admin(user_id):
        await send_maintenance_msg(update)
        return

    if context.user_data.get('awaiting_admin_id') and user_id == OWNER_ID:
        try:
            new_id = int(text)
            if new_id not in db["admins"]: db["admins"].append(new_id); save_db(db)
            await update.message.reply_text("✅ User Added")
        except: await update.message.reply_text("Invalid ID")
        context.user_data['awaiting_admin_id'] = False
        return
    
    if context.user_data.get('awaiting_chap_name') and is_admin(user_id):
        cat, sub = context.user_data['adm_cat'], context.user_data['adm_sub']
        if text not in db["questions"][cat][sub]: 
            db["questions"][cat][sub][text] = []
            save_db(db)
            await update.message.reply_text(f"✅ Created: '{text}'")
        context.user_data['awaiting_chap_name'] = False
        return

    if context.user_data.get('awaiting_broadcast_msg') and is_admin(user_id):
        users = db.get("all_users", [])
        if not users: users = list(map(int, db["stats"].keys()))
        await update.message.reply_text(f"⏳ Sending to {len(users)} users...")
        for uid in users:
            try: 
                await context.bot.send_message(uid, f"📢 <b>Announcement:</b>\n\n{esc(text)}", parse_mode='HTML')
                await asyncio.sleep(0.1)
            except: pass
        await update.message.reply_text("✅ Broadcast Done."); context.user_data['awaiting_broadcast_msg'] = False

async def handle_poll_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if context.user_data.get('adm_mode') != 'active': return
    poll = update.message.poll
    cat, sub, chap = context.user_data['adm_cat'], context.user_data['adm_sub'], context.user_data['adm_chap']
    q_data = {"question": poll.question, "options": [o.text for o in poll.options], "correct": poll.correct_option_id}
    db["questions"][cat][sub][chap].append(q_data); save_db(db); await update.message.reply_text("✅ Saved!")



async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    
    # Database/Backup Restore Logic
    if user_id == OWNER_ID and (doc.file_name == 'database.json' or doc.file_name == 'backup.json'):
        f = await doc.get_file()
        await f.download_to_drive(DB_FILE)
        global db
        db = load_db()
        await update.message.reply_text("♻️ DB Restored!")
        return

    # Text File Upload Logic (Questions Add karna)
    if is_admin(user_id) and doc.file_name.endswith('.txt'):
        f = await doc.get_file()
        content = await f.download_as_bytearray()
        text_data = content.decode('utf-8')
        
        cat, sub = context.user_data.get('adm_cat'), context.user_data.get('adm_sub')
        if not cat or not sub: 
            await update.message.reply_text("⚠️ Select Subject First!")
            return
            
        cur_chap = "General"
        count = 0
        
        # YEH HAI WO LOOP JO SAHI JAGAH HONA CHAHIYE
        for line in text_data.split('\n'):
            line = line.strip()
            if not line: continue
            
            # Chapter detect karna aur naam chhota karna
            if line.lower().startswith('chapter:'): 
                raw_chap = line.split(':', 1)[1].strip()
                cur_chap = raw_chap[:30]  # Crash fix: Limit name to 30 chars
                continue
            
            # Question parse karna
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 6:
                try:
                    q = {"question": parts[0], "options": parts[1:5], "correct": int(parts[-1])-1}
                    if cur_chap not in db["questions"][cat][sub]: 
                        db["questions"][cat][sub][cur_chap] = []
                    db["questions"][cat][sub][cur_chap].append(q)
                    count += 1
                except: pass
                
        save_db(db)
        await update.message.reply_text(f"✅ {count} Questions Imported!")


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('quiz_active'):
        await update.message.reply_text("⚠️ Koi quiz chal nahi raha hai.")
        await show_main_menu(update, context)
        return
    context.user_data['stop_quiz_flag'] = True
    if 'futures' in context.user_data:
        for poll_id, future in context.user_data['futures'].items():
            if not future.done(): future.cancel() 

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        if not context.args: 
            await update.message.reply_text("❌ Usage: /removeadmin <user_id>")
            return
        
        target_id = int(context.args[0])
        if target_id in db["admins"]:
            db["admins"].remove(target_id)
            save_db(db)
            await update.message.reply_text(f"✅ User ID {target_id} removed.")
        else:
            await update.message.reply_text("⚠️ User not in admin list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        user_id = update.effective_user.id
        uid_str = str(user_id)
        
        if uid_str not in db["user_data"]: db["user_data"][uid_str] = {}
        
        # MAINTENANCE CHECK (Allow admins)
        if db.get("maintenance_mode", False) and not is_admin(user_id):
            await send_maintenance_msg(update)
            return
        
        # 1. Force Join Check
        if not await check_membership(IDS["MAIN"], user_id, context):
            await send_force_join_msg(update, LINKS["MAIN"])
            return

        # 2. One-Time Intro Message Check
        if not db["user_data"][uid_str].get("seen_intro", False):
            intro_text = (
                "📢 <b>Introducing Our First Quiz Bot</b> 🎙\n\n"
                "We are excited to launch our new Quiz Bot, specially designed to help students practice effectively and improve their exam performance step by step.\n"
                "This bot focuses not only on asking questions, but also on helping you learn from your mistakes.\n"
                "Approx 5000+ question uploaded\n\n"
                "🤖 <b>How the Bot Works</b>\n"
                "After starting the bot, you will see two options:\n"
                "🔹 BSEB\n🔹 IMPROVE\n\n"
                "👉 Currently, the BSEB section is active with questions added.\n"
                "👉 The NEET section will be updated soon.\n\n"
                "📚 <b>Quiz Flow:</b>\n"
                "1️⃣ Choose BSEB\n"
                "2️⃣ Select your subject\n"
                "3️⃣ Choose one or multiple chapters\n"
                "4️⃣ Set the time limit\n"
                "5️⃣ Select the number of questions\n"
                "6️⃣ Start the quiz 🚀\n\n"
                "⭐ <b>Special Features</b> ⭐\n"
                "✅ <b>Chapter-wise & Multi-chapter Quizzes</b>\n"
                "You can attempt quizzes from a single chapter or combine multiple chapters in one quiz.\n\n"
                "✅ <b>Custom Quiz Settings</b>\n"
                "Choose your own time limit and number of questions according to your preparation level.\n\n"
                "✅ <b>Smart Practice Book (Very Important Feature)</b>\n"
                "Any question you answer incorrectly is automatically saved in your personal practice book.\n"
                "This allows you to:\n"
                "• Re-attempt only wrong questions\n"
                "• Focus on weak topics\n"
                "• Avoid repeating questions you already know\n"
                "• This feature is available on IMPROVE button\n\n"
                "📌 <b>Current Status</b>\n"
                "📚 Available Now: BSEB Quiz Section\n"
                "🚧 Coming Soon: NEET Quiz Section\n\n"
                "🚨🚨🚨🚨🚨🚨\n"
                "<b>IMPORTANT THINGS</b>\n"
                "/done - to stop quiz\n"
                "/start - if you don't find any button or in any crash situation\n"
                "🚨🚨🚨🚨🚨🚨"
            )
            
            db["user_data"][uid_str]["seen_intro"] = True
            save_db(db)
            
            await update.message.reply_text(intro_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Let's Start", callback_data='main_menu')]]))
            return

        await show_main_menu(update, context)

if __name__ == '__main__':
    keep_alive()
    if not TOKEN:
        print("❌ TOKEN MISSING")
    else:
        req = HTTPXRequest(connect_timeout=180.0, read_timeout=180.0)
        app = ApplicationBuilder().token(TOKEN).request(req).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("done", done_command))       
        app.add_handler(CommandHandler("removeadmin", remove_admin_command))
        app.add_handler(CallbackQueryHandler(master_callback_router))
        app.add_handler(MessageHandler(filters.POLL & filters.User(OWNER_ID), handle_poll_upload))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        print("✅ Bot is Live!")
        app.run_polling()
