import logging
import requests
import re
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

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
# (These functions are correct and unchanged)
def get_sui_inbounds():
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
    """Fetches and lists all s-ui inbounds with interactive buttons."""
    await update.message.reply_text("Fetching inbounds from your panel...")

    is_successful, data = get_sui_inbounds()
    if not is_successful:
        await update.message.reply_text(f"❌ Error: {escape_markdown(data)}")
        return

    inbound_list = data.get('inbounds', [])
    if not inbound_list:
        await update.message.reply_text("No inbounds found on your panel.")
        return

    keyboard = []
    message_text = "*Available Inbounds:*\n"
    for inbound in inbound_list:
        remark = escape_markdown(inbound.get('tag', 'No Name'))
        inbound_id = inbound.get('id', 0)
        user_count = len(inbound.get('users', []))

        # Add text description for this inbound
        message_text += f"\n• *Name:* `{remark}` \| *ID:* `{inbound_id}` \| *Users:* {user_count}"

        # Add a button for this inbound
        keyboard.append([
            InlineKeyboardButton(f"View Users in '{inbound.get('tag', 'No Name')}' ({user_count})",
                                 callback_data=f"view_users:{inbound_id}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')


# --- NEW: HANDLER FOR BUTTON CLICKS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    # Data is in the format "action:id", e.g., "view_users:2"
    action, inbound_id_str = query.data.split(':')
    inbound_id = int(inbound_id_str)

    if action == "view_users":
        # In the future, we will fetch users and show them. For now, just confirm.
        is_successful, data = get_sui_inbounds()
        if not is_successful:
            await query.edit_message_text(text=f"Error fetching data again: {escape_markdown(data)}")
            return

        target_inbound = None
        for inbound in data.get('inbounds', []):
            if inbound.get('id') == inbound_id:
                target_inbound = inbound
                break

        if target_inbound:
            remark = escape_markdown(target_inbound.get('tag', 'No Name'))
            user_list = target_inbound.get('users', [])

            if not user_list:
                await query.edit_message_text(text=f"No users found in inbound *{remark}*\.", parse_mode='MarkdownV2')
                return

            # For now, we just list them as text. In the next step, we can make these buttons too.
            user_text_list = "\n".join([f"`{escape_markdown(user)}`" for user in user_list])
            message = f"*Users in {remark}:*\n\n{user_text_list}"

            # Add a "Back" button
            keyboard = [[InlineKeyboardButton("« Back to Inbounds", callback_data="back_to_inbounds")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='MarkdownV2')

        else:
            await query.edit_message_text(text="Couldn't find that inbound anymore. Try /list_inbounds again.")

    elif action == "back_to_inbounds":
        # This is a bit inefficient as it re-runs the command logic, but it's simple and works.
        # We can pass the original message object to a new function to make it cleaner later.
        await list_inbounds_command(query, context)


# --- MAIN BOT FUNCTION ---
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test_sui", test_sui_command))
    application.add_handler(CommandHandler("list_inbounds", list_inbounds_command))
    # Add the new handler for button clicks
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is starting... Press Ctrl-C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()