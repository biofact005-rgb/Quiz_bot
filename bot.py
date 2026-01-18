import logging
import asyncio
import random
import json
import os
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
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
    "BSEB": -1002398369446, 
    "NEET": -1002792641130
}
LINKS = {
    "MAIN": "https://t.me/errorkid_05",
    "BSEB": "https://t.me/+orJX4chtA_EzNzk1",
    "NEET": "https://t.me/+wttsW0EvoRZhMzNl",
    "UPDATE": "https://t.me/NM_INFO_1"
}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ==========================================
# 3. DATABASE FUNCTIONS (FIXED)
# ==========================================
def load_db():
    # Base structure
    default_db = {
        "questions": {
            "BSEB": {
                "Hindi-Gadya": {}, "Hindi-Padya": {}, "Hindi-Grammar": {},
                "English-Prose": {}, "English-Poetry": {}, "English-Grammar": {},
                "Maths": {}, "Biology": {}, "Chemistry": {}, "Physics": {}
            },
            "NEET": {subj: {} for subj in ["Physics", "Chemistry", "Biology"]}
        },
        "admins": [OWNER_ID],
        "stats": {},
        "user_data": {},
        "all_users": [],
        "current_polls": {}
    }

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                
                # [FIX] Force ensure 'questions' key exists
                if "questions" not in data:
                    data["questions"] = default_db["questions"]
                
                # [FIX] Force ensure BSEB sub-keys exist (Critical for Vyakaran)
                if "BSEB" not in data["questions"]:
                    data["questions"]["BSEB"] = default_db["questions"]["BSEB"]
                else:
                    # Check for missing specific sections and add them
                    required_bseb = ["Hindi-Gadya", "Hindi-Padya", "Hindi-Grammar", 
                                   "English-Prose", "English-Poetry", "English-Grammar"]
                    for rk in required_bseb:
                        if rk not in data["questions"]["BSEB"]:
                            data["questions"]["BSEB"][rk] = {}
                
                # Merge other top-level keys
                for k, v in default_db.items():
                    if k not in data:
                        data[k] = v
                        
                return data
        except Exception as e:
            print(f"DB Load Error: {e}")
            
    return default_db

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except: pass

db = load_db()
# Immediately save to fix structure on disk
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
        cat_mistakes = db["user_data"].get(str(user_id), {}).get("mistakes", {}).get(category, {})
        all_mistakes = []
        
        # Combined logic for Improve
        targets = []
        if category == "BSEB" and subject == "Hindi":
            targets = ["Hindi-Gadya", "Hindi-Padya", "Hindi-Grammar"]
        elif category == "BSEB" and subject == "English":
            targets = ["English-Prose", "English-Poetry", "English-Grammar"]
        elif subject != "Any":
            targets = [subject]
        
        if targets:
            for t in targets:
                qs = cat_mistakes.get(t, [])
                all_mistakes.extend(qs)
            return all_mistakes
            
        for sub, qs in cat_mistakes.items():
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
        btns = [[InlineKeyboardButton("📚 BSEB", callback_data='gate_bseb')], [InlineKeyboardButton("🩺 NEET", callback_data='gate_neet')], [InlineKeyboardButton("⚙️ Menu", callback_data='main_menu')]]
        await context.bot.send_message(chat_id, "🏠 <b>Main Menu:</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')
    except: pass

async def safe_edit_message(query, text, reply_markup=None):
    try:
        if reply_markup:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await query.edit_message_text(text, parse_mode='HTML')
    except BadRequest as e:
        print(f"Edit Failed: {e}")

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
                is_anonymous=False
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
        [InlineKeyboardButton("🩺 NEET (Medical)", callback_data='gate_neet')],
        [InlineKeyboardButton("🚀 Improve Mistakes", callback_data='menu_improve')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='menu_settings'), InlineKeyboardButton("ℹ️ Help", callback_data='show_help')]
    ]
    if user_id == OWNER_ID: btns.append([InlineKeyboardButton("👑 Owner Panel", callback_data='menu_owner')])
    if is_admin(user_id): btns.append([InlineKeyboardButton("🛡️ Content Admin", callback_data='menu_admin')])
    text = (f"👋 <b>Namaste {fname}!</b>\n\n🎯 <b>Select Your Goal:</b>\n👇 <i>Select an option below:</i>")
    if update.callback_query: await safe_edit_message(update.callback_query, text, InlineKeyboardMarkup(btns))
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')

