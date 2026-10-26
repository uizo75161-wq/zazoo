import asyncio, datetime, json, os
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
    "1": {"name": "🟪 النمط 1 (𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿)", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "2": {"name": "🟦 النمط 2 (<b>0123456789</b>)", "digits": "<b>0123456789</b>"},
    "3": {"name": "🟩 النمط 3 (𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫)", "digits": "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"},
    "4": {"name": "🄲🄾🄾🄻 النمط 4 (⓪①②③④⑤⑥⑦⑧⑨)", "digits": "⓪①②③④⑤⑥⑦⑧⑨"}
}

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except: return {}

def save_data():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)

users = load_data()
running_accounts, login_states = {}, {}
bot = TelegramClient("bot_control_session", API_ID, API_HASH)

def get_user(uid):
    k = str(uid)
    if k not in users:
        users[k] = {"base_name": "Z", "font_type": "1", "accounts": []}
        save_data()
    return users[k]

def to_fancy_digits(text, font_type):
    normal = "0123456789"
    fancy = FONTS.get(font_type, FONTS["1"])["digits"]
    return str(text).translate(str.maketrans(normal, fancy))

async def check_subscription(event):
    if not event.is_private: return True
    try:
        await bot(GetParticipantRequest(channel=CHANNEL_USERNAME, participant=event.sender_id))
        return True
    except UserNotParticipantError:
        url = f"https://t.me{CHANNEL_USERNAME.replace('@', '')}"
        await event.reply("📢 **يجب الاشتراك في القناة أولاً!**", buttons=[Button.url("اضغط هنا للاشتراك", url)])
        return False
    except: return True

async def account_time_loop(session_key, client, user_id):
    last_time = ""
    try:
        while True:
            try:
                if not client.is_connected(): await client.connect()
                user = get_user(user_id)
                if session_key not in user["accounts"]: break
                now = datetime.datetime.now(ZoneInfo("Africa/Algiers")).strftime("%H:%M")
                fancy = to_fancy_digits(now, user.get("font_type", "1"))
                if fancy != last_time:
                    await client(UpdateProfileRequest(first_name=f"{user['base_name']} {fancy}"))
                    last_time = fancy
                await asyncio.sleep(30)
            except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
            except: await asyncio.sleep(15)
    except asyncio.CancelledError: pass
    finally:
        if client.is_connected(): await client.disconnect()

async def load_saved_sessions():
    await asyncio.sleep(2)
    for uid, udata in users.items():
        for acc in udata.get("accounts", []):
            try:
                if acc.startswith("1") and len(acc) > 40:
                    client = TelegramClient(StringSession(acc), API_ID, API_HASH, auto_reconnect=True)
                else:
                    client = TelegramClient(os.path.join(SESSIONS_DIR, acc), API_ID, API_HASH, auto_reconnect=True)
                await client.connect()
                if await client.is_user_authorized():
                    running_accounts[acc] = asyncio.create_task(account_time_loop(acc, client, int(uid)))
                else: await client.disconnect()
            except: pass

def main_kb():
    return [
        [Button.inline("➕ إضافة حساب", b"m_add"), Button.inline("⚙️ الزخرفات", b"m_fonts")],
        [Button.inline("📝 تغيير الاسم", b"m_name"), Button.inline("📊 المتصلة", b"m_status")],
        [Button.inline("🛑 إيقاف حساب", b"m_stop")]
    ]

@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_h(event):
    if not event.is_private or not await check_subscription(event): return
    get_user(event.sender_id)
    await event.reply("🤖 **لوحة التحكم بالوقت:**", buttons=main_kb())

@bot.on(events.CallbackQuery(pattern=r"^m_main$"))
async def m_main_cb(event):
    await event.edit("🤖 **لوحة التحكم الرئيسية:**", buttons=main_kb())

@bot.on(events.CallbackQuery(pattern=r"^m_choose$"))
async def m_choose_cb(event):
    await event.edit("➕ **إختر طريقة الإضافة:**\n\n💡 _استخدم الـ Session إذا واجهت مشكلة عدم وصول الرمز._", buttons=[
        [Button.inline("📱 عبر الرقم مباشرة", b"m_add_p")],
        [Button.inline("🔑 عبر كود الجلسة (Session)", b"m_add_s")],
        [Button.inline("🔙 عودة", b"m_main")]
    ])

