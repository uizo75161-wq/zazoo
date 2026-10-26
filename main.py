import asyncio
import datetime
import json
import os
import re
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events, Button
from telethon.errors import (
    ApiIdInvalidError,
    ApiIdPublishedFloodError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserNotParticipantError,
)
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.channels import GetParticipantRequest

# Railway Variables: API_ID, API_HASH, BOT_TOKEN
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

# في Railway اربط Volume بمسار /data واضبط DATA_DIR=/data لحفظ الجلسات بعد إعادة النشر.
DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "user_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
BOT_SESSION = os.path.join(DATA_DIR, "bot_control_session")

# غيّر هذا إلى اسم قناتك الحقيقي.
CHANNEL_USERNAME = "@YourChannelUsername"

FONTS = {
    "1": {"name": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "2": {"name": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗", "digits": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"},
    "3": {"name": "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫", "digits": "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫"},
    "4": {"name": "⓪①②③④⑤⑥⑦⑧⑨", "digits": "⓪①②③④⑤⑥⑦⑧⑨"},
}


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


users = load_data()
running_accounts = {}
login_states = {}


def save_data():
    temporary_file = DATA_FILE + ".tmp"
    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2, ensure_ascii=False)
    os.replace(temporary_file, DATA_FILE)


def get_user(user_id):
    key = str(user_id)
    if key not in users or not isinstance(users[key], dict):
        users[key] = {"base_name": "Z", "font_type": "1", "accounts": []}
        save_data()
    user = users[key]
    user.setdefault("base_name", "Z")
    user.setdefault("font_type", "1")
    user.setdefault("accounts", [])
    if not isinstance(user["accounts"], list):
        user["accounts"] = []
    if str(user.get("font_type")) not in FONTS:
        user["font_type"] = "1"
    return user


def to_fancy_digits(value, font_type):
    digits = FONTS.get(str(font_type), FONTS["1"])["digits"]
    return str(value).translate(str.maketrans("0123456789", digits))


def describe_code_delivery(sent):
    """وصف نوع الإرسال الذي أعاده Telegram؛ لا يعني ذلك ضمان وصول الرسالة فعلياً."""
    sent_type = type(getattr(sent, "type", None)).__name__
    delivery = {
        "SentCodeTypeApp": "تطبيق Telegram على جهاز مسجّل الدخول",
        "SentCodeTypeSms": "رسالة SMS",
        "SentCodeTypeCall": "مكالمة هاتفية آلية",
        "SentCodeTypeFlashCall": "مكالمة فائتة للتحقق من رقم المتصل",
        "SentCodeTypeMissedCall": "مكالمة فائتة؛ عادةً تُستخدم أرقامها الأخيرة كرمز",
        "SentCodeTypeEmailCode": "البريد الإلكتروني، إذا عرضه Telegram لهذا الحساب",
        "SentCodeTypeSetUpEmailRequired": "يلزم إعداد بريد إلكتروني حسب تعليمات Telegram",
        "SentCodeTypeFirebaseSms": "رسالة SMS عبر آلية تحقق خاصة بالتطبيقات الرسمية",
    }.get(sent_type, f"طريقة يحددها Telegram ({sent_type or 'غير معروفة'})")
    timeout = getattr(sent, "timeout", None)
    next_type = getattr(sent, "next_type", None)
    next_name = type(next_type).__name__ if next_type is not None else None
    details = f"📨 طريقة التحقق التي أعادها Telegram: **{delivery}**.\n"
    if timeout:
        details += f"⏳ مهلة الانتظار قبل إتاحة طريقة أخرى: {timeout} ثانية تقريباً.\n"
    if next_name:
        details += f"ℹ️ الطريقة التالية التي ذكرها Telegram: `{next_name}`.\n"
    details += (
        "ملاحظة: هذا يوضح نوع التسليم الذي اختاره Telegram فقط، ولا يؤكد أن الرسالة وصلت. "
        "إذا كانت الطريقة تطبيق Telegram، افتح محادثة Telegram الرسمية على جهاز مسجّل الدخول؛ "
        "ولا تفترض أن الرمز سيصل عبر SMS."
    )
    return details


