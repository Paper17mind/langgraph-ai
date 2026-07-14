import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="Lightweight AI Assistant (Telegram & CLI)")
    parser.add_argument('--telegram', action='store_true', help="Run in Telegram Bot mode")
    parser.add_argument('--cli', action='store_true', help="Run in CLI interactive mode")
    
    args = parser.parse_args()
    
    if args.telegram:
        from interfaces.telegram_bot import run_telegram_bot
        run_telegram_bot()
    elif args.cli:
        from interfaces.cli_bot import run_cli_bot
        run_cli_bot()
    else:
        print("Please specify a mode to run: --telegram or --cli")
        print("Example: python main.py --cli")
        sys.exit(1)

if __name__ == "__main__":
    main()
