import logging
import requests
import re
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIGURATION ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUI_PANEL_URL = os.getenv("SUI_PANEL_URL")
SUI_API_TOKEN = os.getenv("SUI_API_TOKEN")
if not all([TELEGRAM_BOT_TOKEN, SUI_PANEL_URL, SUI_API_TOKEN]):
    raise ValueError("One or more required environment variables are not set. Please check your .env file.")

# --- LOGGING SETUP ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- HELPER FUNCTION ---
def escape_markdown(text: str) -> str:
    """Escapes special characters for Telegram's MarkdownV2 format."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


# --- S-UI API FUNCTIONS ---
def get_sui_inbounds():
    """Fetches a list of all inbounds from the s-ui panel."""
    api_url = f"{SUI_PANEL_URL}/apiv2/inbounds"
    headers = {'Accept': 'application/json', 'Token': SUI_API_TOKEN}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.ok:
            data = response.json()
            if data.get("success"):
                return True, data.get("obj", {})
            else:
                return False, f"API Error: {data.get('msg', 'Unknown API error')}"
        else:
            return False, f"HTTP Error: Status Code {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"Connection Error: {e}"


def test_sui_connection():
    """Tests the connection to the s-ui panel."""
    api_url = f"{SUI_PANEL_URL}/apiv2/status"
    headers = {'Accept': 'application/json', 'Token': SUI_API_TOKEN}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.ok:
            data = response.json()
            if data.get("success"):
                return True, "✅ s-ui panel connection successful!"
            else:
                return False, f"❌ s-ui API returned failure: {data.get('msg')}"
        else:
            return False, f"❌ Failed to connect. HTTP Status Code: {response.status_code}"
    except requests.exceptions.RequestException as e:
        return False, f"❌ Connection error: {e}"


# --- TELEGRAM BOT COMMAND HANDLERS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message."""
    user = update.effective_user
    await update.message.reply_html(
        f"👋 Hello {user.mention_html()}!\n\nI am ready to manage your s-ui panel.\n"
        f"➡️ Use /list_inbounds to see your available inbounds and users.\n"
        f"➡️ Use /newuser to add a new client.\n"
        f"➡️ Use /test_sui to check the connection status."
    )


async def test_sui_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs the s-ui connection test."""
    await update.message.reply_text("Connecting to s-ui panel, please wait...")
    is_successful, message = test_sui_connection()
    await update.message.reply_text(escape_markdown(message))


async def list_inbounds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and lists all s-ui inbounds and their associated users."""
    await update.message.reply_text("Fetching inbounds from your panel...")

    is_successful, data = get_sui_inbounds()

    if not is_successful:
        await update.message.reply_text(f"❌ Error: {escape_markdown(data)}")
        return

    inbound_list = data.get('inbounds', [])

    if not inbound_list:
        await update.message.reply_text("No inbounds found on your panel.")
        return

    message_lines = ["*Available Inbounds & Users:*\n"]
    for inbound in inbound_list:
        inbound_id = escape_markdown(str(inbound.get('id', 'N/A')))
        port = escape_markdown(str(inbound.get('listen_port', 'N/A')))
        protocol = escape_markdown(inbound.get('type', 'N/A'))
        remark = escape_markdown(inbound.get('tag', 'No Name'))

        message_lines.append(f"• *Name:* `{remark}`  *ID:* `{inbound_id}`")
        message_lines.append(f"  *Protocol:* {protocol} \\| *Port:* {port}")

        user_list = inbound.get('users', [])
        user_count = len(user_list)

        # --- THIS IS THE FIX ---
        if user_count > 0:
            sample_users = ", ".join(user_list[:3])
            # Escape the parentheses around the count and the dots for the ellipsis
            message_lines.append(f"  *Users \\({user_count}\\):* `{escape_markdown(sample_users)}`\\.\\.\\.")
        else:
            message_lines.append(f"  *Users:* None")

        message_lines.append("")

    await update.message.reply_text("\n".join(message_lines), parse_mode='MarkdownV2')


# --- MAIN BOT FUNCTION ---
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test_sui", test_sui_command))
    application.add_handler(CommandHandler("list_inbounds", list_inbounds_command))

    logger.info("Bot is starting... Press Ctrl-C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()