async def close_login_state(user_id):
    state = login_states.pop(user_id, None)
    if not state:
        return
    client = state.get("client")
    if client:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception as exc:
            print(f"تعذر إغلاق اتصال تسجيل الدخول للمستخدم {user_id}: {type(exc).__name__}: {exc}")


async def check_subscription(event):
    if not event.is_private:
        return True
    try:
        await bot(GetParticipantRequest(channel=CHANNEL_USERNAME, participant=event.sender_id))
        return True
    except UserNotParticipantError:
        url = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        await event.reply(
            "📢 **عذراً، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت!**",
            buttons=[Button.url("اضغط هنا للاشتراك", url)],
        )
        return False
    except Exception as exc:
        print(f"خطأ فحص الاشتراك: {type(exc).__name__}: {exc}")
        await event.reply("⚠️ تعذر التحقق من اشتراك القناة حالياً. تحقق من اسم القناة وصلاحيات البوت.")
        return False


async def account_time_loop(phone_number, client, user_id):
    last_name = None
    try:
        while True:
            try:
                if not client.is_connected():
                    await client.connect()
                user = get_user(user_id)
                if phone_number not in user.get("accounts", []):
                    break

                raw_time = datetime.datetime.now(ZoneInfo("Africa/Algiers")).strftime("%H:%M")
                fancy_time = to_fancy_digits(raw_time, user.get("font_type", "1"))
                new_name = f"{user.get('base_name', 'Z')} {fancy_time}".strip()[:64]
                if new_name != last_name:
                    await client(UpdateProfileRequest(first_name=new_name))
                    last_name = new_name
                await asyncio.sleep(30)
            except FloodWaitError as exc:
                print(f"FloodWait للحساب {phone_number}: الانتظار {exc.seconds} ثانية")
                await asyncio.sleep(exc.seconds + 1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"خطأ تحديث الحساب {phone_number}: {type(exc).__name__}: {exc}")
                await asyncio.sleep(15)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception as exc:
            print(f"تعذر فصل جلسة {phone_number}: {type(exc).__name__}: {exc}")


