import os
import subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify
import threading
import secrets
import json

# Dictionary to track running scripts per user
running_scripts = {}

# Base folder for user scripts/logs
BASE_DIR = Path("user_data")
BASE_DIR.mkdir(exist_ok=True)

# Key system
KEYS_FILE = BASE_DIR / "keys.json"
ADMIN_USER_ID = 7225123280  # <-- Replace with YOUR Telegram user ID

# Initialize keys storage
def load_keys():
    if KEYS_FILE.exists():
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_keys(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)

active_keys = load_keys()

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

def check_access(user_id):
    """Check if user has valid key or is admin"""
    if user_id == ADMIN_USER_ID:
        return True
    return str(user_id) in active_keys

# -------------------------
# Telegram Bot Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text(
            "⚠️ Access denied! You need a valid key to use this bot.\n"
            "Contact the admin to get access."
        )
        return
    
    await update.message.reply_text(
        "✅ Welcome! You have access to the bot.\n\n"
        "Send me a .py file to run it, or requirements.txt to install dependencies.\n"
        "Commands:\n"
        "/stop - Stop your running script\n"
        "/status - Check script status\n"
        "/logs - View script output"
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text("⚠️ Access denied! You need a valid key.")
        return
    
    if not update.message.document:
        await update.message.reply_text("Please send a valid .py file or requirements.txt.")
        return

    file = update.message.document
    
    # Fix: await get_file() first, then download
    telegram_file = await file.get_file()
    file_content = await telegram_file.download_as_bytearray()

    # Handle Python scripts
    if file.file_name.endswith(".py"):
        file_path = save_file(user_id, file_content, file.file_name)
        proc, log_path = launch_script(user_id, file_path)
        await update.message.reply_text(
            f"✅ Running your script: {file.file_name}\nPID: {proc.pid}\n"
            f"Use /logs to see output."
        )
        return

    # Handle requirements.txt
    elif file.file_name == "requirements.txt":
        file_path = save_file(user_id, file_content, "requirements.txt")
        log_path = install_requirements(user_id, file_path)
        await update.message.reply_text(
            f"✅ Installed requirements from requirements.txt.\n"
            f"Check logs with /logs."
        )
        return

    else:
        await update.message.reply_text("Only .py files or requirements.txt are allowed!")

async def stop_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text("⚠️ Access denied!")
        return
    
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        proc.terminate()
        del running_scripts[user_id]
        await update.message.reply_text(f"✅ Stopped your running script (PID: {proc.pid})")
    else:
        await update.message.reply_text("No running script found.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text("⚠️ Access denied!")
        return
    
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        await update.message.reply_text(f"✅ Script running with PID: {proc.pid}")
    else:
        await update.message.reply_text("No script is currently running.")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text("⚠️ Access denied!")
        return
    
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
# Admin Key Management
# -------------------------
async def generate_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ Only admin can generate keys!")
        return
    
    # Check if user_id was provided
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /key <user_id>\n"
            "Example: /key 987654321"
        )
        return
    
    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")
        return
    
    # Generate unique key
    key = secrets.token_urlsafe(16)
    active_keys[str(target_user_id)] = key
    save_keys(active_keys)
    
    await update.message.reply_text(
        f"✅ Key generated for user {target_user_id}\n"
        f"Key: `{key}`\n"
        f"User can now access the bot!"
    )

async def revoke_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ Only admin can revoke keys!")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /revoke <user_id>\n"
            "Example: /revoke 987654321"
        )
        return
    
    try:
        target_user_id = str(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID!")
        return
    
    if target_user_id in active_keys:
        del active_keys[target_user_id]
        save_keys(active_keys)
        await update.message.reply_text(f"✅ Key revoked for user {target_user_id}")
    else:
        await update.message.reply_text(f"❌ No key found for user {target_user_id}")

async def list_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ Only admin can list keys!")
        return
    
    if not active_keys:
        await update.message.reply_text("No active keys.")
        return
    
    message = "🔑 Active Keys:\n\n"
    for uid, key in active_keys.items():
        message += f"User ID: {uid}\nKey: `{key}`\n\n"
    
    await update.message.reply_text(message)

# -------------------------
# Flask Web Server (for deploying from your site)
# -------------------------
app = Flask(__name__)

# Secret token for API authentication
API_SECRET = secrets.token_urlsafe(32)  # Generate on first run
API_SECRET_FILE = BASE_DIR / "api_secret.txt"

# Save or load API secret
if API_SECRET_FILE.exists():
    with open(API_SECRET_FILE, "r") as f:
        API_SECRET = f.read().strip()
else:
    with open(API_SECRET_FILE, "w") as f:
        f.write(API_SECRET)

@app.route('/deploy', methods=['POST'])
def deploy():
    """
    Endpoint to deploy scripts from your website
    
    Expected JSON:
    {
        "secret": "your_api_secret",
        "user_id": 123456789,
        "script": "print('Hello from web!')",
        "filename": "script.py"
    }
    """
    data = request.json
    
    # Verify secret
    if data.get('secret') != API_SECRET:
        return jsonify({"error": "Invalid secret"}), 403
    
    user_id = data.get('user_id')
    script_content = data.get('script')
    filename = data.get('filename', 'web_script.py')
    
    if not user_id or not script_content:
        return jsonify({"error": "Missing user_id or script"}), 400
    
    # Check if user has access
    if not check_access(user_id):
        return jsonify({"error": "User does not have access"}), 403
    
    try:
        # Save and run the script
        file_path = save_file(user_id, script_content.encode('utf-8'), filename)
        proc, log_path = launch_script(user_id, file_path)
        
        return jsonify({
            "success": True,
            "message": f"Script deployed and running",
            "pid": proc.pid if proc else None,
            "filename": filename
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/status/<int:user_id>', methods=['GET'])
def web_status(user_id):
    """Check status of user's running script"""
    secret = request.headers.get('Authorization')
    
    if secret != f"Bearer {API_SECRET}":
        return jsonify({"error": "Invalid authorization"}), 403
    
    if user_id in running_scripts:
        proc = running_scripts[user_id]
        return jsonify({
            "running": True,
            "pid": proc.pid
        })
    else:
        return jsonify({"running": False})

@app.route('/logs/<int:user_id>', methods=['GET'])
def web_logs(user_id):
    """Get logs from user's script"""
    secret = request.headers.get('Authorization')
    
    if secret != f"Bearer {API_SECRET}":
        return jsonify({"error": "Invalid authorization"}), 403
    
    user_dir = BASE_DIR / str(user_id)
    log_path = user_dir / "output.log"
    
    if log_path.exists():
        with open(log_path, "r") as f:
            content = f.read()
        return jsonify({"logs": content})
    else:
        return jsonify({"error": "No logs found"}), 404

def run_flask():
    """Run Flask server in a separate thread"""
    app.run(host='0.0.0.0', port=5000, debug=False)

# -------------------------
# Main Bot Setup
# -------------------------
def main():
    TOKEN = "7711686004:AAFoNhPTi_ggO_3of0VqUERMwCGqU1ZhZkc"  # <-- Replace with your Telegram bot token

    # Print API secret on startup
    print("=" * 50)
    print("🤖 Bot is starting...")
    print(f"🔑 Your API Secret: {API_SECRET}")
    print(f"🌐 Web API running on http://0.0.0.0:5000")
    print(f"👤 Admin User ID: {ADMIN_USER_ID}")
    print("=" * 50)

    # Start Flask server in background
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Build Telegram bot
    telegram_app = ApplicationBuilder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("stop", stop_script))
    telegram_app.add_handler(CommandHandler("status", status))
    telegram_app.add_handler(CommandHandler("logs", logs))
    telegram_app.add_handler(CommandHandler("key", generate_key))
    telegram_app.add_handler(CommandHandler("revoke", revoke_key))
    telegram_app.add_handler(CommandHandler("listkeys", list_keys))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    print("✅ Bot is running...")
    telegram_app.run_polling()

if __name__ == "__main__":
    main()
