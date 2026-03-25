import os
import subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Dictionary to track running scripts per user
running_scripts = {}

# Base folder for user scripts/logs
BASE_DIR = Path("user_data")
BASE_DIR.mkdir(exist_ok=True)

# -------------------------
# Helper Functions
# -------------------------
def save_file(user_id, file_content, filename):
    user_dir = BASE_DIR / str(user_id)
    user_dir.mkdir(exist_ok=True)
    file_path = user_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path.resolve()

def launch_script(user_id, file_path):
    user_dir = file_path.parent
    log_path = user_dir / "output.log"

    # Stop previous script if exists
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        proc.terminate()

    try:
        proc = subprocess.Popen(
            ["python", str(file_path)],
            stdout=open(log_path, "w"),
            stderr=subprocess.STDOUT
        )
        running_scripts[user_id] = proc
        return proc, log_path
    except Exception as e:
        with open(log_path, "w") as f:
            f.write(f"Failed to start script: {e}")
        return None, log_path

def install_requirements(user_id, file_path):
    user_dir = file_path.parent
    log_path = user_dir / "requirements.log"

    try:
        # Run pip install for requirements.txt
        proc = subprocess.Popen(
            ["pip", "install", "-r", str(file_path)],
            stdout=open(log_path, "w"),
            stderr=subprocess.STDOUT
        )
        proc.wait()
        return log_path
    except Exception as e:
        with open(log_path, "w") as f:
            f.write(f"Failed to install requirements: {e}")
        return log_path

# -------------------------
# Telegram Bot Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send me a .py file to run it, or requirements.txt to install dependencies.\n"
        "Use /stop to stop your running script, /status to check, /logs for script output."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Please send a valid .py file or requirements.txt.")
        return

    file = update.message.document
    user_id = update.effective_user.id
    file_content = await file.get_file().download_as_bytearray()

    # Handle Python scripts
    if file.file_name.endswith(".py"):
        file_path = save_file(user_id, file_content, file.file_name)
        proc, log_path = launch_script(user_id, file_path)
        await update.message.reply_text(
            f"Running your script: {file.file_name}\nPID: {proc.pid}\n"
            f"Use /logs to see output."
        )
        return

    # Handle requirements.txt
    elif file.file_name == "requirements.txt":
        file_path = save_file(user_id, file_content, "requirements.txt")
        log_path = install_requirements(user_id, file_path)
        await update.message.reply_text(
            f"Installed requirements from requirements.txt.\n"
            f"Check logs with /logs."
        )
        return

    else:
        await update.message.reply_text("Only .py files or requirements.txt are allowed!")

async def stop_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        proc.terminate()
        del running_scripts[user_id]
        await update.message.reply_text(f"Stopped your running script (PID: {proc.pid})")
    else:
        await update.message.reply_text("No running script found.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        await update.message.reply_text(f"Script running with PID: {proc.pid}")
    else:
        await update.message.reply_text("No script is currently running.")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_dir = BASE_DIR / str(user_id)

    # Prefer script output, fallback to requirements log
    log_path = user_dir / "output.log"
    if not log_path.exists():
        log_path = user_dir / "requirements.log"

    if log_path.exists():
        with open(log_path, "r") as f:
            content = f.read()
        # Telegram message limit
        if len(content) > 4000:
            content = content[-4000:]
        await update.message.reply_text(f"📄 Last logs:\n{content}")
    else:
        await update.message.reply_text("No logs found.")

# -------------------------
# Main Bot Setup
# -------------------------
def main():
    TOKEN = "YOUR_BOT_TOKEN_HERE"  # <-- Replace with your Telegram bot token

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_script))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