async def show_owner_panel(update, context):
    btns = [
        [InlineKeyboardButton("➕ Add Admin", callback_data='add_admin_prompt'), InlineKeyboardButton("📜 Admin List", callback_data='view_admin_list')],
        [InlineKeyboardButton("💾 Backup", callback_data='get_backup'), InlineKeyboardButton("♻️ Restore", callback_data='restore_prompt')],
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
    
    if data == 'menu_admin':
        btns = [
            [InlineKeyboardButton("➕ Add BSEB", callback_data='adm_sel_BSEB')],
            [InlineKeyboardButton("➕ Add NEET", callback_data='adm_sel_NEET')],
            [InlineKeyboardButton("🗑️ Delete Data", callback_data='adm_del_menu')],
            [InlineKeyboardButton("📢 Broadcast", callback_data='adm_broadcast_prompt')],
            [InlineKeyboardButton("Back", callback_data='main_menu')]
        ]
        await safe_edit_message(query, "🛡️ <b>Content Admin Panel</b>", InlineKeyboardMarkup(btns))
        return

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
        await safe_edit_message(query, "📤 <b>Send database.json or backup.json file to restore:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_owner')]]))
        return
    if data == 'adm_broadcast_prompt':
        await safe_edit_message(query, "📢 <b>Send broadcast message:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_broadcast_msg'] = True
        return
    if data == 'adm_del_menu':
        btns = [[InlineKeyboardButton("BSEB", callback_data='del_sel_BSEB'), InlineKeyboardButton("NEET", callback_data='del_sel_NEET')], [InlineKeyboardButton("Back", callback_data='menu_admin')]]
        await safe_edit_message(query, "🗑️ <b>Select Category:</b>", InlineKeyboardMarkup(btns))
        return

    if data.startswith(('del_sel_', 'adm_sel_')):
        mode = 'del' if 'del' in data else 'adm'
        cat = data.split('_')[2]; context.user_data[f'{mode}_cat'] = cat
        subs = db["questions"].get(cat, {}).keys()
        btns = [[InlineKeyboardButton(s, callback_data=f'{mode}_sub_{s}')] for s in subs]
        btns.append([InlineKeyboardButton("Back", callback_data='menu_admin')])
        await safe_edit_message(query, f"📂 <b>{cat} > Select Subject:</b>", InlineKeyboardMarkup(btns))
        return
    
    if data.startswith(('del_sub_', 'adm_sub_')):
        mode = 'del' if 'del' in data else 'adm'
        sub = data.replace(f'{mode}_sub_', ''); context.user_data[f'{mode}_sub'] = sub
        cat = context.user_data.get(f'{mode}_cat')
        chaps = db["questions"].get(cat, {}).get(sub, {}).keys()
        
        if mode == 'del':
            btns = [[InlineKeyboardButton(f"❌ {c}", callback_data=f'del_chap_{c}')] for c in chaps]
            btns.append([InlineKeyboardButton("Back", callback_data=f'del_sel_{cat}')])
            await safe_edit_message(query, "🗑️ <b>Select Chapter to DELETE:</b>", InlineKeyboardMarkup(btns))
        else:
            btns = [[InlineKeyboardButton(c, callback_data=f'adm_chap_{c}')] for c in chaps]
            btns.append([InlineKeyboardButton("➕ Add New Chapter", callback_data='adm_new_chap')])
            btns.append([InlineKeyboardButton("Back", callback_data='menu_admin')])
            await safe_edit_message(query, "📂 <b>Select Chapter:</b>", InlineKeyboardMarkup(btns))
        return

    if data.startswith('del_chap_'):
        chap = data.replace('del_chap_', ''); context.user_data['del_chap'] = chap
        btns = [[InlineKeyboardButton("✅ YES, DELETE", callback_data='confirm_del')], [InlineKeyboardButton("❌ CANCEL", callback_data='menu_admin')]]
        await safe_edit_message(query, f"⚠️ <b>Delete '{chap}'?</b>", InlineKeyboardMarkup(btns))
        return
    if data == 'confirm_del':
        try:
            del db["questions"][context.user_data['del_cat']][context.user_data['del_sub']][context.user_data['del_chap']]
            save_db(db)
            await query.answer("✅ Deleted!", show_alert=True)
            await handle_admin(update, context)
        except: await query.answer("❌ Error", show_alert=True)
        return
    if data == 'adm_new_chap':
        await safe_edit_message(query, "⌨️ <b>Type Chapter Name:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_admin')]]))
        context.user_data['awaiting_chap_name'] = True
        return
    if data.startswith('adm_chap_'):
        chap = data.split('_')[2]; context.user_data['adm_chap'] = chap; context.user_data['adm_mode'] = 'active'
        await safe_edit_message(query, f"📂 <b>Active:</b> {chap}\n\n👇 <b>Forward Polls / Send .txt</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_admin')]]))
        return

async def master_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == 'recheck_main':
        if await check_membership(IDS["MAIN"], query.from_user.id, context): await show_main_menu(update, context)
        else: await query.answer("❌ Join First!", show_alert=True)
        return
    if data in ['gate_bseb', 'gate_neet']: 
        gid = IDS[data.replace('gate_', '').upper()]; link = LINKS[data.replace('gate_', '').upper()]
        await check_gate(query, context, gid, link, open_bseb_menu if 'bseb' in data else open_neet_menu, data)

    if data == 'main_menu': await show_main_menu(update, context)
    elif data == 'menu_settings': await show_settings(update, context)
    elif data == 'menu_owner' or data in ['view_admin_list', 'restore_prompt', 'get_backup']: 
        if data == 'menu_owner': await show_owner_panel(update, context)
        elif data == 'get_backup': save_db(db); await context.bot.send_document(query.message.chat_id, document=open(DB_FILE, 'rb'), filename="backup.json")
        else: await handle_admin(update, context)
    elif data == 'add_admin_prompt':
        context.user_data['awaiting_admin_id'] = True
        await safe_edit_message(query, "⌨️ <b>Send User ID to add as Admin:</b>", InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data='menu_owner')]]))
    elif data.startswith(('menu_admin', 'adm_', 'del_', 'confirm_del')): await handle_admin(update, context)
    
    elif data == 'menu_improve':
        btns = [[InlineKeyboardButton("BSEB", callback_data='imp_cat_BSEB'), InlineKeyboardButton("NEET", callback_data='imp_cat_NEET')], [InlineKeyboardButton("Back", callback_data='main_menu')]]
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
            await query.answer("🎉 No mistakes found!", show_alert=True)
            return
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = sub; context.user_data['quiz_mode'] = 'improve' 
        await ask_time(query)

    elif data == 'section_BSEB_Hindi': await open_bseb_hindi_sections(query, context)
    elif data == 'section_BSEB_English': await open_bseb_english_sections(query, context)

    elif data.startswith('sel_sub_'):
        parts = data.split('_', 3); cat = parts[2]; sub = parts[3]
        context.user_data['quiz_cat'] = cat; context.user_data['quiz_sub'] = sub; context.user_data['quiz_mode'] = 'normal'
        disp_sub = sub.split('-')[-1]
        btns = [[InlineKeyboardButton("📖 Chapter Wise", callback_data='mode_single')], [InlineKeyboardButton("🔀 Mix / Custom", callback_data='mode_mix')], [InlineKeyboardButton("Back", callback_data='main_menu')]]
        await safe_edit_message(query, f"📂 <b>{cat} > {disp_sub}</b>", InlineKeyboardMarkup(btns))
    
    elif data == 'mode_single': await show_chapter_selection(query, context, multi=False)
    elif data == 'mode_mix': context.user_data['selected_chapters'] = []; await show_chapter_selection(query, context, multi=True)
    elif data.startswith('tgl_'):
        chap = data.split('tgl_')[1]; sel = context.user_data.get('selected_chapters', [])
        if chap in sel: sel.remove(chap)
        else: sel.append(chap)
        context.user_data['selected_chapters'] = sel
        await show_chapter_selection(query, context, multi=True)
    elif data == 'confirm_mix':
        if not context.user_data.get('selected_chapters'): await query.answer("Select one!", show_alert=True); return
        context.user_data['final_chapters'] = context.user_data['selected_chapters']; await ask_time(query)
    elif data.startswith('sng_'):
        chap = data.split('sng_')[1]; context.user_data['final_chapters'] = [chap]; await ask_time(query)
    elif data.startswith('time_'): context.user_data['quiz_time'] = int(data.split('_')[1]); await ask_count(query)
    elif data.startswith('count_'): context.user_data['quiz_count'] = int(data.split('_')[1]); await start_private_quiz(query, context)
    
    elif data == 'view_stats': 
        uid = str(query.from_user.id); stats = db["stats"].get(uid, {})
        txt = "📊 <b>Stats:</b>\n"
        if stats:
            for cat, subs in stats.items():
                txt += f"\n📂 <b>{cat}:</b>"
                for sub, data in subs.items():
                    d_sub = sub.split('-')[-1]
                    correct = data.get('correct', 0); wrong = data.get('wrong', 0); total = data.get('total', 0)
                    txt += f"\n  - {d_sub}: {total} Qs (✅{correct} | ❌{wrong})"
        else: txt += "No data found."
        await safe_edit_message(query, txt, InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data='menu_settings')]]))
    elif data == 'req_admin': 
        await context.bot.send_message(OWNER_ID, f"User {query.from_user.id} requested admin."); await query.answer("Request Sent!")