async def load_saved_sessions():
    await asyncio.sleep(1)
    for user_id, user_data in list(users.items()):
        if not isinstance(user_data, dict):
            continue
        for phone in user_data.get("accounts", []):
            if phone in running_accounts and not running_accounts[phone].done():
                continue
            session_path = os.path.join(SESSIONS_DIR, phone)
            if not os.path.exists(session_path + ".session"):
                print(f"لا يوجد ملف جلسة محفوظ للحساب {phone}. تأكد من إعداد DATA_DIR وRailway Volume.")
                continue
            client = TelegramClient(session_path, API_ID, API_HASH, auto_reconnect=True)
            try:
                await client.connect()
                if await client.is_user_authorized():
                    running_accounts[phone] = asyncio.create_task(
                        account_time_loop(phone, client, int(user_id))
                    )
                    print(f"تم تحميل جلسة الحساب {phone}")
                else:
                    await client.disconnect()
                    print(f"جلسة الحساب {phone} غير مصرح بها")
            except Exception as exc:
                print(f"تعذر تحميل جلسة {phone}: {type(exc).__name__}: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass


def make_main_keyboard():
    return [
        [Button.inline("➕ إضافة حساب", b"menu_add"), Button.inline("⚙️ أنواع الزخرفات", b"menu_fonts")],
        [Button.inline("📝 تغيير الاسم", b"menu_name"), Button.inline("📊 الحسابات المتصلة", b"menu_status")],
        [Button.inline("🛑 إيقاف حساب", b"menu_stop")],
    ]


bot = TelegramClient(BOT_SESSION, API_ID, API_HASH)


@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    if not event.is_private or not await check_subscription(event):
        return
    await close_login_state(event.sender_id)
    get_user(event.sender_id)
    await event.reply(
        "🤖 **أهلاً بك في بوت إدارة حسابات الوقت**\n\nيمكنك التحكم عبر الأزرار أدناه:",
        buttons=make_main_keyboard(),
    )


@bot.on(events.CallbackQuery(pattern=b"^menu_main$"))
async def menu_main_callback(event):
    await close_login_state(event.sender_id)
    await event.edit(
        "🤖 **لوحة التحكم الرئيسية**\n\nاختر الإجراء المطلوب من الأزرار المتاحة:",
        buttons=make_main_keyboard(),
    )


@bot.on(events.CallbackQuery(pattern=b"^menu_fonts$"))
async def menu_fonts_callback(event):
    user = get_user(event.sender_id)
    current_font = str(user.get("font_type", "1"))
    buttons = []
    for fid, font in FONTS.items():
        label = f"✅ {font['name']}" if fid == current_font else font["name"]
        buttons.append([Button.inline(label, f"set_font_{fid}".encode())])
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("⚙️ **قائمة أنماط الأرقام:**\nاختر النمط الذي يناسبك لجميع حساباتك:", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=rb"^set_font_(\d+)$"))
async def set_font_callback(event):
    font_id = event.pattern_match.group(1).decode()
    if font_id not in FONTS:
        await event.answer("النمط غير معروف", alert=True)
        return
    user = get_user(event.sender_id)
    user["font_type"] = font_id
    save_data()
    buttons = []
    for fid, font in FONTS.items():
        label = f"✅ {font['name']}" if fid == font_id else font["name"]
        buttons.append([Button.inline(label, f"set_font_{fid}".encode())])
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("⚙️ **تم حفظ نمط الأرقام.**\nاختر نمطاً آخر أو عد إلى القائمة.", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=b"^menu_name$"))
async def menu_name_callback(event):
    await close_login_state(event.sender_id)
    user = get_user(event.sender_id)
    login_states[event.sender_id] = {"step": "change_name_input"}
    await event.edit(
        f"📝 **الاسم الحالي:** {user['base_name']}\n\n"
        "أرسل الاسم الجديد في رسالة عادية (بحد أقصى 40 حرفاً).\nأرسل /start للإلغاء.",
        buttons=[Button.inline("🔙 إلغاء وعودة", b"menu_main")],
    )


@bot.on(events.CallbackQuery(pattern=b"^menu_status$"))
async def menu_status_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        text = "📊 **الحسابات المرتبطة:**\n\nلا توجد حسابات مرتبطة حالياً."
    else:
        text = "📊 **الحسابات المرتبطة حالياً:**\n\n" + "\n".join(
            f"{idx}. `{acc}`" for idx, acc in enumerate(accounts, 1)
        )
    await event.edit(text, buttons=[Button.inline("🔙 عودة", b"menu_main")])


@bot.on(events.CallbackQuery(pattern=b"^menu_stop$"))
async def menu_stop_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        await event.edit("🛑 لا توجد حسابات مرتبطة لإيقافها.", buttons=[Button.inline("🔙 عودة", b"menu_main")])
        return
    buttons = [[Button.inline(f"❌ إيقاف الحساب: {acc}"[:60], f"action_stop_{acc}".encode())] for acc in accounts]
    buttons.append([Button.inline("🔙 عودة", b"menu_main")])
    await event.edit("🛑 **اختر الحساب المراد إيقافه وحذف جلسته:**", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=rb"^action_stop_(.+)$"))
