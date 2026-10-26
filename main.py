import asyncio
import datetime
import json
import os
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError, UserNotParticipantError

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "user_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

CHANNEL_USERNAME = "@YourChannelUsername"

FONTS = {
    "1": {"name": "🟪 النمط الأول (𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿)", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "2": {"name": "🟦 النمط الثاني ( Scholz 𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗 )", "digits": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"},
    "3": {"name": "🟩 النمط الثالث (🟨🟫🟪 🟨 🟪 🟫)", "digits": "🟨🟫🟪🟨🟪🟫⬛⬜🟥🟦"},
    "4": {"name": "🄲🄾🄾🄻 النمط الرابع (⓪①②③④⑤⑥⑦⑧⑨)", "digits": "⓪①②③④⑤⑥⑦⑧⑨"}
}

FONTS = {
    "1": {"name": "🟪 النمط الأول (𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿)", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "2": {"name": "🟦 النمط الثاني (𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩🟪🟪)", "digits": "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"},
    "3": {"name": "🟩 النمط الثالث (𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟲𝟕)", "digits": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"},
    "4": {"name": "🄲🄾🄾🄻 النمط الرابع (⓪①②③④⑤⑥⑦⑧⑨)", "digits": "⓪①②③④⑤⑥⑦⑧⑨"}
}

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data():
    temporary_file = DATA_FILE + ".tmp"
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2, ensure_ascii=False)
    os.replace(temporary_file, DATA_FILE)

users = load_data()
running_accounts = {}
login_states = {}

bot = TelegramClient("bot_control_session", API_ID, API_HASH)

def get_user(user_id):
    key = str(user_id)
    if key not in users:
        users[key] = {
            "base_name": "Z",
            "font_type": "1",
            "accounts": []
        }
        save_data()
    return users[key]

def to_fancy_digits(text, font_type):
    normal_digits = "0123456789"
    fancy_digits = FONTS.get(font_type, FONTS["1"])["digits"]
    digits_map = str.maketrans(normal_digits, fancy_digits)
    return str(text).translate(digits_map)

async def check_subscription(event):
    if event.is_private:
        try:
            await bot(GetParticipantRequest(channel=CHANNEL_USERNAME, participant=event.sender_id))
            return True
        except UserNotParticipantError:
            url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
            await event.reply(
                "📢 **عذراً، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت!**",
                buttons=[Button.url("اضغط هنا للاشتراك", url)]
            )
            return False
        except Exception:
            return True
    return True

async def account_time_loop(session_key, client, user_id):
    last_time = ""
    try:
        while True:
            try:
                if not client.is_connected():
                    await client.connect()

                user = get_user(user_id)
                if session_key not in user["accounts"]:
                    break

                raw_time = datetime.datetime.now(ZoneInfo("Africa/Algiers")).strftime("%H:%M")
                fancy_time = to_fancy_digits(raw_time, user.get("font_type", "1"))

                if fancy_time != last_time:
                    new_name = f"{user['base_name']} {fancy_time}"
                    await client(UpdateProfileRequest(first_name=new_name))
                    last_time = fancy_time

                await asyncio.sleep(30)

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                await asyncio.sleep(15)
    except asyncio.CancelledError:
        pass
    finally:
        if client.is_connected():
            await client.disconnect()

async def load_saved_sessions():
    await asyncio.sleep(2)
    for user_id, user_data in users.items():
        for session_entry in user_data.get("accounts", []):
            try:
                if session_entry.startswith("1") and len(session_entry) > 40:
                    client = TelegramClient(StringSession(session_entry), API_ID, API_HASH, auto_reconnect=True)
                else:
                    session_path = os.path.join(SESSIONS_DIR, session_entry)
                    client = TelegramClient(session_path, API_ID, API_HASH, auto_reconnect=True)

                await client.connect()
                if await client.is_user_authorized():
                    running_accounts[session_entry] = asyncio.create_task(
                        account_time_loop(session_entry, client, int(user_id))
                    )
                else:
                    await client.disconnect()
            except Exception:
                pass

def make_main_keyboard():
    return [
        [Button.inline("➕ إضافة حساب", b"menu_choose_method"), Button.inline("⚙️ أنواع الزخرفات", b"menu_fonts")],
        [Button.inline("📝 تغيير الاسم", b"menu_name"), Button.inline("📊 الحسابات المتصلة", b"menu_status")],
        [Button.inline("🛑 إيقاف حساب", b"menu_stop")]
    ]

@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    if not event.is_private or not await check_subscription(event):
        return
    get_user(event.sender_id)
    await event.reply(
        "🤖 **أهلاً بك في بوت إدارة حسابات الوقت المتطور**

"
        "يمكنك التحكم بكل سهولة عبر الأزرار أدناه:",
        buttons=make_main_keyboard()
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_main$"))
async def menu_main_callback(event):
    await event.edit(
        "🤖 **لوحة التحكم الرئيسية**

"
        "إختر الإجراء المطلوب من الأزرار المتاحة:",
        buttons=make_main_keyboard()
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_choose_method$"))
async def menu_choose_method_callback(event):
    await event.edit(
        "➕ **إختر طريقة إضافة الحساب المناسبة:**

"
        "💡 _ملاحظة: بالنسبة للحسابات المحمية بكلمة مرور إضافية، يرجى استخدام طريقة الـ Session لضمان تخطي قيود الرمز._",
        buttons=[
            [Button.inline("📱 عبر الرقم والرمز مباشرة", b"menu_add_phone")],
            [Button.inline("🔑 عبر كود الجلسة (StringSession)", b"menu_add_session")],
            [Button.inline("🔙 عودة للرئيسية", b"menu_main")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_add_session$"))
async def menu_add_session_callback(event):
    login_states[event.sender_id] = {"step": "string_session"}
    await event.edit(
        "🔑 **إضافة حساب عبر الـ StringSession:**

"
        "أرسل كود الجلسة الخاص بحسابك الآن مباشرة في رسالة عادية.",
        buttons=[Button.inline("🔙 إلغاء", b"menu_main")]
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_add_phone$"))
async def menu_add_phone_callback(event):
    login_states[event.sender_id] = {"step": "phone"}
    await event.edit(
        "📱 **بدء إضافة حساب جديد عبر الرقم:**

"
        "أرسل رقم الهاتف المراد ربطه مع رمز الدولة الآن في رسالة عادية.
"
        "مثال: `+213xxxxxxxxx`",
        buttons=[Button.inline("🔙 إلغاء", b"menu_main")]
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_fonts$"))
async def menu_fonts_callback(event):
    user = get_user(event.sender_id)
    current_font = user.get("font_type", "1")
    
    buttons = []
    for fid, font in FONTS.items():
        text = f"✅ {font['name']}" if fid == current_font else font['name']
        buttons.append([Button.inline(text, f"set_font_{fid}".encode())])
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("⚙️ **قائمة الزخرفات المتاحة للأرقام:**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"^set_font_(\d+)$"))
async def set_font_callback(event):
    font_id = event.pattern_match.group(1).decode()
    user = get_user(event.sender_id)
    user["font_type"] = font_id
    save_data()
    
    buttons = []
    for fid, font in FONTS.items():
        text = f"✅ {font['name']}" if fid == font_id else font['name']
        buttons.append([Button.inline(text, f"set_font_{fid}".encode())])
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("⚙️ **قائمة الزخرفات المتاحة للأرقام:**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"^menu_name$"))
async def menu_name_callback(event):
    user = get_user(event.sender_id)
    login_states[event.sender_id] = {"step": "change_name_input"}
    await event.edit(
        f"📝 **الاسم الحالي المعتمد:** {user['base_name']}

"
        "أرسل الآن الاسم الجديد الذي تريده في رسالة عادية.",
        buttons=[Button.inline("🔙 إلغاء وعودة", b"menu_main")]
    )

@bot.on(events.CallbackQuery(pattern=r"^menu_status$"))
async def menu_status_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        text = "📊 **الحسابات المتصلة:**

لا توجد حسابات مرتبطة بنظامك حالياً."
    else:
        text = "📊 **الحسابات المتصلة حالياً والمحدثة للوقت:**

"
        for idx, acc in enumerate(accounts, 1):
            display = acc if len(acc) < 25 else f"الحساب {idx} (عبر الجلسة)"
            text += f"{idx}️⃣ الحساب: `{display}`
"
            
    await event.edit(text, buttons=[Button.inline("🔙 عودة", b"menu_main")])

@bot.on(events.CallbackQuery(pattern=r"^menu_stop$"))
async def menu_stop_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        await event.edit("🛑 لا توجد حسابات مرتبطة لإيقافها.", buttons=[Button.inline("🔙 عودة", b"menu_main")])
        return
        
    buttons = []
    for idx, acc in enumerate(accounts, 1):
        display = acc if len(acc) < 25 else f"الحساب {idx} (عبر الجلسة)"
        buttons.append([Button.inline(f"❌ إيقاف: {display}", f"action_stop_{idx}".encode())])
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("🛑 **إختر الحساب المراد إيقافه وحذفه نهائياً:**", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=r"^action_stop_(\d+)$"))
async def action_stop_callback(event):
    idx_str = event.pattern_match.group(1).decode()
    idx = int(idx_str) - 1
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    
    if 0 <= idx < len(accounts):
        target = accounts[idx]
        accounts.remove(target)
        save_data()
        
        if target in running_accounts:
            running_accounts[target].cancel()
            del running_accounts[target]
            
        if not (target.startswith("1") and len(target) > 40):
            session_file = os.path.join(SESSIONS_DIR, f"{target}.session")
            if os.path.exists(session_file):
                try: os.remove(session_file)
                except: pass
                
        await event.edit("🛑 تم إيقاف وحذف الحساب بنجاح.", buttons=[Button.inline("🔙 عودة إلى التحكم", b"menu_main")])
    else:
        await event.edit("❌ حدث خطأ، الحساب غير موجود.", buttons=[Button.inline("🔙 عودة", b"menu_main")])

@bot.on(events.NewMessage)
async def global_text_handler(event):
    if not event.is_private or event.text.startswith('/'):
        return

    chat_id = event.sender_id
    if chat_id not in login_states:
        return

    if not await check_subscription(event):
        return

    state = login_states[chat_id]
    user_input = event.text.strip()

    if state["step"] == "change_name_input":
        if len(user_input) > 40:
            await event.reply("❌ الاسم طويل جداً، يرجى إرسال اسم أقل من 40 حرفاً.")
            return
        user = get_user(chat_id)
        user["base_name"] = user_input
        save_data()
        del login_states[chat_id]
        await event.reply(f"✅ تم تعديل الاسم بنجاح إلى: {user_input}", buttons=make_main_keyboard())

    elif state["step"] == "string_session":
        session_str = user_input
        user = get_user(chat_id)
        if session_str in user["accounts"]:
            await event.reply("⚠️ هذا الحساب مرتبط لديك بالفعل!")
            del login_states[chat_id]
            return
            
        status_msg = await event.reply("⏳ جاري التحقق من الـ StringSession وربطه...")
        try:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH, auto_reconnect=True)
            await client.connect()
            if not await client.is_user_authorized():
                await status_msg.delete()
                await event.reply("❌ الـ StringSession غير صالح أو منتهي الصلاحية.")
                await client.disconnect()
                del login_states[chat_id]
                return
                
            user["accounts"].append(session_str)
            save_data()
            
            running_accounts[session_str] = asyncio.create_task(account_time_loop(session_str, client, chat_id))
            me = await client.get_me()
            await status_msg.delete()
            await event.reply(f"✅ **تم ربط وتشغيل الحساب بنجاح!**
👤 حساب: {me.first_name}", buttons=make_main_keyboard())
            del login_states[chat_id]
        except Exception as e:
            await event.reply(f"❌ فشل الاتصال عبر الجلسة: {e}")
            del login_states[chat_id]

    elif state["step"] == "phone":
        phone = user_input
        user = get_user(chat_id)
        if phone in user["accounts"]:
            await event.reply("⚠️ هذا الحساب مرتبط لديك بالفعل!")
            del login_states[chat_id]
            return
            
        status_msg = await event.reply(f"⏳ جاري الاتصال وتوليد رمز التحقق للحساب: `{phone}`...")
        session_path = os.path.join(SESSIONS_DIR, phone)
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        
        try:
            send_code_result = await client.send_code_request(phone)
            state["phone_code_hash"] = send_code_result.phone_code_hash
            state["phone"] = phone
            state["client"] = client
            state["step"] = "code"
            await status_msg.delete()
            await event.reply("📩 تم إرسال رمز التحقق من تيليغرام. يرجى كتابة الرمز وإرساله هنا:")
        except Exception as e:
            await event.reply(f"❌ لم يرسل الرمز. قد يكون الحساب محمياً بـ 2FA أو توجد قيود أمنية.
ينصح بشدة باستخدام خيار StringSession لتخطي هذه المشكلة.
الخطأ: {e}")
            await client.disconnect()
            del login_states[chat_id]

    elif state["step"] == "code":
        code = user_input
        client = state["client"]
        phone = state["phone"]
        phone_code_hash = state["phone_code_hash"]
        
        status_msg = await event.reply("⏳ جاري التحقق من الرمز...")
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            user = get_user(chat_id)
            if phone not in user["accounts"]:
                user["accounts"].append(phone)
                save_data()
                
            running_accounts[phone] = asyncio.create_task(account_time_loop(phone, client, chat_id))
            me = await client.get_me()
            await status_msg.delete()
            await event.reply(f"✅ **تم ربط وتشغيل الحساب بنجاح!**
👤 حساب: {me.first_name}", buttons=make_main_keyboard())
            del login_states[chat_id]
            
        except SessionPasswordNeededError:
            state["step"] = "password"
            await status_msg.delete()
            await event.reply("🔒 هذا الحساب محمي بالتحقق بخطوتين.
يرجى إرسال كلمة المرور الخاصة بالحساب:")
        except Exception as e:
            await event.reply(f"❌ الرمز خاطئ أو حدثت مشكلة: {e}
تم إلغاء العملية.")
            await client.disconnect()
            del login_states[chat_id]

    elif state["step"] == "password":
        password = user_input
        client = state["client"]
        phone = state["phone"]
        
        status_msg = await event.reply("⏳ جاري التحقق من كلمة المرور...")
        try:
            await client.sign_in(password=password)
            user = get_user(chat_id)
            if phone not in user["accounts"]:
                user["accounts"].append(phone)
                save_data()
                
            running_accounts[phone] = asyncio.create_task(account_time_loop(phone, client, chat_id))
            me = await client.get_me()
            await status_msg.delete()
            await event.reply(f"✅ **تم ربط وتشغيل الحساب بنجاح!**
👤 حساب: {me.first_name}", buttons=make_main_keyboard())
            del login_states[chat_id]
        except Exception as e:
            await event.reply(f"❌ كلمة المرور خاطئة أو حدث خطأ: {e}
تم إلغاء العملية.")
            await client.disconnect()
            del login_states[chat_id]

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(load_saved_sessions())
    bot.start(bot_token=BOT_TOKEN)
    bot.run_until_disconnected()