# ==========================================
# 10. NEW MENU FUNCTIONS
# ==========================================
async def open_bseb_menu(query, context):
    btns = [
        [InlineKeyboardButton("📖 Hindi", callback_data='section_BSEB_Hindi'), InlineKeyboardButton("📖 English", callback_data='section_BSEB_English')],
        [InlineKeyboardButton("🔢 Maths", callback_data='sel_sub_BSEB_Maths'), InlineKeyboardButton("🧬 Biology", callback_data='sel_sub_BSEB_Biology')],
        [InlineKeyboardButton("🧪 Chemistry", callback_data='sel_sub_BSEB_Chemistry'), InlineKeyboardButton("⚛️ Physics", callback_data='sel_sub_BSEB_Physics')],
        [InlineKeyboardButton("Back", callback_data='main_menu')]
    ]
    await safe_edit_message(query, "📚 <b>BSEB Subjects</b>", InlineKeyboardMarkup(btns))

async def open_bseb_hindi_sections(query, context):
    btns = [
        [InlineKeyboardButton("📝 गद्य खण्ड", callback_data='sel_sub_BSEB_Hindi-Gadya')],
        [InlineKeyboardButton("📜 पद्य खण्ड", callback_data='sel_sub_BSEB_Hindi-Padya')],
        [InlineKeyboardButton("🔤 व्याकरण", callback_data='sel_sub_BSEB_Hindi-Grammar')],
        [InlineKeyboardButton("Back", callback_data='gate_bseb')]
    ]
    await safe_edit_message(query, "📚 <b>Hindi Sections:</b>", InlineKeyboardMarkup(btns))

