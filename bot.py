import os
import json
import asyncio
import logging
import datetime
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
import google.generativeai as genai

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Config (Railway Environment Variables থেকে) ────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
CHAT_ID            = int(os.environ["CHAT_ID"])
WEATHER_API_KEY    = os.environ.get("WEATHER_API_KEY", "")
DEFAULT_CITY       = os.environ.get("DEFAULT_CITY", "Dhaka")

# ─── Gemini Setup ────────────────────────────────────────────────────────────
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")
chat_sessions = {}  # প্রতিটা user এর জন্য আলাদা chat history

# ─── Data Storage (JSON files) ───────────────────────────────────────────────
TASKS_FILE    = "tasks.json"
REMINDERS_FILE = "reminders.json"

def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Helper: শুধু তোমার message process হবে ─────────────────────────────────
def is_owner(update: Update) -> bool:
    return update.effective_user.id == CHAT_ID

def owner_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_owner(update):
            await update.message.reply_text("❌ এই bot শুধু owner ব্যবহার করতে পারবে।")
            return
        await func(update, ctx)
    return wrapper

# ═══════════════════════════════════════════════════════════════════════════
#  /start  —  Welcome
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "বন্ধু"
    text = (
        f"*আস্সালামুআলাইকুম {name}! 👋*\n\n"
        "আমি তোমার Personal AI Assistant। যা করতে পারি:\n\n"
        "🤖 `/ai [প্রশ্ন]` — Gemini AI দিয়ে যেকোনো প্রশ্ন\n"
        "💬 `/chat` — Gemini এর সাথে conversation mode\n"
        "✅ `/task [কাজ]` — task list এ যোগ করো\n"
        "📋 `/tasks` — সব task দেখো\n"
        "✔️ `/done [নম্বর]` — task শেষ করো\n"
        "🗑️ `/deltask [নম্বর]` — task মুছো\n"
        "⏰ `/remind [Xm/Xh] [message]` — reminder\n"
        "📅 `/reminders` — সব reminder দেখো\n"
        "🌤️ `/weather [শহর]` — আবহাওয়া\n"
        "📰 `/news` — বাংলাদেশের খবর\n"
        "📊 `/summary` — দিনের summary\n"
        "❓ `/help` — সব command\n\n"
        "শুরু করো! যেকোনো কথাও সরাসরি লিখতে পারো — AI উত্তর দেবে। 😊"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════════════
#  /ai  —  Single Gemini query
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_ai(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = " ".join(ctx.args)
    if not query:
        await update.message.reply_text("📝 ব্যবহার: `/ai তোমার প্রশ্ন`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("🤔 ভাবছি...")
    try:
        response = gemini_model.generate_content(
            f"তুমি একটি helpful Bengali AI assistant। বাংলায় উত্তর দাও (যদি প্রশ্ন বাংলায় হয়)।\n\nপ্রশ্ন: {query}"
        )
        await msg.edit_text(f"🤖 *Gemini:*\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  /chat  —  Conversation mode (memory থাকে)
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_sessions[uid] = gemini_model.start_chat(history=[])
    await update.message.reply_text(
        "💬 *Conversation mode চালু!*\n\nএখন সরাসরি কথা বলো — আমি মনে রাখব।\n`/endchat` দিয়ে বন্ধ করো।",
        parse_mode="Markdown"
    )
    ctx.user_data["chat_mode"] = True

@owner_only
async def cmd_endchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_sessions.pop(uid, None)
    ctx.user_data["chat_mode"] = False
    await update.message.reply_text("✅ Conversation শেষ। Chat history মুছা হয়েছে।")

# ═══════════════════════════════════════════════════════════════════════════
#  Free text handler  —  chat mode বা direct AI reply
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    msg = await update.message.reply_text("🤔 ভাবছি...")

    try:
        if uid in chat_sessions:
            # Conversation mode
            response = chat_sessions[uid].send_message(text)
        else:
            # Single query
            response = gemini_model.generate_content(
                f"তুমি একটি helpful Bengali AI assistant। সংক্ষেপে ও স্পষ্টভাবে উত্তর দাও।\n\n{text}"
            )
        await msg.edit_text(f"🤖 {response.text}", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}")

# ═══════════════════════════════════════════════════════════════════════════
#  TASK MANAGER
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    task_text = " ".join(ctx.args)
    if not task_text:
        await update.message.reply_text("📝 ব্যবহার: `/task কাজের নাম`", parse_mode="Markdown")
        return

    tasks = load_json(TASKS_FILE)
    uid = str(CHAT_ID)
    if uid not in tasks:
        tasks[uid] = []

    tasks[uid].append({
        "text": task_text,
        "done": False,
        "added": datetime.datetime.now().strftime("%d/%m %H:%M")
    })
    save_json(TASKS_FILE, tasks)
    count = len([t for t in tasks[uid] if not t["done"]])
    await update.message.reply_text(
        f"✅ Task যোগ হয়েছে!\n\n📌 *{task_text}*\n\n⏳ মোট বাকি: {count}টি task",
        parse_mode="Markdown"
    )

@owner_only
async def cmd_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = load_json(TASKS_FILE)
    uid = str(CHAT_ID)
    user_tasks = tasks.get(uid, [])

    pending = [(i, t) for i, t in enumerate(user_tasks) if not t["done"]]
    done    = [(i, t) for i, t in enumerate(user_tasks) if t["done"]]

    if not user_tasks:
        await update.message.reply_text("📋 কোনো task নেই। `/task কাজ` দিয়ে যোগ করো!", parse_mode="Markdown")
        return

    lines = ["📋 *তোমার Task List*\n"]
    if pending:
        lines.append("⏳ *বাকি আছে:*")
        for i, t in pending:
            lines.append(f"  `{i+1}.` {t['text']}  _{t['added']}_")
    if done:
        lines.append("\n✅ *শেষ হয়েছে:*")
        for i, t in done:
            lines.append(f"  `{i+1}.` ~~{t['text']}~~")

    keyboard = [[
        InlineKeyboardButton("✔️ Done করো", callback_data="task_done_prompt"),
        InlineKeyboardButton("🗑️ মুছো", callback_data="task_del_prompt"),
        InlineKeyboardButton("🧹 সব শেষ মুছো", callback_data="task_clear_done")
    ]]
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@owner_only
async def cmd_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("ব্যবহার: `/done 2` (task নম্বর)", parse_mode="Markdown")
        return

    idx = int(ctx.args[0]) - 1
    tasks = load_json(TASKS_FILE)
    uid = str(CHAT_ID)
    user_tasks = tasks.get(uid, [])

    if 0 <= idx < len(user_tasks):
        user_tasks[idx]["done"] = True
        save_json(TASKS_FILE, tasks)
        await update.message.reply_text(f"🎉 সম্পন্ন: ~~{user_tasks[idx]['text']}~~", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ এই নম্বরের task নেই।")

@owner_only
async def cmd_deltask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("ব্যবহার: `/deltask 2`", parse_mode="Markdown")
        return

    idx = int(ctx.args[0]) - 1
    tasks = load_json(TASKS_FILE)
    uid = str(CHAT_ID)
    user_tasks = tasks.get(uid, [])

    if 0 <= idx < len(user_tasks):
        removed = user_tasks.pop(idx)
        save_json(TASKS_FILE, tasks)
        await update.message.reply_text(f"🗑️ মুছা হয়েছে: *{removed['text']}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ এই নম্বরের task নেই।")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "task_clear_done":
        tasks = load_json(TASKS_FILE)
        uid = str(CHAT_ID)
        before = len(tasks.get(uid, []))
        tasks[uid] = [t for t in tasks.get(uid, []) if not t["done"]]
        save_json(TASKS_FILE, tasks)
        removed = before - len(tasks[uid])
        await query.edit_message_text(f"🧹 {removed}টি completed task মুছা হয়েছে।")
    elif data == "task_done_prompt":
        await query.message.reply_text("কোন নম্বর task শেষ করেছ? লেখো: `/done 1`", parse_mode="Markdown")
    elif data == "task_del_prompt":
        await query.message.reply_text("কোন নম্বর task মুছবে? লেখো: `/deltask 1`", parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════════════
#  REMINDER SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
scheduler = AsyncIOScheduler(timezone="Asia/Dhaka")

@owner_only
async def cmd_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    ব্যবহার:
      /remind 30m নামাজের সময়
      /remind 2h পানি খাও
      /remind 09:30 সকালের রুটিন
    """
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "⏰ ব্যবহার:\n`/remind 30m কাজের নাম`\n`/remind 2h কাজের নাম`\n`/remind 09:30 কাজের নাম`",
            parse_mode="Markdown"
        )
        return

    time_str = ctx.args[0]
    message  = " ".join(ctx.args[1:])
    now      = datetime.datetime.now()

    try:
        if time_str.endswith("m"):
            delta = datetime.timedelta(minutes=int(time_str[:-1]))
            run_at = now + delta
        elif time_str.endswith("h"):
            delta = datetime.timedelta(hours=int(time_str[:-1]))
            run_at = now + delta
        elif ":" in time_str:
            h, m = map(int, time_str.split(":"))
            run_at = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if run_at <= now:
                run_at += datetime.timedelta(days=1)
        else:
            raise ValueError("Invalid format")
    except ValueError:
        await update.message.reply_text("❌ সময়ের format ঠিক নেই। উদাহরণ: `30m`, `2h`, `09:30`", parse_mode="Markdown")
        return

    app = ctx.application
    job_id = f"remind_{CHAT_ID}_{run_at.timestamp()}"

    scheduler.add_job(
        send_reminder,
        "date",
        run_date=run_at,
        args=[app, message],
        id=job_id,
        replace_existing=True
    )

    # reminders file এ save করো
    reminders = load_json(REMINDERS_FILE)
    if str(CHAT_ID) not in reminders:
        reminders[str(CHAT_ID)] = []
    reminders[str(CHAT_ID)].append({
        "id": job_id,
        "message": message,
        "time": run_at.strftime("%d/%m/%Y %H:%M")
    })
    save_json(REMINDERS_FILE, reminders)

    diff = run_at - now
    mins = int(diff.total_seconds() / 60)
    await update.message.reply_text(
        f"⏰ *Reminder set!*\n\n📌 {message}\n🕐 {run_at.strftime('%H:%M')} তে মনে করিয়ে দেব\n⏳ {mins} মিনিট পরে",
        parse_mode="Markdown"
    )

async def send_reminder(app, message: str):
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=f"⏰ *Reminder!*\n\n{message}",
        parse_mode="Markdown"
    )

@owner_only
async def cmd_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reminders = load_json(REMINDERS_FILE)
    user_reminders = reminders.get(str(CHAT_ID), [])

    if not user_reminders:
        await update.message.reply_text("📅 কোনো reminder নেই। `/remind 30m কাজ` দিয়ে set করো!", parse_mode="Markdown")
        return

    lines = ["📅 *তোমার Reminders:*\n"]
    for i, r in enumerate(user_reminders, 1):
        lines.append(f"`{i}.` ⏰ {r['time']}\n    📌 {r['message']}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════════════
#  WEATHER
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_weather(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    city = " ".join(ctx.args) if ctx.args else DEFAULT_CITY

    if not WEATHER_API_KEY:
        # Gemini দিয়ে general info দেওয়া হবে
        msg = await update.message.reply_text("🌤️ তথ্য আনছি...")
        response = gemini_model.generate_content(
            f"আজকের {city} এর আবহাওয়া সম্পর্কে সাধারণ তথ্য দাও বাংলায়। "
            f"(Note: real-time data নেই, তাই seasonal বলো)"
        )
        await msg.edit_text(f"🌤️ *{city} আবহাওয়া (সাধারণ)*\n\n{response.text}", parse_mode="Markdown")
        return

    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=bn"
        data = requests.get(url, timeout=10).json()

        if data.get("cod") != 200:
            await update.message.reply_text(f"❌ '{city}' পাওয়া যায়নি।")
            return

        temp   = data["main"]["temp"]
        feels  = data["main"]["feels_like"]
        humid  = data["main"]["humidity"]
        desc   = data["weather"][0]["description"]
        wind   = data["wind"]["speed"]

        emoji = "☀️" if "clear" in desc else "🌧️" if "rain" in desc else "☁️"

        text = (
            f"{emoji} *{city} এর আবহাওয়া*\n\n"
            f"🌡️ তাপমাত্রা: *{temp}°C* (feels like {feels}°C)\n"
            f"💧 আর্দ্রতা: {humid}%\n"
            f"💨 বাতাস: {wind} m/s\n"
            f"🌤️ অবস্থা: {desc}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  NEWS  —  Gemini দিয়ে
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📰 খবর আনছি...")
    try:
        response = gemini_model.generate_content(
            "বাংলাদেশের আজকের গুরুত্বপূর্ণ সংবাদ সম্পর্কে brief summary দাও বাংলায়। "
            "৫টি bullet point এ main topics উল্লেখ করো। Real-time data না থাকলে "
            "সেটা mention করে সাধারণ current affairs দাও।"
        )
        await msg.edit_text(f"📰 *আজকের সংবাদ*\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  DAILY SUMMARY  —  Gemini দিয়ে productivity tips
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = load_json(TASKS_FILE)
    uid = str(CHAT_ID)
    user_tasks = tasks.get(uid, [])
    pending = [t["text"] for t in user_tasks if not t["done"]]
    done    = [t["text"] for t in user_tasks if t["done"]]

    now = datetime.datetime.now()
    msg = await update.message.reply_text("📊 Summary তৈরি করছি...")

    prompt = (
        f"আজকের দিন: {now.strftime('%A, %d %B %Y')}, সময়: {now.strftime('%H:%M')}\n"
        f"বাকি tasks: {', '.join(pending) if pending else 'কিছু নেই'}\n"
        f"শেষ করা tasks: {', '.join(done) if done else 'কিছু নেই'}\n\n"
        "এই তথ্য দেখে বাংলায় একটি সংক্ষিপ্ত দৈনিক summary দাও। "
        "Productivity tips এবং motivational কথা যোগ করো।"
    )
    try:
        response = gemini_model.generate_content(prompt)
        await msg.edit_text(f"📊 *দৈনিক Summary*\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#  MORNING ROUTINE  —  প্রতিদিন সকাল ৭টায়
# ═══════════════════════════════════════════════════════════════════════════
async def morning_routine(app):
    now = datetime.datetime.now()
    tasks = load_json(TASKS_FILE)
    user_tasks = tasks.get(str(CHAT_ID), [])
    pending = [t["text"] for t in user_tasks if not t["done"]]

    try:
        response = gemini_model.generate_content(
            f"আজ {now.strftime('%A, %d %B')}। সকালের শুভেচ্ছা দাও বাংলায় এবং "
            f"দিনটি productive করতে ৩টি tips দাও।"
        )
        greeting = response.text
    except Exception:
        greeting = "আজকের দিন সুন্দর হোক! 🌅"

    task_text = ""
    if pending:
        task_text = f"\n\n📋 *আজকের বাকি tasks ({len(pending)}টি):*\n"
        for i, t in enumerate(pending, 1):
            task_text += f"{i}. {t}\n"

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=f"🌅 *সুপ্রভাত!*\n\n{greeting}{task_text}",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════════════════════════
#  EVENING CHECK-IN  —  প্রতিদিন রাত ৯টায়
# ═══════════════════════════════════════════════════════════════════════════
async def evening_checkin(app):
    tasks = load_json(TASKS_FILE)
    user_tasks = tasks.get(str(CHAT_ID), [])
    pending = len([t for t in user_tasks if not t["done"]])
    done    = len([t for t in user_tasks if t["done"]])

    text = (
        f"🌙 *সন্ধ্যার check-in!*\n\n"
        f"✅ আজ শেষ করেছ: {done}টি task\n"
        f"⏳ এখনো বাকি: {pending}টি task\n\n"
        f"বাকি tasks দেখতে `/tasks` লেখো।\n"
        f"কাল কী করবে ঠিক করতে `/ai কালকের plan বানাও` লেখো। 💪"
    )
    await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════════════
#  /help
# ═══════════════════════════════════════════════════════════════════════════
@owner_only
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "*সব Command:*\n\n"
        "🤖 *AI:*\n"
        "`/ai [প্রশ্ন]` — এক-বার প্রশ্ন\n"
        "`/chat` — conversation mode চালু\n"
        "`/endchat` — conversation বন্ধ\n\n"
        "✅ *Tasks:*\n"
        "`/task [কাজ]` — task যোগ\n"
        "`/tasks` — সব task দেখো\n"
        "`/done [নম্বর]` — task শেষ করো\n"
        "`/deltask [নম্বর]` — task মুছো\n\n"
        "⏰ *Reminders:*\n"
        "`/remind 30m [message]` — ৩০ মিনিট পরে\n"
        "`/remind 2h [message]` — ২ ঘন্টা পরে\n"
        "`/remind 09:30 [message]` — নির্দিষ্ট সময়ে\n"
        "`/reminders` — সব reminder দেখো\n\n"
        "🌤️ *Info:*\n"
        "`/weather [শহর]` — আবহাওয়া\n"
        "`/news` — খবর\n"
        "`/summary` — দিনের summary\n\n"
        "📱 *Auto:*\n"
        "প্রতিদিন সকাল ৭টায় morning briefing\n"
        "প্রতিদিন রাত ৯টায় evening check-in"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("ai",        cmd_ai))
    app.add_handler(CommandHandler("chat",      cmd_chat))
    app.add_handler(CommandHandler("endchat",   cmd_endchat))
    app.add_handler(CommandHandler("task",      cmd_task))
    app.add_handler(CommandHandler("tasks",     cmd_tasks))
    app.add_handler(CommandHandler("done",      cmd_done))
    app.add_handler(CommandHandler("deltask",   cmd_deltask))
    app.add_handler(CommandHandler("remind",    cmd_remind))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("weather",   cmd_weather))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("summary",   cmd_summary))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Free text → AI reply
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Scheduled jobs (Asia/Dhaka timezone)
    scheduler.add_job(morning_routine,  "cron", hour=7,  minute=0,  args=[app])
    scheduler.add_job(evening_checkin,  "cron", hour=21, minute=0,  args=[app])
    scheduler.start()

    logger.info("✅ Bot চালু হয়েছে!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
