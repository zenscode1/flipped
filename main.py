import os
import subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Dictionary to track running scripts per user
running_scripts = {}

# Folder to store user scripts and logs
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
    return file_path

def launch_script(user_id, file_path):
    user_dir = file_path.parent
    log_path = user_dir / "output.log"
    
    # Stop previous script if exists
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        proc.terminate()
    
    # Launch script in a separate process, log stdout/stderr
    proc = subprocess.Popen(
        ["python3", str(file_path)],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT
    )
    running_scripts[user_id] = proc
    return proc, log_path

# -------------------------
# Telegram Bot Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send me a .py file, and I can run it for you.\n"
        "Use /stop to stop your running script.\n"
        "Use /status to see if it's still running.\n"
        "Use /logs to see the output of your script."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Please send a valid .py file.")
        return

    file = update.message.document
    if not file.file_name.endswith(".py"):
        await update.message.reply_text("Only .py files are allowed!")
        return

    user_id = update.effective_user.id
    file_content = await file.get_file().download_as_bytearray()
    file_path = save_file(user_id, file_content, file.file_name)

    proc, log_path = launch_script(user_id, file_path)
    await update.message.reply_text(
        f"Running your script: {file.file_name}\nPID: {proc.pid}\n"
        f"Use /logs to see the output."
    )

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
    log_path = user_dir / "output.log"
    
    if log_path.exists():
        with open(log_path, "r") as f:
            content = f.read()
        # Telegram message limit is 4096 chars
        if len(content) > 4000:
            content = content[-4000:]  # last 4000 chars
        await update.message.reply_text(f"📄 Last logs:\n{content}")
    else:
        await update.message.reply_text("No logs found.")

# -------------------------
# Main Bot Setup
# -------------------------
def main():
    TOKEN = "7711686004:AAFoNhPTi_ggO_3of0VqUERMwCGqU1ZhZkc"  # <-- Replace with your bot token

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_script))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("logs", logs))
    app.add_handler(MessageHandler(filters.Document.FileExtension("py"), handle_file))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