async def open_bseb_english_sections(query, context):
    btns = [
        [InlineKeyboardButton("📝 Prose", callback_data='sel_sub_BSEB_English-Prose')],
        [InlineKeyboardButton("📜 Poetry", callback_data='sel_sub_BSEB_English-Poetry')],
        [InlineKeyboardButton("🔤 Grammar", callback_data='sel_sub_BSEB_English-Grammar')],
        [InlineKeyboardButton("Back", callback_data='gate_bseb')]
    ]
    await safe_edit_message(query, "📚 <b>English Sections:</b>", InlineKeyboardMarkup(btns))

async def open_neet_menu(query, context):
    btns = [[InlineKeyboardButton(f"🧪 {s}", callback_data=f'sel_sub_NEET_{s}')] for s in ["Physics", "Chemistry", "Biology"]]
    btns.append([InlineKeyboardButton("Back", callback_data='main_menu')])
    await safe_edit_message(query, "🩺 <b>NEET Subjects</b>", InlineKeyboardMarkup(btns))

async def show_chapter_selection(query, context, multi):
    cat, sub = context.user_data.get('quiz_cat'), context.user_data.get('quiz_sub')
    
    # [FIX] Handle missing keys gracefully
    if cat not in db["questions"] or sub not in db["questions"][cat]:
        await query.answer("⚠️ Folder not created yet!", show_alert=True)
        return

    chapters = db["questions"][cat][sub]
    disp_sub = sub.split('-')[-1]
    
    if not chapters: 
        await query.answer(f"⚠️ No chapters in {disp_sub}!", show_alert=True)
        return
        
    btns = []
    sel = context.user_data.get('selected_chapters', [])
    for chap, qs in chapters.items():
        count = len(qs)
        if multi:
            icon = "✅" if chap in sel else "⬜"
            btns.append([InlineKeyboardButton(f"{icon} {chap} [{count}]", callback_data=f'tgl_{chap}')])
        else:
            btns.append([InlineKeyboardButton(f"📄 {chap} [{count}]", callback_data=f'sng_{chap}')])
    if multi: btns.append([InlineKeyboardButton(f"▶️ Start ({len(sel)})", callback_data='confirm_mix')])
    btns.append([InlineKeyboardButton("⬅️ Back", callback_data='main_menu')])
    await safe_edit_message(query, f"📖 <b>Select Chapter ({disp_sub})</b>", InlineKeyboardMarkup(btns))

