
import asyncio
import os
import re
import sqlite3
from urllib.parse import urlparse

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import ChatInviteAlready

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "").strip()
SOURCE_CHANNEL = os.getenv(
    "SOURCE_CHANNEL",
    "https://t.me/+YIddoz87wW0yMDA0",
).strip()
GENERATOR_BOT = os.getenv("GENERATOR_BOT", "@TeraBestBot").strip()
RESULT_TIMEOUT = int(os.getenv("RESULT_TIMEOUT", "180"))

DEFAULT_DOMAINS = (
    "terabox.com,1024terabox.com,1024tera.com,"
    "teraboxapp.com,terabox.app,4funbox.com"
)

TERABOX_DOMAINS = {
    domain.strip().lower().lstrip(".")
    for domain in os.getenv(
        "RESULT_DOMAINS", DEFAULT_DOMAINS
    ).split(",")
    if domain.strip()
}

DB_FILE = "jobs.db"
LINKS_FILE = "links.txt"
OUTPUT_FILE = "output.txt"
SESSION_NAME = "telegram_session"

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


# ============================================================
# DATABASE
# ============================================================

def connect_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def initialize_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                generated_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()

    # A previous run may have stopped while processing a link.
    # Do not automatically resend it: the bot may have processed it.
    with connect_db() as db:
        db.execute("""
            UPDATE jobs
            SET status = 'needs_review',
                last_error = 'Previous run stopped during processing; check bot chat before retrying.'
            WHERE status = 'processing'
        """)
        db.commit()


def add_job(message_id, url):
    with connect_db() as db:
        cursor = db.execute("""
            INSERT OR IGNORE INTO jobs
                (message_id, source_url, status)
            VALUES (?, ?, 'pending')
        """, (message_id, url))
        db.commit()
        return cursor.rowcount > 0


def get_jobs(status=None):
    with connect_db() as db:
        if status:
            return db.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY id",
                (status,),
            ).fetchall()

        return db.execute(
            "SELECT * FROM jobs ORDER BY id"
        ).fetchall()


def update_job(job_id, status, generated_url=None, error=None):
    with connect_db() as db:
        db.execute("""
            UPDATE jobs
            SET status = ?,
                generated_url = ?,
                last_error = ?
            WHERE id = ?
        """, (status, generated_url, error, job_id))
        db.commit()


# ============================================================
# LINK HELPERS
# ============================================================

def clean_url(url):
    return url.rstrip(".,;:!?)]}>")


def is_terabox_url(url):
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in TERABOX_DOMAINS
        )
    except Exception:
        return False


def extract_terabox_links(text):
    if not text:
        return []

    found = []
    seen = set()

    for match in URL_PATTERN.findall(text):
        url = clean_url(match)

        if is_terabox_url(url) and url not in seen:
            found.append(url)
            seen.add(url)

    return found


def extract_invite_hash(invite_url):
    """Extract the hash from t.me/+HASH or t.me/joinchat/HASH."""
    parsed = urlparse(invite_url)
    host = (parsed.hostname or "").lower()

    if host not in {"t.me", "www.t.me", "telegram.me"}:
        return None

    path = parsed.path.strip("/")

    if path.startswith("+"):
        return path[1:]

    if path.startswith("joinchat/"):
        return path.split("/", 1)[1]

    return None


# ============================================================
# RESOLVE PRIVATE SOURCE CHANNEL
# ============================================================

async def resolve_source():
    """
    Resolve a public channel/entity or a private invite URL.
    If not already a member, Telegram may ask to join via the invite.
    You must have legitimate access to the source channel.
    """
    invite_hash = extract_invite_hash(SOURCE_CHANNEL)

    if not invite_hash:
        return await client.get_entity(SOURCE_CHANNEL)

    invite_info = await client(CheckChatInviteRequest(invite_hash))

    if isinstance(invite_info, ChatInviteAlready):
        return invite_info.chat

    try:
        updates = await client(ImportChatInviteRequest(invite_hash))
        chats = getattr(updates, "chats", [])

        if not chats:
            raise RuntimeError(
                "Joined the invite, but Telegram returned no channel entity."
            )

        print("Joined the private source channel.")
        return chats[0]

    except UserAlreadyParticipantError:
        # The membership may have changed between checking and joining.
        dialogs = await client.get_dialogs()

        for dialog in dialogs:
            entity = dialog.entity
            if getattr(entity, "id", None) == getattr(
                invite_info, "chat", None
            ):
                return entity

        raise RuntimeError(
            "Already a member, but the channel could not be resolved. "
            "Open Telegram, verify you can see the channel, and try again."
        )


