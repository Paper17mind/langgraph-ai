import argparse
import sys
import threading
import time

def main():
    parser = argparse.ArgumentParser(description="AI Telebot & Desktop Assistant")
    parser.add_argument('--telegram', action='store_true', help="Run Telegram Bot mode")
    parser.add_argument('--cli', action='store_true', help="Run CLI interactive mode")
    parser.add_argument('--webhook', action='store_true', help="Run Webhook Server (FastAPI)")
    parser.add_argument('--all', action='store_true', help="Run both Telegram Bot and Webhook Server concurrently")
    
    args = parser.parse_args()
    
    # Mode --all: Telegram bot + Webhook receiver concurrently
    if args.all or (args.telegram and args.webhook):
        from interfaces.webhook_server import run_webhook_server
        from interfaces.telegram_bot import run_telegram_bot

        print("🚀 Starting both Telegram Bot and Webhook Server concurrently...")
        webhook_thread = threading.Thread(
            target=run_webhook_server,
            kwargs={"host": "0.0.0.0", "port": 8000},
            daemon=True,
            name="webhook-server"
        )
        webhook_thread.start()
        # Run telegram bot in main thread for clean signal handling
        run_telegram_bot()

    elif args.telegram:
        from interfaces.telegram_bot import run_telegram_bot
        run_telegram_bot()
    elif args.cli:
        from interfaces.cli_bot import run_cli_bot
        run_cli_bot()
    elif args.webhook:
        from interfaces.webhook_server import run_webhook_server
        run_webhook_server()
    else:
        print("Please specify a mode to run:")
        print("  python main.py --telegram")
        print("  python main.py --webhook")
        print("  python main.py --all        (Runs both Telegram & Webhook)")
        print("  python main.py --cli")
        sys.exit(1)

if __name__ == "__main__":
    main()