async def ask_time(query):
    btns = [InlineKeyboardButton(f"{t}s", callback_data=f"time_{t}") for t in [15, 30, 45, 60]]
    await safe_edit_message(query, "⏱️ <b>Per Question Time:</b>", InlineKeyboardMarkup([btns, [InlineKeyboardButton("Cancel", callback_data='main_menu')]]))

async def ask_count(query):
    counts = [10, 20, 30, 50, 100, 150, 200, 300, 400, 500]
    btns = [[InlineKeyboardButton(f"{c} Qs", callback_data=f"count_{c}") for c in counts[i:i+3]] for i in range(0, len(counts), 3)]
    btns.append([InlineKeyboardButton("Cancel", callback_data='main_menu')])
    await safe_edit_message(query, "🔢 <b>Question Count:</b>", InlineKeyboardMarkup(btns))

# ==========================================
# 8. HANDLERS (COMMANDS)
# ==========================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message or not update.message.text: return
    user_id = update.effective_user.id
    text = update.message.text
    
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
            await update.message.reply_text(f"✅ Chapter '{text}' Added!")
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
    if user_id == OWNER_ID and (doc.file_name == 'database.json' or doc.file_name == 'backup.json'):
        f = await doc.get_file(); await f.download_to_drive(DB_FILE); global db; db = load_db(); await update.message.reply_text("♻️ DB Restored!")
        return
    if is_admin(user_id) and doc.file_name.endswith('.txt'):
        f = await doc.get_file(); content = await f.download_as_bytearray(); text_data = content.decode('utf-8')
        cat, sub = context.user_data.get('adm_cat'), context.user_data.get('adm_sub')
        if not cat or not sub: await update.message.reply_text("⚠️ Select Subject First!"); return
        cur_chap = "General"; count = 0
        for line in text_data.split('\n'):
            line = line.strip()
            if not line: continue
            if line.lower().startswith('chapter:'): cur_chap = line.split(':', 1)[1].strip(); continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 6:
                try:
                    q = {"question": parts[0], "options": parts[1:5], "correct": int(parts[-1])-1}
                    if cur_chap not in db["questions"][cat][sub]: db["questions"][cat][sub][cur_chap] = []
                    db["questions"][cat][sub][cur_chap].append(q); count += 1
                except: pass
        save_db(db); await update.message.reply_text(f"✅ {count} Imported!")

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
        if not context.args: await update.message.reply_text("❌ Usage: /removeadmin <user_id>"); return
        target_id = int(context.args[0])
        if target_id in db["admins"]:
            db["admins"].remove(target_id); save_db(db)
            await update.message.reply_text(f"✅ User ID {target_id} admin se hata diya gaya.")
        else: await update.message.reply_text("⚠️ Ye user admin list me nahi hai.")
    except ValueError: await update.message.reply_text("❌ Please enter a valid Numeric ID.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        if await check_membership(IDS["MAIN"], update.effective_user.id, context): await show_main_menu(update, context)
        else: await send_force_join_msg(update, LINKS["MAIN"])

if __name__ == '__main__':
    keep_alive()
    if not TOKEN: print("❌ TOKEN MISSING")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("done", done_command))       
        app.add_handler(CommandHandler("removeadmin", remove_admin_command))
        app.add_handler(CallbackQueryHandler(master_callback_router))
        app.add_handler(MessageHandler(filters.POLL & filters.User(OWNER_ID), handle_poll_upload))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(PollAnswerHandler(handle_poll_answer))
        print("✅ Bot is Live!"); app.run_polling()