async def action_stop_callback(event):
    phone = event.pattern_match.group(1).decode()
    user = get_user(event.sender_id)
    if phone not in user.get("accounts", []):
        await event.answer("هذا الحساب غير موجود ضمن حساباتك.", alert=True)
        return

    user["accounts"].remove(phone)
    save_data()
    task = running_accounts.pop(phone, None)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    session_file = os.path.join(SESSIONS_DIR, phone + ".session")
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(session_file + suffix)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"تعذر حذف ملف الجلسة: {exc}")

    await event.edit(f"🛑 تم إيقاف الحساب وفصل جلسته: `{phone}`", buttons=[Button.inline("🔙 عودة إلى التحكم", b"menu_main")])


@bot.on(events.CallbackQuery(pattern=b"^menu_add$"))
async def menu_add_callback(event):
    await close_login_state(event.sender_id)
    if not await check_subscription(event):
        return
    login_states[event.sender_id] = {"step": "phone"}
    await event.edit(
        "📱 **إضافة حساب جديد**\n\n"
        "أرسل رقم الهاتف بالصيغة الدولية، مثال: `+213XXXXXXXXX`.\n\n"
        "مهم: Telegram هو من يحدد طريقة وصول الرمز؛ قد يصل داخل تطبيق Telegram وليس SMS. "
        "لن نعتبر طلب الإرسال دليلاً على وصول الرسالة.",
        buttons=[Button.inline("🔙 إلغاء", b"menu_main")],
    )