@bot.on(events.CallbackQuery(pattern=r"^m_add$"))
async def m_add_cb(event):
    await m_choose_cb(event)

@bot.on(events.CallbackQuery(pattern=r"^m_add_s$"))
async def m_add_s_cb(event):
    login_states[event.sender_id] = {"step": "str_session"}
    await event.edit("🔑 **أرسل كود الـ StringSession الآن:**", buttons=[Button.inline("🔙 إلغاء", b"m_main")])

@bot.on(events.CallbackQuery(pattern=r"^m_add_p$"))
async def m_add_p_cb(event):
    login_states[event.sender_id] = {"step": "phone"}
    await event.edit("📱 **أرسل رقم الهاتف مع رمز الدولة:**\nمثال: `+213xxxxxxxxx`", buttons=[Button.inline("🔙 إلغاء", b"m_main")])

@bot.on(events.CallbackQuery(pattern=r"^m_fonts$"))
async def m_fonts_cb(event):
    user = get_user(event.sender_id)
    cur = user.get("font_type", "1")
    btns = []
    for fid, f in FONTS.items():
        txt = f"✅ {f['name']}" if fid == cur else f['name']
        btns.append([Button.inline(txt, f"s_f_{fid}".encode())])
    btns.append([Button.inline("🔙 عودة", b"m_main")])
    await event.edit("⚙️ **إختر نمط الزخرفة المفضل:**", buttons=btns)

@bot.on(events.CallbackQuery(pattern=r"^s_f_(\d+)$"))
async def s_f_cb(event):
    fid = event.pattern_match.group(1).decode()
    user = get_user(event.sender_id)
    user["font_type"] = fid
    save_data()
    await m_fonts_cb(event)

@bot.on(events.CallbackQuery(pattern=r"^m_name$"))
async def m_name_cb(event):
    user = get_user(event.sender_id)
    login_states[event.sender_id] = {"step": "name_in"}
    await event.edit(f"📝 **الاسم الحالي:** {user['base_name']}\n\nأرسل الاسم الجديد الآن:", buttons=[Button.inline("🔙 إلغاء", b"m_main")])

@bot.on(events.CallbackQuery(pattern=r"^m_status$"))
async def m_status_cb(event):
    user = get_user(event.sender_id)
    accs = user.get("accounts", [])
    if not accs: txt = "📊 لا توجد حسابات مرتبطة حالياً."
    else:
        txt = "📊 **الحسابات المتصلة:**\n\n"
        for i, acc in enumerate(accs, 1):
            txt += f"{i}️⃣ `{acc if len(acc) < 20 else f'Session الحساب {i}'}`\n"
    await event.edit(txt, buttons=[Button.inline("🔙 عودة", b"m_main")])

@bot.on(events.CallbackQuery(pattern=r"^m_stop$"))
async def m_stop_cb(event):
    user = get_user(event.sender_id)
    accs = user.get("accounts", [])
    if not accs:
        await event.edit("🛑 لا توجد حسابات لإيقافها.", buttons=[Button.inline("🔙 عودة", b"m_main")])
        return
    btns = [[Button.inline(f"❌ إيقاف: {a if len(a)<20 else f'الحساب {i+1}'}", f"st_{i}".encode())] for i, a in enumerate(accs)]
    btns.append([Button.inline("🔙 عودة", b"m_main")])
    await event.edit("🛑 **إختر الحساب المراد حذفه وإيقافه:**", buttons=btns)

@bot.on(events.CallbackQuery(pattern=r"^st_(\d+)$"))
async def st_cb(event):
    idx = int(event.pattern_match.group(1).decode())
    user = get_user(event.sender_id)
    accs = user.get("accounts", [])
    if 0 <= idx < len(accs):
        target = accs[idx]
        accs.remove(target)
        save_data()
        if target in running_accounts:
            running_accounts[target].cancel()
            del running_accounts[target]
        if not (target.startswith("1") and len(target) > 40):
            try: os.remove(os.path.join(SESSIONS_DIR, f"{target}.session"))
            except: pass
        await event.edit("🛑 تم إيقاف الحساب بنجاح.", buttons=[Button.inline("🔙 عودة", b"m_main")])
    else: await event.edit("❌ الحساب غير موجود.", buttons=[Button.inline("🔙 عودة", b"m_main")])