# ============================================================
# COLLECT SOURCE LINKS — OLDEST TO NEWEST
# ============================================================

async def collect_links():
    print("\nResolving source channel...")
    source = await resolve_source()

    print("Reading messages from oldest to newest...")
    added = 0
    scanned = 0

    # reverse=True makes Telethon yield messages oldest-first.
    async for message in client.iter_messages(source, reverse=True):
        scanned += 1
        text = message.message or ""
        links = extract_terabox_links(text)

        for url in links:
            if add_job(message.id, url):
                added += 1
                print(f"[NEW] {url}")

    export_links()

    print(f"\nMessages scanned: {scanned}")
    print(f"New links added: {added}")
    print(f"All source links exported to {LINKS_FILE}")


# ============================================================
# EXPORT FILES
# ============================================================

def export_links():
    jobs = get_jobs()

    with open(LINKS_FILE, "w", encoding="utf-8") as file:
        for job in jobs:
            file.write(job["source_url"] + "\n")


def export_output():
    jobs = get_jobs()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        for job in jobs:
            if job["status"] == "done" and job["generated_url"]:
                file.write(job["generated_url"] + "\n")

    print(f"Confirmed generated URLs exported to {OUTPUT_FILE}")


# ============================================================
# GENERATOR BOT
# ============================================================

async def get_bot_response(bot, source_url):
    """
    Send one URL and read the first response plus any immediate
    follow-up messages. Returns combined text for inspection.
    """
    messages = []

    async with client.conversation(
        bot,
        timeout=RESULT_TIMEOUT,
        exclusive=True,
    ) as conversation:
        await conversation.send_message(source_url)

        first = await conversation.get_response()
        messages.append(first)

        # Some bots send the link and the completion status separately.
        # Wait briefly for additional responses without resending the URL.
        while True:
            try:
                extra = await asyncio.wait_for(
                    conversation.get_response(),
                    timeout=4,
                )
                messages.append(extra)
            except asyncio.TimeoutError:
                break
            except Exception:
                break

    return "\n".join(
        (message.message or "")
        for message in messages
    )


async def process_one(job, bot):
    job_id = job["id"]
    source_url = job["source_url"]

    update_job(job_id, "processing", error=None)

    print(f"\n[{job_id}] Sending: {source_url}")

    try:
        response_text = await get_bot_response(bot, source_url)
        response_urls = extract_terabox_links(response_text)

        # Never treat the original input URL as a generated result.
        distinct_urls = [
            url for url in response_urls
            if url.rstrip("/") != source_url.rstrip("/")
        ]

        if distinct_urls:
            generated_url = distinct_urls[0]

            update_job(
                job_id,
                "done",
                generated_url=generated_url,
                error=None,
            )

            print(f"[DONE] Generated URL: {generated_url}")

        else:
            detail = (
                "No distinct TeraBox URL found. "
                "The bot may have echoed the input URL or returned "
                "a status-only response. Inspect the bot chat."
            )

            update_job(
                job_id,
                "needs_review",
                generated_url=None,
                error=detail + "\nBot response:\n" + response_text[:1500],
            )

            print("[REVIEW] No distinct output URL was found.")
            print("Bot response:")
            print(response_text[:1500])

    except FloodWaitError as exc:
        wait_seconds = int(exc.seconds) + 2
        detail = f"Telegram rate limit. Wait {wait_seconds} seconds."

        update_job(
            job_id,
            "needs_review",
            error=detail,
        )

        print(f"[WAIT] {detail}")

    except asyncio.TimeoutError:
        update_job(
            job_id,
            "needs_review",
            error=(
                "Timed out waiting for the generator bot. "
                "Check the bot chat before retrying."
            ),
        )
        print("[TIMEOUT] Check the bot chat before retrying.")

    except Exception as exc:
        update_job(
            job_id,
            "needs_review",
            error=f"{type(exc).__name__}: {exc}",
        )
        print(f"[ERROR] {type(exc).__name__}: {exc}")

    finally:
        export_output()


