# GP Wallet BD

Telegram Bot + Telegram Mini App + Admin Panel.

## Included
- Bot name: GP Wallet BD
- Mini App button inside Telegram
- Admin Panel
- Editable bKash deposit number
- Package management
- Example package: price ৳500, profit ৳200, total ৳700
- Deposit/withdraw request records
- User balance and transaction history
- SQLite database
- Telegram Mini App user validation

## Setup
1. Copy `.env.example` to `.env`
2. Put your BotFather token in `BOT_TOKEN`
3. Put your Telegram numeric ID in `ADMIN_IDS`
4. Put your HTTPS Mini App URL in `WEBAPP_URL`
5. Install:
   `pip install -r requirements.txt`
6. Run:
   `python app.py`

The bKash number starts as `01941854440` and can be changed from Admin Panel.

IMPORTANT:
This project records deposit/withdrawal requests and admin approvals. It does not connect to bKash automatically. Before handling real money, add a legally appropriate payment provider/reconciliation process and follow the provider's terms and applicable Bangladesh requirements. Package profit/return values are configurable and should only be used where the underlying service is lawful and accurately disclosed.
