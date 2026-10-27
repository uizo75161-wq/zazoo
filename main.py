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

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "user_sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
BOT_SESSION = os.path.join(DATA_DIR, "bot_control_session")

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()

def normalize_channel_username(value):
    value = (value or "").strip()
    if not value:
        return ""
    value = re.sub(r"^https?://t\.me/", "", value, flags=re.IGNORECASE).strip("/ ")
    value = value.split("?")[0].strip()
    if value and not value.startswith("@"): 
        value = "@" + value
    return value

CHANNEL_USERNAME = normalize_channel_username(CHANNEL_USERNAME)

FONTS = {
    "1": {"name": "0123456789 (Normal)", "digits": "0123456789"},
    "2": {"name": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿 (Monospace)", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "3": {"name": "0123456789 (Bold Serif)", "digits": "0123456789"},
    "4": {"name": "0123456789 (Sans-Serif)", "digits": "0123456789"},
    "5": {"name": "0123456789 (Sans Bold)", "digits": "0123456789"},
    "6": {"name": "⓪①②③④⑤⑥⑦⑧⑨ (Circled)", "digits": "⓪①②③④⑤⑥⑦⑧⑨"},
    "7": {"name": "0123456789 (Squared)", "digits": "🄀⒈⒉⒊⒋⒌⒍⒎⒏⒐"},
    "8": {"name": "⓿❶❷❸❹❺❻❼❽❾ (Dark Circled)", "digits": "⓿❶❷❸❹❺❻❼❽❾"},
    "9": {"name": "0123456789 (Italic Sans)", "digits": "0123456789"},
    "10": {"name": "0123456789 (Italic Bold Sans)", "digits": "0123456789"},
    "11": {"name": "0123456789 (Fraktur)", "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "12": {"name": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡 (Double Struck)", "digits": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"},
    "13": {"name": "0123456789 (Tortoise)", "digits": "🄋🄌🄍🄎🄏🄐🄑🄒🄓🄔"},
    "14": {"name": "0123456789 (Math Sans Bold)", "digits": "0123456789"},
    "15": {"name": "0123456789 (Math Italic)", "digits": "🟶🟷🟸🟹🟺🟻🟼🟽🟾🟿"},
    "16": {"name": "0123456789 (Math Bold Italic)", "digits": "0123456789"},
    "17": {"name": "0123456789 (Serif Bold Italic)", "digits": "🟶🟷🟸🟹🟺🟻🟼🟽🟾🟿"},
    "18": {"name": "0️⃣1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣ (Keycap)", "digits": "0️⃣1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣"},
    "19": {"name": "0123456789 (Comma-like)", "digits": "🄀🄁🄂🄃🄄🄅🄆🄇🄈🄉"},
    "20": {"name": "0123456789 (Subscript Style)", "digits": "₀₁₂₃₄₅₆₇₈₉"},
    "21": {"name": "⁰¹²³⁴⁵⁶⁷⁸⁹ (Superscript)", "digits": "⁰¹²³⁴⁵⁶⁷⁸⁹"},
    "22": {"name": "🯰🯱🯲🯳🯴🯵🯶🯷🯸🯹 (Segment)", "digits": "🯰🯱🯲🯳🯴🯵🯶🯷🯸🯹"},
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
        users[key] = {"font_type": "1", "accounts": [], "account_names": {}}
        save_data()
    user = users[key]
    user.setdefault("font_type", "1")
    user.setdefault("accounts", [])
    user.setdefault("account_names", {})
    if not isinstance(user["accounts"], list):
        user["accounts"] = []
    if not isinstance(user["account_names"], dict):
        user["account_names"] = {}
    if str(user.get("font_type")) not in FONTS:
        user["font_type"] = "1"
    return user

def to_fancy_digits(value, font_type):
    digits = FONTS.get(str(font_type), FONTS["1"])["digits"]
    return str(value).translate(str.maketrans("0123456789", digits))

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
            print(f"Error closing login state for user {user_id}: {type(exc).__name__}: {exc}")

async def check_subscription(event):
    if not event.is_private:
        return True

    if not CHANNEL_USERNAME or CHANNEL_USERNAME.lower() == "@yourchannelusername":
        print("Missing config: Add CHANNEL_USERNAME in Railway Variables")
        await event.reply(
            "Subscription channel is not configured in the bot.\n\n"
            "Please add CHANNEL_USERNAME in Railway Variables and redeploy."
        )
        return False

    try:
        await bot(GetParticipantRequest(channel=CHANNEL_USERNAME, participant=event.sender_id))
        return True
    except UserNotParticipantError:
        channel_link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        buttons = [
            [Button.url("Join Channel", channel_link)],
            [Button.inline("Verify Subscription", b"check_subscription")],
        ]
        await event.reply(
            "To use this bot, you must subscribe to our channel first.\n\n"
            "1) Click Join Channel.\n"
            "2) Subscribe and return here to click Verify Subscription.",
            buttons=buttons,
        )
        return False
    except Exception as exc:
        error_name = type(exc).__name__
        print(f"Subscription check error for {CHANNEL_USERNAME}: {error_name}: {exc}")
        await event.reply("Subscription check failed. Please ensure the bot is an admin in the channel.")
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
                
                base_name = user.get("account_names", {}).get(phone_number, "Z")
                new_name = f"{base_name} {fancy_time}".strip()[:64]
                if new_name != last_name:
                    await client(UpdateProfileRequest(first_name=new_name))
                    last_name = new_name
                await asyncio.sleep(30)
            except FloodWaitError as exc:
                print(f"FloodWait for account {phone_number}: Waiting {exc.seconds} seconds")
                await asyncio.sleep(exc.seconds + 1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"Update error for account {phone_number}: {type(exc).__name__}: {exc}")
                await asyncio.sleep(15)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception as exc:
            print(f"Failed to disconnect session {phone_number}: {type(exc).__name__}: {exc}")

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
                print(f"No session file found for account {phone}.")
                continue
            client = TelegramClient(session_path, API_ID, API_HASH, auto_reconnect=True)
            try:
                await client.connect()
                if await client.is_user_authorized():
                    running_accounts[phone] = asyncio.create_task(
                        account_time_loop(phone, client, int(user_id))
                    )
                    print(f"Loaded session for account {phone}")
                else:
                    await client.disconnect()
                    print(f"Session unauthorized for account {phone}")
            except Exception as exc:
                print(f"Could not load session {phone}: {type(exc).__name__}: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass

def make_main_keyboard():
    return [
        [Button.inline("Add Account", b"menu_add"), Button.inline("Font Styles", b"menu_fonts")],
        [Button.inline("Change Name", b"menu_name_select"), Button.inline("Status Dashboard", b"menu_status")],
        [Button.inline("Stop Account", b"menu_stop")],
    ]

bot = TelegramClient(BOT_SESSION, API_ID, API_HASH)

@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    if not event.is_private or not await check_subscription(event):
        return
    await close_login_state(event.sender_id)
    get_user(event.sender_id)
    await event.reply(
        "Welcome to Time Account Manager Bot\n\nControl your accounts using the buttons below:",
        buttons=make_main_keyboard(),
    )

@bot.on(events.CallbackQuery(pattern=b"^check_subscription$"))
async def check_subscription_callback(event):
    if not CHANNEL_USERNAME or CHANNEL_USERNAME.lower() == "@yourchannelusername":
        await event.answer("CHANNEL_USERNAME configuration missing.", alert=True)
        return
    try:
        await bot(GetParticipantRequest(channel=CHANNEL_USERNAME, participant=event.sender_id))
    except UserNotParticipantError:
        channel_link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        await event.answer("Subscription not found. Join the channel first.", alert=True)
        try:
            await event.edit(
                "You must join our channel to use this bot.\n\nSubscribe and press Verify Subscription.",
                buttons=[
                    [Button.url("Join Channel", channel_link)],
                    [Button.inline("Verify Subscription", b"check_subscription")],
                ],
            )
        except Exception:
            pass
        return
    except Exception as exc:
        await event.answer("Verification failed. Please contact support.", alert=True)
        return

    await event.answer("Subscription verified")
    await event.edit(
        "Welcome to Time Account Manager Bot\n\nSubscription verified. You can use the buttons below:",
        buttons=make_main_keyboard(),
    )

@bot.on(events.CallbackQuery(pattern=b"^menu_main$"))
async def menu_main_callback(event):
    await close_login_state(event.sender_id)
    await event.edit(
        "Main Dashboard\n\nChoose an action from the options below:",
        buttons=make_main_keyboard(),
    )

@bot.on(events.CallbackQuery(pattern=b"^menu_fonts$"))
async def menu_fonts_callback(event):
    user = get_user(event.sender_id)
    current_font = str(user.get("font_type", "1"))
    buttons = []
    row = []
    for fid, font in FONTS.items():
        label = f"Selected {font['name']}" if fid == current_font else font["name"]
        row.append(Button.inline(label, f"set_font_{fid}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("Back", b"menu_main")])
    await event.edit("Font Styles Menu\nSelect your preferred digit style for all accounts:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=rb"^set_font_(\d+)$"))
async def set_font_callback(event):
    font_id = event.pattern_match.group(1).decode()
    if font_id not in FONTS:
        await event.answer("Unknown font style", alert=True)
        return
    user = get_user(event.sender_id)
    user["font_type"] = font_id
    save_data()

    buttons = []
    row = []
    for fid, font in FONTS.items():
        label = f"Selected {font['name']}" if fid == font_id else font["name"]
        row.append(Button.inline(label, f"set_font_{fid}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("Back", b"menu_main")])
    await event.edit("Font style saved successfully.\nSelect another style or go back.", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b"^menu_name_select$"))
async def menu_name_select_callback(event):
    await close_login_state(event.sender_id)
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])

    if not accounts:
        await event.edit("No linked accounts available to rename. Please add an account first.", buttons=[Button.inline("Back", b"menu_main")])
        return

    buttons = []
    for acc in accounts:
        current_name = user.get("account_names", {}).get(acc, "Z")
        buttons.append([Button.inline(f"{acc} ({current_name})", f"name_edit_{acc}".encode())])

    buttons.append([Button.inline("Back", b"menu_main")])
    await event.edit("Select the account you want to rename:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=rb"^name_edit_(.+)$"))
async def name_edit_callback(event):
    phone = event.pattern_match.group(1).decode()
    user = get_user(event.sender_id)

    if phone not in user.get("accounts", []):
        await event.answer("Account not found.", alert=True)
        return

    login_states[event.sender_id] = {
        "step": "change_name_input",
        "target_phone": phone
    }

    current_name = user.get("account_names", {}).get(phone, "Z")
    await event.edit(
        f"Account: {phone}\n"
        f"Current Name: {current_name}\n\n"
        "Send the new base name in a normal text message (Max 40 characters).\nSend /start to cancel.",
        buttons=[Button.inline("Cancel", b"menu_name_select")],
    )

@bot.on(events.CallbackQuery(pattern=b"^menu_status$"))
async def menu_status_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        text = "Status Dashboard\n\nNo accounts linked currently."
    else:
        text = "Linked Accounts Status:\n\n"
        for idx, acc in enumerate(accounts, 1):
            c_name = user.get("account_names", {}).get(acc, "Z")
            text += f"{idx}. {acc} -> {c_name}\n"

    await event.edit(text, buttons=[Button.inline("Back", b"menu_main")])

@bot.on(events.CallbackQuery(pattern=b"^menu_stop$"))
async def menu_stop_callback(event):
    user = get_user(event.sender_id)
    accounts = user.get("accounts", [])
    if not accounts:
        await event.edit("No linked accounts available to stop.", buttons=[Button.inline("Back", b"menu_main")])
        return
    buttons = [[Button.inline(f"Stop: {acc}"[:60], f"action_stop_{acc}".encode())] for acc in accounts]
    buttons.append([Button.inline("Back", b"menu_main")])
    await event.edit("Select the account you want to stop and remove:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=rb"^action_stop_(.+)$"))
async def action_stop_callback(event):
    phone = event.pattern_match.group(1).decode()
    user = get_user(event.sender_id)
    if phone not in user.get("accounts", []):
        await event.answer("This account does not belong to you.", alert=True)
        return

    user["accounts"].remove(phone)
    if phone in user.get("account_names", {}):
        user["account_names"].pop(phone)
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
            print(f"Could not remove session file: {exc}")

    await event.edit(f"Stopped and disconnected account: {phone}", buttons=[Button.inline("Back to Menu", b"menu_main")])

@bot.on(events.CallbackQuery(pattern=b"^menu_add$"))
async def menu_add_callback(event):
    await close_login_state(event.sender_id)
    if not await check_subscription(event):
        return
    login_states[event.sender_id] = {"step": "phone"}
    await event.edit(
        "Add New Account\n\n"
        "Send the phone number in international format, e.g., +213XXXXXXXXX.\n\n"
        "Note: Telegram decides how the code is sent. Check your active Telegram apps.",
        buttons=[Button.inline("Cancel", b"menu_main")],
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
            await event.reply("Operation canceled.", buttons=make_main_keyboard())
        return
    if not await check_subscription(event):
        return

    user_input = event.raw_text.strip()

    if state["step"] == "change_name_input":
        if not user_input:
            await event.reply("Name cannot be empty.")
            return
        if len(user_input) > 40:
            await event.reply("Name is too long. Max 40 characters.")
            return

        target_phone = state["target_phone"]
        user = get_user(chat_id)
        user["account_names"][target_phone] = user_input
        save_data()

        login_states.pop(chat_id, None)
        await event.reply(f"Base name updated for account {target_phone} to: {user_input}", buttons=make_main_keyboard())
        return

    if state["step"] == "phone":
        phone = user_input.replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            await event.reply("Invalid format. Please use international format like +213XXXXXXXXX.")
            return
        user = get_user(chat_id)
        if phone in user["accounts"]:
            await close_login_state(chat_id)
            await event.reply("This account is already linked.", buttons=make_main_keyboard())
            return
        if phone in running_accounts and not running_accounts[phone].done():
            await close_login_state(chat_id)
            await event.reply("An active session already exists for this number.", buttons=make_main_keyboard())
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
            await event.reply(f"Telegram sent a verification code request for {phone}. Please enter the code below:")
        except PhoneNumberInvalidError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("Telegram rejected this number as invalid. Please check the code and number.")
        except PhoneNumberBannedError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("This number is banned from Telegram.")
        except PhoneNumberFloodError:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("Too many attempts for this number. Please wait and try again later.")
        except FloodWaitError as exc:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply(f"Flood wait active. Please try again after {exc.seconds} seconds.")
        except (ApiIdInvalidError, ApiIdPublishedFloodError) as exc:
            await client.disconnect()
            login_states.pop(chat_id, None)
            await event.reply("API key error. Check your API_ID and API_HASH settings in Railway.")
        except Exception as exc:
            try:
                await client.disconnect()
            except Exception:
                pass
            login_states.pop(chat_id, None)
            await event.reply(f"Request failed: {type(exc).__name__}. Check Railway logs for details.")
        return

    if state["step"] == "code":
        code = re.sub(r"\s+", "", user_input)
        client = state["client"]
        phone = state["phone"]
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=state["phone_code_hash"])
        except PhoneCodeInvalidError:
            await event.reply("Invalid code. Please enter the correct code.")
            return
        except PhoneCodeExpiredError:
            await close_login_state(chat_id)
            await event.reply("Code expired. Please request a new code.", buttons=make_main_keyboard())
            return
        except SessionPasswordNeededError:
            state["step"] = "password"
            await event.reply("Two-step verification password is required. Please send your password:")
            return
        except Exception as exc:
            await close_login_state(chat_id)
            await event.reply(f"Verification failed: {type(exc).__name__}.", buttons=make_main_keyboard())
            return

        user = get_user(chat_id)
        if phone not in user["accounts"]:
            user["accounts"].append(phone)
            user["account_names"].setdefault(phone, "Z")
        save_data()

        task = asyncio.create_task(account_time_loop(phone, client, chat_id))
        running_accounts[phone] = task
        login_states.pop(chat_id, None)
        await event.reply(f"Account linked and started successfully. You can now customize its name from the dashboard.", buttons=make_main_keyboard())
        return

    if state["step"] == "password":
        client = state["client"]
        phone = state["phone"]
        try:
            await client.sign_in(password=user_input)
        except PasswordHashInvalidError:
            await event.reply("Incorrect password. Please try again:")
            return
        except Exception as exc:
            await close_login_state(chat_id)
            await event.reply(f"Password verification failed: {type(exc).__name__}.", buttons=make_main_keyboard())
            return

        user = get_user(chat_id)
        if phone not in user["accounts"]:
            user["accounts"].append(phone)
            user["account_names"].setdefault(phone, "Z")
        save_data()

        task = asyncio.create_task(account_time_loop(phone, client, chat_id))
        running_accounts[phone] = task
        login_states.pop(chat_id, None)
        await event.reply(f"Account linked and started successfully. You can now customize its name from the dashboard.", buttons=make_main_keyboard())

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Bot is running.")
    await load_saved_sessions()
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
