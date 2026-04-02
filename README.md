# 🤖 Personal Telegram AI Bot (Gemini + Telegram)

আমার personal productivity bot — সম্পূর্ণ বাংলায়, সম্পূর্ণ ফ্রি।

---

## ✅ Features

- 🤖 **Gemini AI** — যেকোনো প্রশ্ন, conversation mode সহ
- ✅ **Task Manager** — task add, done, delete
- ⏰ **Smart Reminders** — 30m / 2h / 09:30 format
- 🌤️ **Weather** — যেকোনো শহরের আবহাওয়া
- 📰 **News** — বাংলাদেশের খবর
- 📊 **Daily Summary** — AI-generated day plan
- 🌅 **Morning Briefing** — প্রতিদিন ৭টায় auto message
- 🌙 **Evening Check-in** — প্রতিদিন রাত ৯টায় auto message

---

## 🚀 Deploy করো (Railway)

### ধাপ ১: Keys সংগ্রহ করো

| Key | কোথায় পাবে |
|-----|------------|
| `TELEGRAM_BOT_TOKEN` | @BotFather → /newbot |
| `GEMINI_API_KEY` | aistudio.google.com/apikey |
| `CHAT_ID` | @userinfobot → /start |
| `WEATHER_API_KEY` | openweathermap.org/api (ফ্রি, optional) |

### ধাপ ২: Railway তে Deploy

1. [railway.app](https://railway.app) এ sign up করো (GitHub দিয়ে)
2. **"New Project"** → **"Deploy from GitHub repo"**
3. এই repository select করো
4. **"Variables"** tab এ যাও এবং add করো:

```
TELEGRAM_BOT_TOKEN = তোমার_token
GEMINI_API_KEY     = তোমার_gemini_key
CHAT_ID            = তোমার_chat_id
WEATHER_API_KEY    = তোমার_weather_key  (optional)
DEFAULT_CITY       = Dhaka
```

5. **Deploy** দাও — ২ মিনিটে চালু হবে!

---

## 📱 Phone Notification → Telegram

Android এ সব notification Telegram এ পেতে:

**Option 1 (সহজ):** Play Store এ "Notify Me - Telegram" install করো
- Bot token আর Chat ID দাও → সব notification forward হবে

**Option 2 (advanced):** MacroDroid app
- Trigger: "Notification received" 
- Action: "HTTP request" → Telegram Bot API

---

## 💬 Commands

```
/start         — শুরু করো
/ai [প্রশ্ন]  — AI কে প্রশ্ন করো
/chat          — conversation mode
/endchat       — conversation বন্ধ
/task [কাজ]   — task যোগ করো
/tasks         — সব task দেখো
/done [নম্বর] — task শেষ করো
/deltask [নম্বর] — task মুছো
/remind 30m [msg]  — ৩০ মিনিট পরে reminder
/remind 2h [msg]   — ২ ঘন্টা পরে reminder
/remind 09:30 [msg] — নির্দিষ্ট সময়ে reminder
/reminders     — সব reminder দেখো
/weather [শহর] — আবহাওয়া
/news          — বাংলাদেশের খবর
/summary       — দিনের AI summary
/help          — সব command
```

---

## 🔒 Security

- শুধু owner (CHAT_ID) এর message process হবে
- অন্য কেউ message পাঠালে ignore হবে

---

## 📁 Files

```
bot.py           — main bot code
requirements.txt — Python packages
Procfile         — Railway deployment config
tasks.json       — task storage (auto-created)
reminders.json   — reminder storage (auto-created)
```
