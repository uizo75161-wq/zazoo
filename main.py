import asyncio
import datetime
import os
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events, Button
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import FloodWaitError, SessionPasswordNeededError, UserNotParticipantError

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_NAME = os.getenv("BASE_NAME", "Z")
CHANNEL_USERNAME = "@https://t.me/zadneverdie"

SESSIONS_DIR = "user_sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

running_accounts = {}
login_states = {}

bot = TelegramClient('bot_control_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)


def to_fancy_digits(text):
    normal_digits = "0123456789"
    fancy_digits = "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"
    digits_map = str.maketrans(normal_digits, fancy_digits)
    return str(text).translate(digits_map)


async def check_subscription(event):
    if event.is_private:
        try:
            await bot(GetParticipantRequest(
                channel=CHANNEL_USERNAME,
                participant=event.sender_id
            ))
            return True
        except UserNotParticipantError:
            url = f"https://t.me{CHANNEL_USERNAME.replace('@', '')}"
            await event.reply(
                "**Sorry, you need to join my channel!**",
                buttons=[Button.url("Join the channel", url)]
            )
            return False
        except Exception:
            return True
    return True


async def account_time_loop(phone_number, client):
    last_time = ""
    try:
        while True:
            try:
                if not client.is_connected():
                    await client.connect()

                raw_time = datetime.datetime.now(
                    ZoneInfo("Africa/Algiers")
                ).strftime("%H:%M")

                fancy_time = to_fancy_digits(raw_time)

                if fancy_time != last_time:
                    new_name = f"{BASE_NAME} {fancy_time}"
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

    for file in os.listdir(SESSIONS_DIR):
        if file.endswith(".session") and not file.startswith("bot_control_session"):
            phone = file.replace(".session", "")

            try:
                session_path = os.path.join(SESSIONS_DIR, phone)
                client = TelegramClient(
                    session_path,
                    API_ID,
                    API_HASH,
                    auto_reconnect=True
                )

                await client.connect()

                if await client.is_user_authorized():
                    running_accounts[phone] = {
                        "client": client,
                        "task": asyncio.create_task(
                            account_time_loop(phone, client)
                        )
                    }
                else:
                    await client.disconnect()

            except Exception:
                pass


@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await check_subscription(event):
        return

    welcome_text = (
        "**Welcome to Zad Bot**\n\n"
        "Available commands:\n"
        "1. To add a new account:\n `/add`\n"
        "2. To check the status of online accounts:\n `/status`"
    )

    await event.reply(welcome_text)


@bot.on(events.NewMessage(pattern='/add'))
async def add_account_start(event):
    if not await check_subscription(event):
        return

    chat_id = event.chat_id
    login_states[chat_id] = {"step": "phone"}

    await event.reply(
        "Please send your phone number with the country code.\n"
        "Example: `+213xxxxxxxxx`"
    )


@bot.on(events.NewMessage)
async def login_flow_handler(event):
    chat_id = event.chat_id

    if chat_id not in login_states or event.text.startswith('/'):
        return

    if not await check_subscription(event):
        return

    state = login_states[chat_id]
    user_input = event.text.strip()

    if state["step"] == "phone":
        phone = user_input

        await event.reply(
            f"Connecting and requesting a verification code for: `{phone}`..."
        )

        session_path = os.path.join(SESSIONS_DIR, phone)
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()

        try:
            send_code_result = await client.send_code_request(phone)

            state["phone_code_hash"] = send_code_result.phone_code_hash
            state["phone"] = phone
            state["client"] = client
            state["step"] = "code"

            await event.reply(
                "Telegram has sent a verification code. Please enter it here:"
            )

        except Exception as e:
            await event.reply(
                f"An error occurred while sending the code: {e}"
            )
            await client.disconnect()
            del login_states[chat_id]

    elif state["step"] == "code":
        code = user_input
        client = state["client"]
        phone = state["phone"]
        phone_code_hash = state["phone_code_hash"]

        await event.reply("Verifying the code...")

        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )

            running_accounts[phone] = {
                "client": client,
                "task": asyncio.create_task(
                    account_time_loop(phone, client)
                )
            }

            me = await client.get_me()

            await event.reply(
                f"**Account connected and started successfully!**\n"
                f"Name: {me.first_name}"
            )

            del login_states[chat_id]

        except SessionPasswordNeededError:
            state["step"] = "password"

            await event.reply(
                "This account is protected by two-step verification.\n"
                "Please enter your password:"
            )

        except Exception as e:
            await event.reply(
                f"Incorrect code or an error occurred: {e}\n"
                "The operation has been cancelled."
            )

            await client.disconnect()
            del login_states[chat_id]

    elif state["step"] == "password":
        password = user_input
        client = state["client"]
        phone = state["phone"]

        await event.reply("Verifying the password...")

        try:
            await client.sign_in(password=password)

            running_accounts[phone] = {
                "client": client,
                "task": asyncio.create_task(
                    account_time_loop(phone, client)
                )
            }

            me = await client.get_me()

            await event.reply(
                f"**Account verified and started successfully!**\n"
                f"Name: {me.first_name}"
            )

            del login_states[chat_id]

        except Exception as e:
            await event.reply(
                f"Incorrect password: {e}\n"
                "The operation has been cancelled."
            )

            await client.disconnect()
            del login_states[chat_id]


@bot.on(events.NewMessage(pattern='/stop'))
async def stop_account_handler(event):
    if not await check_subscription(event):
        return

    parts = event.text.split(maxsplit=1)

    if len(parts) < 2:
        await event.reply(
            "Please provide the phone number of the account to stop.\n"
            "Example:\n`/stop +213566547854`"
        )
        return

    phone = parts[1].strip()

    if phone not in running_accounts:
        await event.reply(
            "This phone number is not currently in the list of active accounts."
        )
        return

    running_accounts[phone]["task"].cancel()
    del running_accounts[phone]

    session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")

    if os.path.exists(session_file):
        try:
            os.remove(session_file)
        except Exception:
            pass

    await event.reply(
        f"Account `{phone}` has been stopped and its session file deleted."
    )


@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    if not await check_subscription(event):
        return

    if not running_accounts:
        await event.reply("There are currently no running accounts.")
        return

    status_text = "**Currently running accounts:**\n\n"

    for idx, phone in enumerate(running_accounts.keys(), 1):
        status_text += f"{idx}. Phone number: `{phone}`\n"

    await event.reply(status_text)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(load_saved_sessions())

    try:
        bot.run_until_disconnected()
    except KeyboardInterrupt:
        pass
