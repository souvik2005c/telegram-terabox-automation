# Telegram TeraBox Automation

A Python-based automation tool that collects TeraBox links from a Telegram channel, submits them to a Telegram bot for processing, and exports confirmed results to a text file.

## Features

- **Telegram Integration:** Access Telegram channels using Telethon.
- **QR-Code Authentication:** Optional QR-based login using an existing Telegram session.
- **Automated Link Collection:** Extract supported TeraBox URLs from channel messages.
- **Oldest-First Processing:** Collect messages in chronological order.
- **Bot Integration:** Submit links individually to a configured Telegram bot.
- **Persistent Progress:** Store job status in SQLite to resume after interruptions.
- **Result Export:** Save source links to `links.txt` and confirmed generated links to `output.txt`.
- **Manual Review:** Flag uncertain responses to avoid treating the original URL as a generated result.
- **Credential Protection:** Load configuration from environment variables.

## Tech Stack

- Python 3.11+
- Telethon
- SQLite
- python-dotenv
- qrcode / Pillow

## Project Structure

```text
telegram-terabox-automation/
├── tele.py
├── qr.py
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── jobs.db                 # Generated locally
├── links.txt               # Generated locally
├── output.txt              # Generated locally
└── telegram_session.session # Generated locally; never commit
```

The database, output files, virtual environment, and Telegram session are local runtime files and should not be committed to GitHub.

## Prerequisites

- Python 3.11 or newer
- Git
- A Telegram account with legitimate access to the source channel
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)
- Access to the Telegram bot you want to use for processing

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/souvik2005c/telegram-terabox-automation.git
cd telegram-terabox-automation
```

### 2. Create a virtual environment

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file by copying `.env.example`:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and add your own values:

```dotenv
TG_API_ID=YOUR_API_ID
TG_API_HASH=YOUR_API_HASH

SOURCE_CHANNEL=YOUR_TELEGRAM_CHANNEL_OR_INVITE
GENERATOR_BOT=@TeraBot

RESULT_TIMEOUT=180
RESULT_DOMAINS=terabox.com,1024terabox.com,1024tera.com,teraboxapp.com,terabox.app,4funbox.com
```

Get your API ID and API hash from [my.telegram.org](https://my.telegram.org).

**Never commit your real `.env` file, API hash, login code, or Telegram session file.**

## Usage

Run the script that matches the filenames in your repository.

### QR Login (optional)

If your `qr.py` script implements QR-based authentication:

```powershell
python qr.py
```

Follow the terminal instructions and scan the QR code using Telegram's **Settings → Devices → Link Desktop Device** option.

Only use this flow with your own Telegram account. Keep the QR code and generated session file private.

### Run the automation

```powershell
python tele.py
```

If prompted, follow the authentication instructions. Use the menu displayed by your script to collect links, process pending jobs, review uncertain responses, and export results.

## Output Files

| File | Purpose |
|---|---|
| `jobs.db` | Stores job status and processing progress |
| `links.txt` | Collected source TeraBox links |
| `output.txt` | Confirmed, distinct result URLs |
| `telegram_session.session` | Local Telegram authentication session |

The precise output behavior depends on the implementation of the Python scripts in your local repository.

## Important Notes

- The source account must have permission to access the channel.
- Telegram may impose rate limits or require additional verification.
- Bot responses can vary. A response that simply echoes the input URL does not establish that a new result was generated.
- Jobs with uncertain outcomes should be reviewed before retrying to avoid duplicate requests.
- Use the automation in accordance with Telegram's rules, the source channel's permissions, and the generator bot's terms.
- Never publish API credentials, session files, private invite links, or personal data.

## Troubleshooting

**Git or Python command not found**

Install Git or Python and reopen PowerShell so the updated PATH is loaded.

**Missing API credentials**

Check that `.env` is in the project root and contains valid `TG_API_ID` and `TG_API_HASH` values.

**Telegram login code not received**

Check existing Telegram sessions and follow the login options displayed by Telegram. QR authentication may be available if supported by your script.

**No distinct generated URL**

Inspect the actual bot response. Update the result parser to match the bot's response format rather than assuming that every response contains a new link.

**Module not found**

Activate your virtual environment and run:

```powershell
pip install -r requirements.txt
```

## Security

This project uses user-account authentication through Telethon. A Telegram session file can grant access to your account, so treat it like a password.

The `.gitignore` file should exclude `.env`, `.venv/`, `*.session`, `*.session-journal`, and generated files containing private links.

## License

Choose a license before allowing others to reuse, modify, or distribute this project. No license is granted merely by publishing the repository.

---

**Author:** [souvik2005c](https://github.com/souvik2005c)

**Repository:** [telegram-terabox-automation](https://github.com/souvik2005c/telegram-terabox-automation)