@bot.on(events.NewMessage)
async def text_h(event):
    if not event.is_private or event.text.startswith('/'): return
    cid = event.sender_id
    if cid not in login_states or not await check_subscription(event): return
    st = login_states[cid]
    inp = event.text.strip()

    if st["step"] == "name_in":
        if len(inp) > 40:
            await event.reply("❌ الاسم طويل جداً!")
            return
        user = get_user(cid)
        user["base_name"] = inp
        save_data()
        del login_states[cid]
        await event.reply(f"✅ تم تعديل الاسم إلى: {inp}", buttons=main_kb())

    elif st["step"] == "str_session":
        user = get_user(cid)
        if inp in user["accounts"]:
            await event.reply("⚠️ الحساب مضاف بالفعل!")
            del login_states[cid]
            return
        msg = await event.reply("⏳ جاري التحقق من الـ Session...")
        try:
            cl = TelegramClient(StringSession(inp), API_ID, API_HASH, auto_reconnect=True)
            await cl.connect()
            if not await cl.is_user_authorized():
                await msg.delete()
                await event.reply("❌ كود الجلسة غير صالح.")
                await cl.disconnect()
                del login_states[cid]
                return
            user["accounts"].append(inp)
            save_data()
            running_accounts[inp] = asyncio.create_task(account_time_loop(inp, cl, cid))
Utilisez le code avec précaution.
me = await cl.get_me()
await msg.delete()
await event.reply(f"✅ تم ربط الحساب: {me.first_name}", buttons=main_kb())
del login_states[cid]
except:
await event.reply("❌ فشل الاتصال بالجلسة.")
del login_states[cid]
elif st["step"] == "phone":
user = get_user(cid)
if inp in user["accounts"]:
await event.reply("⚠️ الحساب مضاف بالفعل!")
del login_states[cid]
return
msg = await event.reply(f"⏳ جاري طلب الرمز للرقم: {inp}...")
cl = TelegramClient(os.path.join(SESSIONS_DIR, inp), API_ID, API_HASH)
await cl.connect()
try:
res = await cl.send_code_request(inp)
st.update({"phone_code_hash": res.phone_code_hash, "phone": inp, "client": cl, "step": "code"})
await msg.delete()
await event.reply("📩 أرسل رمز التحقق الآن:")
except Exception as e:
await event.reply(f"❌ لم يرسل الرمز. استخدم خيار الـ Session للتخطي.\nالخطأ: {e}")
await cl.disconnect()
del login_states[cid]
elif st["step"] == "code":
cl, phone, hsh = st["client"], st["phone"], st["phone_code_hash"]
msg = await event.reply("⏳ جاري التحقق...")
try:
await cl.sign_in(phone=phone, code=inp, phone_code_hash=hsh)
user = get_user(cid)
if phone not in user["accounts"]:
user["accounts"].append(phone)
save_data()
running_accounts[phone] = asyncio.create_task(account_time_loop(phone, cl, cid))
me = await cl.get_me()
await msg.delete()
await event.reply(f"✅ تم تشغيل الحساب: {me.first_name}", buttons=main_kb())
del login_states[cid]
except SessionPasswordNeededError:
st["step"] = "password"
await msg.delete()
await event.reply("🔒 الحساب محمي بكلمة مرور، أرسلها الآن:")
except:
await event.reply("❌ الرمز خاطئ. تم إلغاء العملية.")
await cl.disconnect()
del login_states[cid]
elif st["step"] == "password":
cl, phone = st["client"], st["phone"]
msg = await event.reply("⏳ جاري التحقق...")
try:
await cl.sign_in(password=inp)
user = get_user(cid)
if phone not in user["accounts"]:
user["accounts"].append(phone)
save_data()
running_accounts[phone] = asyncio.create_task(account_time_loop(phone, cl, cid))
me = await cl.get_me()
await msg.delete()
await event.reply(f"✅ تم تشغيل الحساب: {me.first_name}", buttons=main_kb())
del login_states[cid]
except:
await event.reply("❌ كلمة المرور خاطئة. تم إلغاء العملية.")
await cl.disconnect()
del login_states[cid]
if name == "main":
loop = asyncio.get_event_loop()
loop.create_task(load_saved_sessions())
bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