@bot.on(events.NewMessage)
async def global_text_handler(event):
    if not event.is_private or not event.raw_text:
        return
    chat_id = event.sender_id
    state = login_states.get(chat_id)
    if not state:
        return
    if event.raw_text.startswith("/"):
        if event.raw_text.strip().lower() in ("/cancel", "/start"):
            await close_login_state(chat_id)
            await event.reply("تم إلغاء العملية.", buttons=make_main_keyboard())
        return
    if not await check_subscription(event):
        return

    user_input = event.raw_text.strip()

    if state["step"] == "change_name_input":
        if not user_input:
            await event.reply("❌ الاسم لا يمكن أن يكون فارغاً.")
            return
        if len(user_input) > 40:
            await event.reply("❌ الاسم طويل جداً؛ أرسل اسماً لا يتجاوز 40 حرفاً.")
            return
        user = get_user(chat_id)
        user["base_name"] = user_input
        save_data()
        login_states.pop(chat_id, None)
        await event.reply(f"✅ تم تعديل الاسم الأساسي إلى: {user_input}", buttons=make_main_keyboard())
        return

    if state["step"] == "phone":
        phone = user_input.replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            await event.reply("❌ صيغة الرقم غير صحيحة. أرسله بالصيغة الدولية مثل `+213XXXXXXXXX`.")
            return
        user = get_user(chat_id)
        if phone in user["accounts"]:
            await close_login_state(chat_id)
            await event.reply("⚠️ هذا الحساب مرتبط لديك بالفعل!", buttons=make_main_keyboard())
            return
        if phone in running_accounts and not running_accounts[phone].done():
            await close_login_state(chat_id)
            await event.reply("⚠️ توجد جلسة نشطة لهذا الرقم بالفعل.", buttons=make_main_keyboard())
            return

        session_path = os.path.join(SESSIONS_DIR, phone)
        client = TelegramClient(session_path, API_ID, API_HASH)
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
            login_states[chat_id] = {
                "step": "code",
                "phone_code_hash": sent.phone_code_hash,
                "phone": phone,
                "client": client,
            }
            await event.reply(
                f"✅ أعاد Telegram نتيجة لطلب الرمز للرقم `{phone}`.\n\n"
                f"{describe_code_delivery(sent)}\n\n"
                "إذا لم يصلك الرمز، افحص المكان الموضّح أعلاه. لا تطلب إعادة الإرسال بشكل متكرر.",
            )
        except PhoneNumberInvalidError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("❌ Telegram رفض الرقم باعتباره غير صالح. راجع رمز الدولة والرقم.")
        except PhoneNumberBannedError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("❌ Telegram أفاد بأن هذا الرقم محظور؛ لا يمكن إصلاح ذلك من كود البوت.")
        except PhoneNumberFloodError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("⏳ طلب Telegram رموزاً كثيرة لهذا الرقم. أوقف المحاولات وانتظر قبل التجربة مجدداً.")
        except FloodWaitError as exc:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply(f"⏳ Telegram فرض انتظاراً لمدة {exc.seconds} ثانية. حاول مرة واحدة بعد انتهاء المهلة.")
        except (ApiIdInvalidError, ApiIdPublishedFloodError) as exc:
            print(f"خطأ API Telegram: {type(exc).__name__}: {exc}")
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("❌ مشكلة في API_ID/API_HASH أو تقييد على بيانات API. راجع سجلات Railway وإعدادات API.")
        except Exception as exc:
            print(f"فشل طلب الرمز للرقم {phone}: {type(exc).__name__}: {exc}")
            try:
                await client.disconnect()
            except Exception:
                pass
            login_states.pop(chat_id, None)
            await event.reply(f"❌ فشل طلب الرمز: `{type(exc).__name__}`. راجع Logs في Railway لمعرفة التفاصيل.")
        return

    if state["step"] == "code":
        code = re.sub(r"\s+", "", user_input)
        client = state["client"]
        phone = state["phone"]
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=state["phone_code_hash"])
        except PhoneCodeInvalidError:
            # ابقِ المحاولة مفتوحة للسماح بإدخال الرمز الصحيح دون إنشاء طلب جديد.
            await event.reply("❌ الرمز الذي أدخلته غير صحيح. أدخل أحدث رمز وصلك من Telegram كما هو.")
            return
        except PhoneCodeExpiredError:
            await close_login_state(chat_id)
            await event.reply("⌛ انتهت صلاحية الرمز. اضغط إضافة حساب واطلب رمزاً جديداً مرة واحدة.", buttons=make_main_keyboard())
            return
        except SessionPasswordNeededError:
            state["step"] = "password"
            await event.reply("🔒 الحساب محمي بالتحقق بخطوتين. أرسل كلمة المرور لإكمال تسجيل الدخول.")
            return
        except Exception as exc:
            print(f"فشل التحقق من رمز {phone}: {type(exc).__name__}: {exc}")
            await close_login_state(chat_id)
            await event.reply(f"❌ فشل التحقق: `{type(exc).__name__}`. راجع Logs في Railway.", buttons=make_main_keyboard())
            return

        user = get_user(chat_id)
        if phone not in user["accounts"]:
            user["accounts"].append(phone)
            save_data()
        task = asyncio.create_task(account_time_loop(phone, client, chat_id))
        running_accounts[phone] = task
        me = await client.get_me()
        login_states.pop(chat_id, None)
        await event.reply(f"✅ تم ربط وتشغيل الحساب بنجاح!\n👤 الحساب: {me.first_name}", buttons=make_main_keyboard())
        return

    if state["step"] == "password":
        client = state["client"]
        phone = state["phone"]
        try:
            await client.sign_in(password=user_input)
        except PasswordHashInvalidError:
            await event.reply("❌ كلمة المرور غير صحيحة. أعد إدخال كلمة مرور التحقق بخطوتين.")
            return
        except Exception as exc:
            print(f"فشل تحقق كلمة مرور {phone}: {type(exc).__name__}: {exc}")
            await close_login_state(chat_id)
            await event.reply(f"❌ فشل التحقق: `{type(exc).__name__}`. راجع Logs في Railway.", buttons=make_main_keyboard())
            return

        user = get_user(chat_id)
        if phone not in user["accounts"]:
            user["accounts"].append(phone)
            save_data()
        task = asyncio.create_task(account_time_loop(phone, client, chat_id))
        running_accounts[phone] = task
        me = await client.get_me()
        login_states.pop(chat_id, None)
        await event.reply(f"✅ تم ربط وتشغيل الحساب بنجاح!\n👤 الحساب: {me.first_name}", buttons=make_main_keyboard())


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("البوت يعمل.")
    await load_saved_sessions()
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
