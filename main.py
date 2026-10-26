import asyncio
import json
import os

from telethon import TelegramClient, events

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

DATA_DIR = os.getenv("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "users.json")

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data():
    temporary_file = DATA_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)

    os.replace(temporary_file, DATA_FILE)

users = load_data()

bot = TelegramClient(
    "bot_control_session",
    API_ID,
    API_HASH
).start(bot_token=BOT_TOKEN)


def get_user(user_id):
    key = str(user_id)

    if key not in users:
        users[key] = {
            "base_name": "Z",
            "accounts": []
        }
        save_data()

    return users[key]


@bot.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    if not event.is_private:
        return

    get_user(event.sender_id)

    await event.reply(
        "Welcome to the account management bot.\n\n"
        "Available commands:\n"
        "/name - Set your preferred name\n"
        "/status - View your account list\n"
        "/add - Learn about secure account linking\n"
        "/stop - View account management instructions"
    )


@bot.on(events.NewMessage(pattern=r"^/name(?:\s+(.+))?$"))
async def name_handler(event):
    if not event.is_private:
        return

    match = event.pattern_match
    new_name = match.group(1)

    user = get_user(event.sender_id)

    if not new_name:
        await event.reply(
            f"Your current name is: {user['base_name']}\n"
            "Set a new name with /name YourName\n"
            "Use /name Z to restore the default."
        )
        return

    new_name = new_name.strip()

    if len(new_name) > 40:
        await event.reply("The name must be 40 characters or fewer.")
        return

    user["base_name"] = new_name
    save_data()

    await event.reply(f"Your preferred name has been set to: {new_name}")


@bot.on(events.NewMessage(pattern=r"^/status$"))
async def status_handler(event):
    if not event.is_private:
        return

    user = get_user(event.sender_id)
    accounts = user["accounts"]

    if not accounts:
        await event.reply(
            f"Preferred name: {user['base_name']}\n"
            "No linked accounts are registered."
        )
        return

    account_list = "\n".join(
        f"{index}. {account}"
        for index, account in enumerate(accounts, start=1)
    )

    await event.reply(
        f"Preferred name: {user['base_name']}\n"
        f"Registered accounts:\n{account_list}"
    )


@bot.on(events.NewMessage(pattern=r"^/add$"))
async def add_handler(event):
    if not event.is_private:
        return

    get_user(event.sender_id)

    await event.reply(
        "Secure account linking is not configured in this example.\n"
        "Do not send verification codes or passwords to this bot."
    )


@bot.on(events.NewMessage(pattern=r"^/stop$"))
async def stop_handler(event):
    if not event.is_private:
        return

    user = get_user(event.sender_id)

    await event.reply(
        "Account management instructions:\n"
        "No active account sessions are managed by this example.\n"
        f"Your current preferred name is: {user['base_name']}"
    )


async def main():
    print("Bot is running.")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
