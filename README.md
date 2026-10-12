# HushJet stock monitor

Checks Dyson HushJet (HJ10) pages at Harvey Norman, Best Denki, Gain City, Dyson SG and FairPrice every 5 minutes via GitHub Actions and sends a Telegram message when one becomes in stock or open for pre-order.

## Setup
1. Repo → Settings → Secrets and variables → Actions → New repository secret:
   - `TELEGRAM_BOT_TOKEN` — from @BotFather
   - `TELEGRAM_CHAT_ID` — send your bot a message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`
2. Actions tab → "HushJet stock check" → Run workflow. The first run sends a summary of every page so you know the bot works.

After that you're messaged only when a page changes to in stock / pre-order.

To add or remove pages, edit `PRODUCTS` in `check_stock.py`. To stop, disable the workflow in the Actions tab.
