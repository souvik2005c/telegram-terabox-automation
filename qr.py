
import asyncio
import os

import qrcode
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "").strip()

# IMPORTANT: Use the SAME session name as in tele.py.
# If tele.py uses TelegramClient("telegram_session", ...),
# keep this value as "telegram_session".
SESSION_NAME = "telegram_session"


async def main():
    if not API_ID or not API_HASH:
        print("Check TG_API_ID and TG_API_HASH in your .env file.")
        return

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    try:
        if await client.is_user_authorized():
            print("This session is already logged in!")
        else:
            qr = await client.qr_login()

            print("\nScan this QR code using Telegram on your phone:\n")
            image = qrcode.QRCode(border=2)
            image.add_data(qr.url)
            image.make(fit=True)
            image.print_ascii(invert=True)

            print("\nOn your phone, open Telegram:")
            print("Settings > Devices > Link Desktop Device")
            print("Scan the QR code shown above.")
            print("Keep this terminal open while scanning.\n")

            try:
                await qr.wait()
            except SessionPasswordNeededError:
                password = input(
                    "Enter your Telegram two-step verification password: "
                )
                await client.sign_in(password=password)

            print("\nQR login successful!")

        me = await client.get_me()
        print(f"Logged in as: {me.first_name}")
        print("Session is saved. You can now run your main script.")

    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
