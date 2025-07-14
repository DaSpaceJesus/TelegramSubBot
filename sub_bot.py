import logging
import requests
import re
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# --- CONFIGURATION & SETUP (Unchanged) ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUI_PANEL_URL = os.getenv("SUI_PANEL_URL")
SUI_API_TOKEN = os.getenv("SUI_API_TOKEN")
if not all([TELEGRAM_BOT_TOKEN, SUI_PANEL_URL, SUI_API_TOKEN]):
    raise ValueError("One or more required environment variables are not set. Please check your .env file.")
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# --- HELPER & API FUNCTIONS (Unchanged) ---
def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


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


# --- TELEGRAM COMMAND HANDLERS (Unchanged, except for the button handler below) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        f"👋 Hello {user.mention_html()}!\n\n"
        f"I am ready to manage your s-ui panel.\n"
        f"➡️ Use /list_inbounds to browse users.\n"
        f"➡️ Use /newuser to add a new client."
    )


async def list_inbounds_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.callback_query.message
    await message.reply_text("Fetching inbounds from your panel...")
    is_successful, data = get_sui_inbounds()
    if not is_successful:
        await message.reply_text(f"❌ Error: {escape_markdown(data)}")
        return
    inbound_list = data.get('inbounds', [])
    if not inbound_list:
        await message.reply_text("No inbounds found on your panel.")
        return
    keyboard = []
    message_text = "*Available Inbounds:*\n"
    for inbound in inbound_list:
        remark = escape_markdown(inbound.get('tag', 'No Name'))
        inbound_id = inbound.get('id', 0)
        user_count = len(inbound.get('users', []))
        message_text += f"\n• *Name:* `{remark}` \\| *ID:* `{inbound_id}` \\| *Users:* {user_count}"
        keyboard.append([
            InlineKeyboardButton(f"View Users in '{inbound.get('tag', 'No Name')}' ({user_count})",
                                 callback_data=f"view_users:{inbound_id}")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Edit the message if it's from a button click, otherwise send a new one
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')


# --- UPDATED BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all button clicks."""
    query = update.callback_query
    await query.answer()

    # Data can be "action:id" or "action:id:username"
    parts = query.data.split(':', 2)
    action = parts[0]

    # --- Action: view_users ---
    if action == "view_users":
        inbound_id = int(parts[1])
        is_successful, data = get_sui_inbounds()
        if not is_successful:
            await query.edit_message_text(text=f"Error fetching data: {escape_markdown(data)}")
            return

        target_inbound = next((inb for inb in data.get('inbounds', []) if inb.get('id') == inbound_id), None)

        if not target_inbound:
            await query.edit_message_text(text="Couldn't find that inbound. Try /list_inbounds again.")
            return

        remark = escape_markdown(target_inbound.get('tag', 'No Name'))
        user_list = target_inbound.get('users', [])

        if not user_list:
            await query.edit_message_text(text=f"No users found in inbound *{remark}*\.", parse_mode='MarkdownV2')
            return

        # --- CREATE USER BUTTONS ---
        user_keyboard = []
        # Arrange users into 2 columns for a cleaner look
        row = []
        for user in user_list:
            button = InlineKeyboardButton(user, callback_data=f"user_details:{inbound_id}:{user}")
            row.append(button)
            if len(row) == 2:
                user_keyboard.append(row)
                row = []
        if row:  # Add the last row if it's not full
            user_keyboard.append(row)

        user_keyboard.append([InlineKeyboardButton("« Back to Inbounds", callback_data="back_to_inbounds")])
        reply_markup = InlineKeyboardMarkup(user_keyboard)
        await query.edit_message_text(text=f"Please select a user from *{remark}*:", reply_markup=reply_markup,
                                      parse_mode='MarkdownV2')

    # --- Action: user_details (New) ---
    elif action == "user_details":
        inbound_id = int(parts[1])
        username = parts[2]

        # For now, just confirm the selection
        message = f"You selected user `{escape_markdown(username)}` from inbound *{inbound_id}*\."

        keyboard = [
            # In the future, we can add buttons like "Get Stats" or "Delete"
            [InlineKeyboardButton(f"« Back to User List", callback_data=f"view_users:{inbound_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='MarkdownV2')

    # --- Action: back_to_inbounds ---
    elif action == "back_to_inbounds":
        # Call the original command function to show the inbound list again
        await list_inbounds_command(query, context)


# --- MAIN BOT FUNCTION ---
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("list_inbounds", list_inbounds_command))

    # Add the handler for all button clicks
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is starting... Press Ctrl-C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()