async def process_pending():
    pending = get_jobs("pending")

    if not pending:
        print("No pending links. Collect source links first.")
        return

    bot = await client.get_entity(GENERATOR_BOT)

    print(f"\nPending links: {len(pending)}")
    print("Processing in saved oldest-first order.")

    for index, job in enumerate(pending, start=1):
        print(f"\nProgress: {index}/{len(pending)}")
        await process_one(job, bot)

        # Small pause between requests to avoid rapid-fire messaging.
        await asyncio.sleep(2)

    export_output()
    print("\nPending queue finished.")


# ============================================================
# REVIEW / MANUAL RETRY
# ============================================================

def show_review_jobs():
    jobs = get_jobs("needs_review")

    if not jobs:
        print("No jobs need review.")
        return

    for job in jobs:
        print("\n" + "-" * 60)
        print(f"Job ID: {job['id']}")
        print(f"Input: {job['source_url']}")
        print(f"Reason: {job['last_error'] or 'Unknown'}")
        print("-" * 60)


async def retry_job():
    raw_id = input("Enter the job ID to retry: ").strip()

    if not raw_id.isdigit():
        print("Invalid job ID.")
        return

    job_id = int(raw_id)
    matches = [job for job in get_jobs("needs_review")
               if job["id"] == job_id]

    if not matches:
        print("That job is not in needs_review.")
        return

    job = matches[0]

    print("\nBefore retrying, check the Telegram bot chat.")
    print("If the bot already processed this link, do not resend it.")
    confirm = input("Have you checked and confirmed retry is safe? (yes/no): ")

    if confirm.strip().lower() != "yes":
        print("Retry cancelled.")
        return

    update_job(job_id, "pending", error=None)

    bot = await client.get_entity(GENERATOR_BOT)
    refreshed_job = next(
        item for item in get_jobs()
        if item["id"] == job_id
    )

    await process_one(refreshed_job, bot)


def show_status():
    jobs = get_jobs()

    counts = {}
    for job in jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1

    print("\nQueue status")
    print("-" * 30)
    print(f"Total:        {len(jobs)}")
    print(f"Pending:      {counts.get('pending', 0)}")
    print(f"Processing:   {counts.get('processing', 0)}")
    print(f"Completed:    {counts.get('done', 0)}")
    print(f"Needs review: {counts.get('needs_review', 0)}")


# ============================================================
# MAIN MENU
# ============================================================

async def main():
    if not API_ID or not API_HASH:
        print("Missing TG_API_ID or TG_API_HASH in your .env file.")
        print("Get your Telegram API credentials from https://my.telegram.org")
        return

    initialize_db()

    await client.start()

    me = await client.get_me()
    print(f"\nLogged in to Telegram as: {me.first_name}")
    print(f"Source: {SOURCE_CHANNEL}")
    print(f"Generator: {GENERATOR_BOT}")

    while True:
        print("\n" + "=" * 48)
        print(" TELEGRAM → TERABOX AUTOMATION")
        print("=" * 48)
        print("1. Collect source links (oldest to newest)")
        print("2. Process pending links with generator bot")
        print("3. Show jobs needing review")
        print("4. Retry one reviewed job")
        print("5. Export links.txt and output.txt")
        print("6. Show queue status")
        print("0. Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            try:
                await collect_links()
            except Exception as exc:
                print(f"Collection failed: {type(exc).__name__}: {exc}")

        elif choice == "2":
            await process_pending()

        elif choice == "3":
            show_review_jobs()

        elif choice == "4":
            await retry_job()

        elif choice == "5":
            export_links()
            export_output()

        elif choice == "6":
            show_status()

        elif choice == "0":
            print("Progress is saved in jobs.db. Goodbye!")
            break

        else:
            print("Invalid choice. Select one of the menu options.")

    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped. Saved database progress will be available next run.")
