
import os, json, hmac, hashlib, sqlite3, asyncio, threading
from pathlib import Path
from urllib.parse import parse_qsl
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import uvicorn

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
DB_PATH = os.getenv("DATABASE_PATH", "data/gp_wallet.db")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
      balance REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS packages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      price REAL NOT NULL, profit REAL NOT NULL DEFAULT 0,
      total REAL NOT NULL DEFAULT 0, description TEXT DEFAULT '',
      active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS purchases(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      package_id INTEGER NOT NULL, price REAL NOT NULL,
      profit REAL NOT NULL, total REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS transactions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      kind TEXT NOT NULL, amount REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      reference TEXT DEFAULT '', note TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    defaults = {
      "app_name":"GP Wallet BD",
      "deposit_method":"bKash",
      "deposit_number":"01941854440",
      "minimum_deposit":"100",
      "minimum_withdraw":"100",
      "maintenance":"0",
      "support_text":"Support is available through the official support contact."
    }
    for k,v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    if c.execute("SELECT COUNT(*) n FROM packages").fetchone()["n"] == 0:
        c.execute("""INSERT INTO packages(name,price,profit,total,description)
                     VALUES(?,?,?,?,?)""",
                  ("VIP 1",500,200,700,"উদাহরণ প্যাকেজ"))
    c.commit(); c.close()

def get_settings():
    c=db(); rows=c.execute("SELECT key,value FROM settings").fetchall(); c.close()
    return {r["key"]:r["value"] for r in rows}

def save_settings(data):
    c=db()
    allowed={"app_name","deposit_method","deposit_number","minimum_deposit",
             "minimum_withdraw","maintenance","support_text"}
    for k,v in data.items():
        if k in allowed:
            c.execute("""INSERT INTO settings(key,value) VALUES(?,?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value""",(k,str(v)))
    c.commit(); c.close()

def upsert_user(u):
    c=db()
    c.execute("""INSERT INTO users(id,username,first_name) VALUES(?,?,?)
      ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name""",
      (u["id"],u.get("username",""),u.get("first_name","")))
    c.commit(); c.close()

def validate_tg(init_data):
    if not BOT_TOKEN: raise HTTPException(503,"BOT_TOKEN is not configured")
    vals=dict(parse_qsl(init_data or "",keep_blank_values=True))
    received=vals.pop("hash",None)
    if not received: raise HTTPException(401,"Telegram session missing")
    check="\n".join(f"{k}={vals[k]}" for k in sorted(vals))
    secret=hmac.new(b"WebAppData",BOT_TOKEN.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,received): raise HTTPException(401,"Invalid Telegram session")
    if not vals.get("user"): raise HTTPException(401,"Telegram user missing")
    return json.loads(vals["user"])

def require_admin(request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data",""))
    if u["id"] not in ADMIN_IDS: raise HTTPException(403,"Admin only")
    return u

init_db()
api=FastAPI(title="GP Wallet BD")
router=Router()

def keyboard():
    rows=[]
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="🚀 GP Wallet BD খুলুন",
                                          web_app=WebAppInfo(url=WEBAPP_URL))])
    rows += [
      [InlineKeyboardButton(text="💰 ডিপোজিট",callback_data="deposit"),
       InlineKeyboardButton(text="💸 উত্তোলন",callback_data="withdraw")],
      [InlineKeyboardButton(text="📦 প্যাকেজ",callback_data="packages"),
       InlineKeyboardButton(text="👤 আমার অ্যাকাউন্ট",callback_data="account")],
      [InlineKeyboardButton(text="🎁 রেফার",callback_data="referral"),
       InlineKeyboardButton(text="🆘 সাপোর্ট",callback_data="support")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(CommandStart())
async def start(message:Message):
    u={"id":message.from_user.id,"username":message.from_user.username or "",
       "first_name":message.from_user.first_name or ""}
    upsert_user(u); s=get_settings()
    await message.answer(
      f"👋 স্বাগতম, {s['app_name']}!\n\n"
      "আপনার ওয়ালেট, প্যাকেজ ও অ্যাকাউন্ট দেখতে নিচের বাটনে চাপুন।",
      reply_markup=keyboard())

@router.message(Command("admin"))
async def admin(message:Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Admin access নেই।"); return
    await message.answer(f"🛠️ Admin Panel\n{WEBAPP_URL}/admin")

async def bot_runner():
    if not BOT_TOKEN: return
    bot=Bot(BOT_TOKEN); dp=Dispatcher(); dp.include_router(router)
    await dp.start_polling(bot)

@api.get("/")
async def home(): return FileResponse("web/index.html")

@api.get("/admin")
async def admin_page(): return FileResponse("web/admin.html")

@api.get("/api/config")
async def config():
    s=get_settings()
    return {"app_name":s["app_name"],"deposit_method":s["deposit_method"],
            "deposit_number":s["deposit_number"],"minimum_deposit":s["minimum_deposit"],
            "minimum_withdraw":s["minimum_withdraw"],"maintenance":s["maintenance"]=="1"}

@api.get("/api/me")
async def me(request:Request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data","")); upsert_user(u)
    c=db(); row=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone(); c.close()
    return dict(row)

@api.get("/api/packages")
async def packages():
    c=db(); rows=c.execute("SELECT * FROM packages WHERE active=1 ORDER BY id").fetchall(); c.close()
    return [dict(r) for r in rows]

@api.post("/api/purchase")
async def purchase(request:Request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data",""))
    data=await request.json(); pid=int(data.get("package_id",0))
    c=db(); p=c.execute("SELECT * FROM packages WHERE id=? AND active=1",(pid,)).fetchone()
    if not p: c.close(); raise HTTPException(404,"Package not found")
    # Purchase remains pending until an administrator verifies the payment.
    c.execute("""INSERT INTO purchases(user_id,package_id,price,profit,total)
                 VALUES(?,?,?,?,?)""",(u["id"],p["id"],p["price"],p["profit"],p["total"]))
    purchase_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.commit(); c.close()
    return {"ok":True,"purchase_id":purchase_id,
            "message":"প্যাকেজ কেনার অনুরোধ জমা হয়েছে। পেমেন্ট যাচাইয়ের পর Admin approve করবেন।"}

@api.post("/api/transaction")
async def transaction(request:Request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data",""))
    d=await request.json(); kind=d.get("kind"); amount=float(d.get("amount",0))
    if kind not in {"deposit","withdraw"} or amount<=0: raise HTTPException(400,"Invalid request")
    c=db()
    c.execute("""INSERT INTO transactions(user_id,kind,amount,reference,note)
                 VALUES(?,?,?,?,?)""",(u["id"],kind,amount,str(d.get("reference",""))[:100],
                                        str(d.get("note",""))[:500]))
    c.commit(); c.close()
    return {"ok":True}

@api.get("/api/transactions")
async def transactions(request:Request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data",""))
    c=db(); rows=c.execute("""SELECT * FROM transactions WHERE user_id=?
                             ORDER BY id DESC LIMIT 50""",(u["id"],)).fetchall(); c.close()
    return [dict(r) for r in rows]

@api.get("/api/purchases")
async def purchases(request:Request):
    u=validate_tg(request.headers.get("X-Telegram-Init-Data",""))
    c=db(); rows=c.execute("""SELECT p.*, x.name FROM purchases p
                             JOIN packages x ON x.id=p.package_id
                             WHERE p.user_id=? ORDER BY p.id DESC LIMIT 50""",(u["id"],)).fetchall()
    c.close(); return [dict(r) for r in rows]

@api.get("/api/admin/summary")
async def summary(request:Request):
    require_admin(request); c=db()
    out={"users":c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"],
         "pending_transactions":c.execute("SELECT COUNT(*) n FROM transactions WHERE status='pending'").fetchone()["n"],
         "pending_purchases":c.execute("SELECT COUNT(*) n FROM purchases WHERE status='pending'").fetchone()["n"]}
    c.close(); return out

@api.get("/api/admin/settings")
async def admin_settings_get(request:Request):
    require_admin(request); return get_settings()

@api.post("/api/admin/settings")
async def admin_settings(request:Request):
    require_admin(request); save_settings(await request.json()); return {"ok":True}

@api.get("/api/admin/users")
async def admin_users(request:Request):
    require_admin(request); c=db(); rows=c.execute("SELECT * FROM users ORDER BY id DESC LIMIT 200").fetchall()
    c.close(); return [dict(r) for r in rows]

@api.post("/api/admin/user/{uid}/status")
async def user_status(request:Request,uid:int):
    require_admin(request); d=await request.json(); status=d.get("status")
    if status not in {"active","suspended"}: raise HTTPException(400,"Invalid status")
    c=db(); c.execute("UPDATE users SET status=? WHERE id=?",(status,uid)); c.commit(); c.close()
    return {"ok":True}

@api.get("/api/admin/packages")
async def admin_packages(request:Request):
    require_admin(request); c=db(); rows=c.execute("SELECT * FROM packages ORDER BY id").fetchall(); c.close()
    return [dict(r) for r in rows]

@api.post("/api/admin/package")
async def admin_package(request:Request):
    require_admin(request); d=await request.json()
    name=str(d.get("name","")).strip(); price=float(d.get("price",0)); profit=float(d.get("profit",0))
    if not name or price<0 or profit<0: raise HTTPException(400,"Invalid package")
    total=price+profit
    c=db(); c.execute("""INSERT INTO packages(name,price,profit,total,description,active)
                         VALUES(?,?,?,?,?,?)""",(name,price,profit,total,str(d.get("description","")),1))
    c.commit(); c.close(); return {"ok":True}

@api.post("/api/admin/package/{pid}")
async def update_package(request:Request,pid:int):
    require_admin(request); d=await request.json()
    price=float(d.get("price",0)); profit=float(d.get("profit",0))
    c=db(); c.execute("""UPDATE packages SET name=?,price=?,profit=?,total=?,description=?,active=?
                         WHERE id=?""",(str(d.get("name","")),price,profit,price+profit,
                                        str(d.get("description","")),1 if d.get("active",True) else 0,pid))
    c.commit(); c.close(); return {"ok":True}

@api.get("/api/admin/transactions")
async def admin_transactions(request:Request):
    require_admin(request); c=db()
    rows=c.execute("""SELECT t.*,u.username,u.first_name FROM transactions t
                      LEFT JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT 200""").fetchall()
    c.close(); return [dict(r) for r in rows]

@api.post("/api/admin/transaction/{tid}")
async def approve_transaction(request:Request,tid:int):
    require_admin(request); d=await request.json(); status=d.get("status")
    if status not in {"approved","rejected","pending"}: raise HTTPException(400,"Invalid status")
    c=db(); t=c.execute("SELECT * FROM transactions WHERE id=?",(tid,)).fetchone()
    if not t: c.close(); raise HTTPException(404,"Not found")
    if status=="approved" and t["status"]!="approved":
        if t["kind"]=="deposit":
            c.execute("UPDATE users SET balance=balance+? WHERE id=?",(t["amount"],t["user_id"]))
        elif t["kind"]=="withdraw":
            bal=c.execute("SELECT balance FROM users WHERE id=?",(t["user_id"],)).fetchone()["balance"]
            if bal<t["amount"]: c.close(); raise HTTPException(400,"Insufficient balance")
            c.execute("UPDATE users SET balance=balance-? WHERE id=?",(t["amount"],t["user_id"]))
    c.execute("UPDATE transactions SET status=? WHERE id=?",(status,tid)); c.commit(); c.close()
    return {"ok":True}

@api.get("/api/admin/purchases")
async def admin_purchases(request:Request):
    require_admin(request); c=db()
    rows=c.execute("""SELECT p.*,x.name,u.username,u.first_name FROM purchases p
                      JOIN packages x ON x.id=p.package_id
                      LEFT JOIN users u ON u.id=p.user_id
                      ORDER BY p.id DESC LIMIT 200""").fetchall()
    c.close(); return [dict(r) for r in rows]

@api.post("/api/admin/purchase/{pid}")
async def approve_purchase(request:Request,pid:int):
    require_admin(request); d=await request.json(); status=d.get("status")
    if status not in {"approved","rejected","pending"}: raise HTTPException(400,"Invalid status")
    c=db(); p=c.execute("SELECT * FROM purchases WHERE id=?",(pid,)).fetchone()
    if not p: c.close(); raise HTTPException(404,"Not found")
    # Approval adds the configured total as wallet credit.
    # Change this rule later if your actual business flow requires a different accounting model.
    if status=="approved" and p["status"]!="approved":
        c.execute("UPDATE users SET balance=balance+? WHERE id=?",(p["total"],p["user_id"]))
    c.execute("UPDATE purchases SET status=? WHERE id=?",(status,pid)); c.commit(); c.close()
    return {"ok":True}

if __name__=="__main__":
    if BOT_TOKEN:
        threading.Thread(target=lambda:asyncio.run(bot_runner()),daemon=True).start()
    uvicorn.run(api,host="0.0.0.0",port=PORT)
