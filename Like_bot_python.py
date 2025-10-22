import aiohttp
import logging
import json
import random
import string
import os
from datetime import datetime, date, timedelta
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from PIL import Image
from io import BytesIO
import html

# ---------------- CONFIG ---------------- #
OWNER_ID = 7649642940  # <-- Put your Telegram user ID here (owner). Not Admins
BOT_TOKEN = "8286060517:AAGD9XkOFnEcMHCUMZhPnN8Kb56mJIPQdzM"  # <-- Put your Telegram bot token here

LIKE_COST = 30.0 # <-- Update Your Price

# In The Redeem Code Generator Change Your Name # 

# <-------------------------------- Don't Change Any Of It Under This --------------------------------> #

LIKE_API_URL = "https://no-like-api2.vercel.app/like"
LIKE_SERVER = "bd"
LIKE_API_KEY = "Gamigo_bd"

DATA_DIR = "LIKEBOT_DATA"
os.makedirs(DATA_DIR, exist_ok=True)

WALLET_FILE = os.path.join(DATA_DIR, "like_wallets.json")
ADMINS_FILE = os.path.join(DATA_DIR, "like_admins.json")
ORDERS_FILE = os.path.join(DATA_DIR, "like_orders.json")
GROUPS_FILE = os.path.join(DATA_DIR, "like_groups.json")
RECHARGES_FILE = os.path.join(DATA_DIR, "like_recharges.json")
REDEEMS_FILE = os.path.join(DATA_DIR, "like_redeems.json")
EZCASH_FILE = os.path.join(DATA_DIR, "like_ezcash.json")
SCHEDULE_FILE = os.path.join(DATA_DIR, "like_schedules.json")
LOG_FILE = os.path.join(DATA_DIR, "like_logs.json")
UNAUTH_FILE = os.path.join(DATA_DIR, "like_unauth_attempts.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------- Helpers: JSON storage ---------------- #
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------- Wallet helpers ---------------- #
def get_wallet(chat_id):
    wallets = load_json(WALLET_FILE)
    return float(wallets.get(str(chat_id), 0.0))

def set_wallet(chat_id, amount):
    wallets = load_json(WALLET_FILE)
    wallets[str(chat_id)] = float(amount)
    save_json(WALLET_FILE, wallets)

def add_wallet(chat_id, amount):
    amt = get_wallet(chat_id) + float(amount)
    set_wallet(chat_id, amt)
    return amt

def remove_wallet(chat_id, amount):
    amt = get_wallet(chat_id) - float(amount)
    set_wallet(chat_id, amt)
    return amt


# ---------------- Logs & Schedules ---------------- #
def load_logs():
    data = load_json(LOG_FILE)
    return data if isinstance(data, dict) else {}

def save_logs(data):
    save_json(LOG_FILE, data)

def load_schedules():
    data = load_json(SCHEDULE_FILE)
    return data if isinstance(data, dict) else {}

def save_schedules(data):
    save_json(SCHEDULE_FILE, data)


# ---------------- Admins & Groups ---------------- #
def load_admins():
    admins = load_json(ADMINS_FILE)
    if not isinstance(admins, list):
        admins = []
    if OWNER_ID not in admins:
        admins.append(OWNER_ID)
        save_json(ADMINS_FILE, admins)
    return admins

def save_admins(admin_list):
    save_json(ADMINS_FILE, admin_list)

def get_groups():
    groups = load_json(GROUPS_FILE)
    return groups if isinstance(groups, dict) else {}

def is_authorized_group(chat_id):
    groups = get_groups()
    return str(chat_id) in groups

def now_utc():
    return datetime.utcnow().replace(tzinfo=pytz.UTC)

def next_utc_140():
    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    target = now.replace(hour=1, minute=40, second=0, microsecond=0)
    if now < target:
        return target
    return target + timedelta(days=1)

def format_dt_utc(dt):
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            try:
                dt = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S.%f")
            except Exception:
                return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def get_time_srilanka():
    tz = pytz.timezone("Asia/Colombo")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    return user_id in load_admins()

def is_restricted_admin(user_id: int) -> bool:
    return is_admin(user_id) and not is_owner(user_id)

def allow_restricted_admin_command(cmd: str) -> bool:
    allowed_admin_cmds = [
        "/addgroup", "/removegroup", "/add", "/remove",
        "/wallet", "/start", "/leaderboard", "/report", "/check"
    ]
    return cmd in allowed_admin_cmds or cmd.startswith("/id")


# ---------------- API call (normalized) ---------------- #
async def freefire_like_api(uid, api_key=LIKE_API_KEY, base_url=LIKE_API_URL, server=LIKE_SERVER):
    url = f"{base_url}?uid={uid}&server_name={server}&key={api_key}"
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    text = await resp.text()
                    return {"status": 0, "message": f"API returned non-JSON ({resp.status}): {text}", "http_status": resp.status}

                resp_obj = data.get("response") if isinstance(data.get("response"), dict) else {}
                likes_given = resp_obj.get("LikesGivenByAPI")
                if likes_given is not None:
                    try:
                        lg = int(likes_given)
                    except Exception:
                        lg = likes_given
                    if lg == 0:
                        return {
                            "status": 3,
                            "message": "Player has reached maximum likes for today",
                            "response": resp_obj
                        }
                return data
    except Exception as e:
        logger.exception("freefire_like_api exception: %s", e)
        return {"status": 0, "message": f"API exception: {str(e)}", "http_status": None}


# ---------------- Authorization decorator ---------------- #
def require_authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        msg = getattr(update, "message", None)
        text = (msg.text or "").strip() if msg else ""
        cmd = text.split()[0].lower() if text else ""

        if chat.type == "private":
            if is_owner(user.id):
                return await func(update, context)
            if is_restricted_admin(user.id):
                if allow_restricted_admin_command(cmd):
                    return await func(update, context)
                await update.message.reply_text("Only Owner Can Use This Command")
                return
            await update.message.reply_text("This bot only operates within authorized groups.")
            return

        if chat.type in ["group", "supergroup"]:
            gid = str(chat.id)
            if is_authorized_group(chat.id):
                return await func(update, context)
            if cmd.startswith("/access"):
                attempts = load_json(UNAUTH_FILE) or {}
                cnt = attempts.get(gid, 0) + 1
                attempts[gid] = cnt
                save_json(UNAUTH_FILE, attempts)
                try:
                    return await func(update, context)
                except Exception:
                    logger.exception("Error while running access handler for group %s", gid)
                finally:
                    if cnt >= 2:
                        try:
                            await context.bot.send_message(chat_id=int(gid), text="This group is not authorized. Leaving the group...")
                        except Exception:
                            logger.exception("Failed to send leaving message to group %s", gid)
                        try:
                            await context.bot.leave_chat(chat.id)
                        except Exception:
                            logger.exception("Failed to leave chat %s", gid)
                return
            try:
                await context.bot.send_message(chat_id=int(gid), text="This group is not authorized. Leaving the group...")
            except Exception:
                logger.exception("Failed to notify group %s before leaving", gid)
            try:
                await context.bot.leave_chat(chat.id)
            except Exception:
                logger.exception("Failed to leave chat %s", gid)
            return

        if msg:
            await update.message.reply_text("This bot only operates in authorized groups.")
        return
    return wrapper


# ---------------- Redeem code generator ---------------- #
def generate_code():
    parts = []
    for _ in range(4):
        parts.append(''.join(random.choices(string.ascii_uppercase + string.digits, k=4)))
    return "VINSO-" + "-".join(parts) # <-- Change With Your Store Name For Redeem Code )"Your_Name-" <--(


# ---------------- Start Command ---------------- #
@require_authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    balance = get_wallet(gid)
    menu_text = (
        "• `/wallet` 💳 (Check your wallet balance)\n"
        "• `/like player_uid` 👍 (Send Likes For UID)\n"
        "• `/like player_uid days` 🔄 (Send Likes For schedule)\n"
        "• `/redeem code` 🎁 (Redeem a code to add funds)\n"
        "• `/report` 📊 (View the last 3 day’s transactions)\n"
        "• `/leaderboard` 🏆 (View top players based on like value)\n"
        "• `/check player_id` 🔍 (Check like details for the player)\n\n"
        f"📦 Products (LKR):\n\n"
        f"• Like For 1 Day: {LIKE_COST:.2f} LKR\n"
    )
    await update.message.reply_text(f"✨ Welcome To Free Fire Like Bot! ✨\n\n"
                                    f"💰 Current Wallet Balance: {balance:.2f} LKR\n\n{menu_text}", parse_mode="Markdown")

# ---------------- Wallet ---------------- #
@require_authorized
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    await update.message.reply_text(f"💰 Current wallet balance: {get_wallet(gid):.2f} LKR")


# ---------------- Access Token ---------------- #
@require_authorized
async def access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        gid = str(chat.id)
        await update.message.reply_text(f"🔑 Access ID: `{gid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("This command works only in groups.")
        

# ---------------- Like Command ---------------- #
@require_authorized
async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /like <uid> [days]")
        return

    uid = args[0]
    days = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    # Multi-day scheduled flow
    if days and days > 0:
        total_cost = float(days * LIKE_COST)
        balance = get_wallet(chat_id)
        if balance < total_cost:
            await update.message.reply_text(f"❌ Insufficient balance. Need at least {total_cost:.2f} LKR.")
            return

        # Deduct up-front for entire schedule
        set_wallet(chat_id, balance - total_cost)

        # Create schedule entry
        schedules = load_schedules()
        sch_group = schedules.setdefault(chat_id, {})
        sch_group[uid] = {
            "days_total": days,
            "days_left": days,
            "active": True,
            "next_run": next_utc_140().isoformat(),
            "nickname": "",
            "level": "",
            "likes_given": 0,
            "last_error": ""
        }
        save_schedules(schedules)

        # Immediate first attempt
        like_data = await freefire_like_api(uid)
        now = now_utc()
        resp = like_data.get("response", {}) if isinstance(like_data.get("response"), dict) else {}
        player_nickname = resp.get("PlayerNickname", "N/A")
        key_expires = resp.get("KeyExpiresAt", "N/A")

        # Success cases
        if like_data.get("status") in (1, 2):
            sch_group[uid]["likes_given"] += 1
            sch_group[uid]["days_left"] = max(0, sch_group[uid]["days_left"] - 1)
            sch_group[uid]["nickname"] = player_nickname
            sch_group[uid]["last_error"] = ""
            sch_group[uid]["next_run"] = next_utc_140().isoformat()
            save_schedules(schedules)

            # Log
            logs = load_logs()
            today = now.strftime("%Y-%m-%d")
            logs.setdefault(today, {}).setdefault(chat_id, [])
            logs[today][chat_id].append({
                "time": format_dt_utc(now),
                "uid": uid,
                "nickname": player_nickname,
                "likes_given": 1
            })
            save_logs(logs)

            await update.message.reply_text(
                f"📅 {format_dt_utc(now)}\n"
                f"✅ Like sent (1/{days}).\n"
                f"• UID: {uid}\n"
                f"• Nickname: {player_nickname}\n"
                f"• Day progress: {sch_group[uid]['days_total'] - sch_group[uid]['days_left']}/{sch_group[uid]['days_total']}  |  Available days left: {sch_group[uid]['days_left']}\n"
                f"• Next run: {format_dt_utc(datetime.fromisoformat(sch_group[uid]['next_run']))}\n"
                f"💸 {total_cost:.2f} LKR was deducted up front.\n"
                f"💰 New Wallet Balance: {get_wallet(chat_id):.2f} LKR"
            )

            if sch_group[uid]["days_left"] <= 0:
                sch_group[uid]["active"] = False
                save_schedules(schedules)
                await update.message.reply_text(f"✅ Schedule completed for UID {uid}.")
            return

        # LikesGivenByAPI == 0 case normalized to status==3
        if like_data.get("status") == 3 and like_data.get("message") == "Player has reached maximum likes for today":
            # DO NOT refund, DO NOT decrement days_left
            day_progress = sch_group[uid].get("days_total", 0) - sch_group[uid].get("days_left", 0)
            next_run_iso = sch_group[uid]["next_run"]
            await update.message.reply_text(
                f"📅 {format_dt_utc(now)}\n"
                f"❌ Like send unsuccessful !\n"
                f"• UID: {uid}\n"
                f"• Nickname: {player_nickname}\n"
                f"• Key remaining: {key_expires}\n"
                f"• Day progress: {day_progress}  |  Available days left: {sch_group[uid]['days_left']}\n"
                f"• Next run: {format_dt_utc(datetime.fromisoformat(next_run_iso))}"
            )
            sch_group[uid]["last_error"] = like_data.get("message", "")
            sch_group[uid]["next_run"] = next_utc_140().isoformat()
            sch_group[uid]["nickname"] = player_nickname
            save_schedules(schedules)
            return

        # Other errors: schedule retry and store last_error
        sch_group[uid]["last_error"] = like_data.get("message", "")
        sch_group[uid]["next_run"] = next_utc_140().isoformat()
        save_schedules(schedules)
        await update.message.reply_text(f"❌ Error placing schedule for UID {uid}: {like_data.get('message', 'Unknown')}. Will retry at next 01:40 UTC.")
        return

    # Single immediate run (non-scheduled)
    total_cost = float(LIKE_COST)
    balance = get_wallet(chat_id)
    if balance < total_cost:
        await update.message.reply_text(f"❌ Insufficient balance. Need at least {total_cost:.2f} LKR.")
        return

    like_data = await freefire_like_api(uid)
    now = now_utc()
    resp = like_data.get("response", {}) if isinstance(like_data.get("response"), dict) else {}
    player_nickname = resp.get("PlayerNickname", "N/A")
    likes_before = resp.get("LikesbeforeCommand", "N/A")
    likes_after = resp.get("LikesafterCommand", "N/A")

    if like_data.get("status") in (1, 2):
        set_wallet(chat_id, balance - total_cost)
        logs = load_logs()
        today = now.strftime("%Y-%m-%d")
        logs.setdefault(today, {}).setdefault(chat_id, [])
        logs[today][chat_id].append({
            "time": format_dt_utc(now),
            "uid": uid,
            "nickname": player_nickname,
            "likes_given": 1
        })
        save_logs(logs)
        await update.message.reply_text(
            f"📅 {format_dt_utc(now)}\n"
            f"✅ Like sent.\n"
            f"• Player: {player_nickname}\n"
            f"• Likes: {likes_before} ➜ {likes_after}\n"
            f"💸 {total_cost:.2f} LKR deducted.\n"
            f"💰 New Wallet Balance: {get_wallet(chat_id):.2f} LKR"
        )
    elif like_data.get("status") == 3 and like_data.get("message"):
        # For single runs, keep refund behavior (optional). Here we do not deduct before call, so no refund needed
        await update.message.reply_text(f"❌ {like_data.get('message')}")
    else:
        await update.message.reply_text(f"❌ Like send failed for UID: {uid}. {like_data.get('message', 'No details.')}")


# ---------------- Scheduler ---------------- #
async def auto_like_scheduler(context: ContextTypes.DEFAULT_TYPE):
    schedules = load_schedules()
    logs = load_logs()
    wallets = load_json(WALLET_FILE)
    now = now_utc()
    changed = False

    for chat_id, group_sched in list(schedules.items()):
        for uid, sch in list(group_sched.items()):
            if not sch.get("active") or sch.get("days_left", 0) <= 0:
                continue

            # Parse next_run (ensure tz-aware)
            try:
                next_run = datetime.fromisoformat(sch["next_run"])
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=pytz.UTC)
            except Exception:
                next_run = next_utc_140()
                sch["next_run"] = next_run.isoformat()
                changed = True

            if now >= next_run:
                like_data = await freefire_like_api(uid)
                resp = like_data.get("response", {}) if isinstance(like_data.get("response"), dict) else {}
                player_nickname = resp.get("PlayerNickname", "N/A")
                key_expires = resp.get("KeyExpiresAt", "N/A")
                likes_before = resp.get("LikesbeforeCommand", "N/A")
                likes_after = resp.get("LikesafterCommand", "N/A")
                current_error = like_data.get("message", "")
                last_error = sch.get("last_error", "")

                # LikesGivenByAPI==0 normalized to status==3
                if like_data.get("status") == 3 and like_data.get("message") == "Player has reached maximum likes for today":
                    # Do NOT refund, do NOT decrement days_left; schedule next attempt
                    day_progress = sch.get("days_total", 0) - sch.get("days_left", 0)
                    sch["last_error"] = like_data.get("message", "")
                    sch["next_run"] = next_utc_140().isoformat()
                    changed = True
                    await context.bot.send_message(
                        int(chat_id),
                        f"📅 {format_dt_utc(now)}\n"
                        f"❌ Like send unsuccessful !\n"
                        f"• UID: {uid}\n"
                        f"• Nickname: {player_nickname}\n"
                        f"• Key remaining: {key_expires}\n"
                        f"• Day progress: {day_progress}  |  Available days left: {sch.get('days_left', 0)}\n"
                        f"• Next run: {format_dt_utc(datetime.fromisoformat(sch['next_run']))}"
                    )
                    continue

                # Other status==3 messages (invalid UID etc.)
                if like_data.get("status") == 3 and like_data.get("message"):
                    sch["active"] = False
                    sch["last_error"] = like_data.get("message", "")
                    changed = True
                    await context.bot.send_message(int(chat_id), f"❌ UID {uid}: {like_data.get('message')}\nSchedule stopped.")
                    continue

                # If same API error occurs twice => refund remaining days and stop (existing policy)
                if current_error and current_error == last_error:
                    refund_amount = sch.get("days_left", 0) * LIKE_COST
                    wallets[str(chat_id)] = float(wallets.get(str(chat_id), 0.0) + refund_amount)
                    save_json(WALLET_FILE, wallets)
                    sch["active"] = False
                    changed = True
                    await context.bot.send_message(
                        int(chat_id),
                        f"❌ Error sending like to UID {uid}: {current_error} occurred twice. Refunded {refund_amount:.2f} LKR for {sch.get('days_left',0)} remaining days. Schedule stopped."
                    )
                    continue

                if like_data.get("status") in (1, 2):
                    # success: count the day
                    sch["nickname"] = player_nickname
                    sch["days_left"] = max(0, sch.get("days_left", 0) - 1)
                    sch["likes_given"] = sch.get("likes_given", 0) + 1
                    sch["next_run"] = next_utc_140().isoformat()
                    sch["last_error"] = ""
                    changed = True

                    # Log
                    today = now.strftime("%Y-%m-%d")
                    logs.setdefault(today, {}).setdefault(chat_id, [])
                    logs[today][chat_id].append({
                        "time": format_dt_utc(now),
                        "uid": uid,
                        "nickname": player_nickname,
                        "likes_given": 1
                    })
                    save_logs(logs)

                    await context.bot.send_message(
                        int(chat_id),
                        f"📅 {format_dt_utc(now)}\n"
                        f"✅ Like sent.\n"
                        f"• UID: {uid}\n"
                        f"• Player: {player_nickname}\n"
                        f"• Likes: {likes_before} ➜ {likes_after}\n"
                        f"• Day progress: {sch.get('days_total',0)-sch.get('days_left',0)}/{sch.get('days_total',0)}  |  Available days left: {sch.get('days_left',0)}\n"
                        f"• Next run: {format_dt_utc(datetime.fromisoformat(sch['next_run']))}"
                    )
                    if sch.get("days_left", 0) <= 0:
                        sch["active"] = False
                        await context.bot.send_message(int(chat_id), f"✅ Schedule completed for Player: {player_nickname} ({uid}).")
                elif like_data.get("status") == 0:
                    # API error: schedule retry next_utc_140
                    sch["last_error"] = current_error
                    sch["next_run"] = next_utc_140().isoformat()
                    changed = True
                    await context.bot.send_message(
                        int(chat_id),
                        f"📅 {format_dt_utc(now)}\n"
                        f"❌ Like attempt failed for UID {uid}.\n"
                        f"• Error: {current_error}\n"
                        f"• This attempt was NOT counted and will be retried at next 01:40 UTC.\n"
                        f"• Days remaining to complete: {sch.get('days_left', 0)}"
                    )
                else:
                    # fallback: retry after 2 hours
                    sch["next_run"] = (now + timedelta(hours=2)).isoformat()
                    sch["last_error"] = like_data.get("message", "Unknown error")
                    changed = True
                    await context.bot.send_message(int(chat_id), f"❌ Error sending like to UID: {uid}: {like_data.get('message', 'Unknown')}. Will retry in 2h.")
    if changed:
        save_schedules(schedules)
        save_logs(logs)
        save_json(WALLET_FILE, wallets)


# ---------------- Add Funds ---------------- #
@require_authorized
async def add_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    gid = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❌ Usage: /add <amount>")
        return
    try:
        amount = float(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Amount must be a number.")
        return
    wallets = load_json(WALLET_FILE) or {}
    wallets[gid] = float(wallets.get(gid, 0.0) + amount)
    save_json(WALLET_FILE, wallets)
    recharges = load_json(RECHARGES_FILE) or {}
    try:
        rid = str(max([int(k) for k in recharges.keys()] + [0]) + 1)
    except Exception:
        rid = str(len(recharges) + 1)
    recharges[rid] = {"group": gid, "amount": amount, "date": date.today().strftime("%Y-%m-%d")}
    save_json(RECHARGES_FILE, recharges)
    await update.message.reply_text(f"✅ Added {amount:.2f} LKR. New Balance: {wallets[gid]:.2f} LKR")


# ---------------- Remove Funds ---------------- #
@require_authorized
async def remove_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    gid = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❌ Usage: /remove <amount>")
        return
    try:
        amount = float(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Amount must be a number.")
        return
    wallets = load_json(WALLET_FILE) or {}
    wallets[gid] = float(wallets.get(gid, 0.0) - amount)
    save_json(WALLET_FILE, wallets)
    await update.message.reply_text(f"✅ Deducted {amount:.2f} LKR. New Balance: {wallets[gid]:.2f} LKR")


# ---------------- Add Group ---------------- #
@require_authorized
async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /addgroup <group_id>")
        return
    gid = str(context.args[0]).strip()
    groups = load_json(GROUPS_FILE) or {}
    wallets = load_json(WALLET_FILE) or {}
    if gid in groups:
        await update.message.reply_text("⚠️ Group already authorized.")
        return
    groups[gid] = True
    save_json(GROUPS_FILE, groups)
    wallets[gid] = float(wallets.get(gid, 0.0))
    save_json(WALLET_FILE, wallets)
    attempts = load_json(UNAUTH_FILE) or {}
    if gid in attempts:
        attempts.pop(gid, None)
        save_json(UNAUTH_FILE, attempts)
    await update.message.reply_text(f"✅ Group {gid} authorized")


# ---------------- Remove Group ---------------- #
@require_authorized
async def remove_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /removegroup <group_id>")
        return
    gid = str(context.args[0]).strip()
    groups = load_json(GROUPS_FILE) or {}
    wallets = load_json(WALLET_FILE) or {}
    if gid not in groups:
        await update.message.reply_text("⚠️ Group not found.")
        return
    groups.pop(gid, None)
    wallets.pop(gid, None)
    save_json(GROUPS_FILE, groups)
    save_json(WALLET_FILE, wallets)
    await update.message.reply_text(f"❌ Group {gid} removed.")


# ---------------- Add Admin ---------------- #
@require_authorized
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can add admins.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /addadmin <telegram_id>")
        return
    try:
        new_admin_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid Telegram ID.")
        return
    admins = load_admins()
    if new_admin_id in admins:
        await update.message.reply_text("❌ User already admin.")
        return
    admins.append(new_admin_id)
    save_admins(admins)
    await update.message.reply_text(f"✅ User {new_admin_id} added as admin.")


# ---------------- Remove Admin ---------------- #
@require_authorized
async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can remove admins.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /removeadmin <admin_telegram_id>")
        return
    try:
        remove_admin_id = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid Telegram ID.")
        return
    if remove_admin_id == OWNER_ID:
        await update.message.reply_text("❌ Cannot remove owner.")
        return
    admins = load_admins()
    if remove_admin_id not in admins:
        await update.message.reply_text("❌ This user is not an admin.")
        return
    admins.remove(remove_admin_id)
    save_admins(admins)
    await update.message.reply_text(f"✅ User {remove_admin_id} removed from admin list.")


# ---------------- Genarate A Redeem Code ---------------- #
@require_authorized
async def gredeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can generate redeems.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /gredeem <amount>")
        return
    try:
        amount = float(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Invalid amount.")
        return
    code = generate_code()
    redeems = load_json(REDEEMS_FILE) or {}
    redeems[code] = {"amount": amount, "used": False, "created_by": update.effective_user.id, "date": date.today().strftime("%Y-%m-%d")}
    save_json(REDEEMS_FILE, redeems)
    try:
        await context.bot.send_message(chat_id=update.effective_user.id, text=f"✅ Redeem Code Generated!\n\nCode: `{code}`\nAmount: {amount:.2f} LKR", parse_mode="Markdown")
        if update.effective_chat.type != "private":
            await update.message.reply_text("✅ Redeem code generated and sent to owner privately.")
    except Exception:
        await update.message.reply_text(f"✅ Redeem Code: `{code}`\nAmount: {amount:.2f} LKR", parse_mode="Markdown")


# ---------------- Redeem A Code ---------------- #
@require_authorized
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❌ Usage: /redeem <code>")
        return
    code = context.args[0].upper().strip()
    redeems = load_json(REDEEMS_FILE) or {}
    if code not in redeems:
        await update.message.reply_text("❌ Invalid redeem code.")
        return
    if redeems[code].get("used"):
        await update.message.reply_text("❌ This code has already been redeemed.")
        return
    amount = float(redeems[code].get("amount", 0))
    wallets = load_json(WALLET_FILE) or {}
    wallets[gid] = float(wallets.get(gid, 0.0) + amount)
    save_json(WALLET_FILE, wallets)
    redeems[code]["used"] = True
    redeems[code]["redeemed_by"] = gid
    redeems[code]["redeemed_at"] = date.today().strftime("%Y-%m-%d")
    save_json(REDEEMS_FILE, redeems)
    recharges = load_json(RECHARGES_FILE) or {}
    try:
        rid = str(max([int(k) for k in recharges.keys()] + [0]) + 1)
    except Exception:
        rid = str(len(recharges) + 1)
    recharges[rid] = {"group": gid, "amount": amount, "date": date.today().strftime("%Y-%m-%d"), "code": code}
    save_json(RECHARGES_FILE, recharges)
    await update.message.reply_text(f"🎉 Redeem successful! Code: `{code}` Amount: +{amount:.2f} LKR New Balance: {wallets[gid]:.2f} LKR", parse_mode="Markdown")


# ---------------- Accept A Ez Cash Rechage ---------------- #
@require_authorized
async def acceptez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can accept ezcash.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /acceptez <RnNumber> <amount>")
        return
    rn = context.args[0]
    try:
        amount = float(context.args[1])
    except Exception:
        await update.message.reply_text("❌ Amount must be a number.")
        return
    redeems = load_json(EZCASH_FILE) or {}
    if rn not in redeems:
        await update.message.reply_text("❌ RN not found.")
        return
    if redeems[rn].get("status") != "Pending":
        await update.message.reply_text(f"❌ RN {rn} already {redeems[rn].get('status')}.")
        return
    gid = redeems[rn].get("group")
    wallets = load_json(WALLET_FILE) or {}
    wallets[gid] = float(wallets.get(gid, 0.0) + amount)
    save_json(WALLET_FILE, wallets)
    time_now = get_time_srilanka()
    redeems[rn]["status"] = "Accepted"
    redeems[rn]["amount"] = amount
    redeems[rn]["time"] = time_now
    save_json(EZCASH_FILE, redeems)
    await update.message.reply_text(f"✅ Accepted RN {rn} for group {gid} | Added {amount:.2f} LKR | New Balance: {wallets[gid]:.2f} LKR")
    try:
        await context.bot.send_message(int(gid), f"✅ Your Ez Cash redeem was accepted!\nRN: {rn}\nAmount: {amount:.2f} LKR\nNew Balance: {wallets[gid]:.2f} LKR")
    except Exception:
        logger.exception("Failed to notify group %s about accepted RN %s", gid, rn)


# ---------------- Reject A Ez Cash Recharge ---------------- #
@require_authorized
async def rejectez(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can reject ezcash.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /rejectez <RnNumber>")
        return
    rn = context.args[0]
    redeems = load_json(EZCASH_FILE) or {}
    if rn not in redeems:
        await update.message.reply_text("❌ RN not found.")
        return
    if redeems[rn].get("status") != "Pending":
        await update.message.reply_text(f"❌ RN {rn} already {redeems[rn].get('status')}.")
        return
    gid = redeems[rn].get("group")
    time_now = get_time_srilanka()
    redeems[rn]["status"] = "Rejected"
    redeems[rn]["time"] = time_now
    save_json(EZCASH_FILE, redeems)
    await update.message.reply_text(f"❌ Rejected RN {rn} for group {gid}. Time: {time_now}")
    try:
        if gid:
            await context.bot.send_message(int(gid), f"❌ Your Ez Cash redeem was rejected.\nRN: {rn}\nTime: {time_now}")
    except Exception:
        logger.exception("Failed to notify group %s about rejected RN %s", gid, rn)


# ---------------- Price Updated Notice To All ---------------- 
@require_authorized
async def price_notice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can send price notices.")
        return
    notice = " ".join(context.args).strip() if context.args else (f"📢 Price Update 📢\n\n"
                                                                  f"Use /start to viwes the latest price list instantly")
    for admin in load_admins():
        try:
            await context.bot.send_message(chat_id=admin, text=notice)
        except Exception:
            logger.exception("Failed to send notice to admin %s", admin)
    groups = load_json(GROUPS_FILE) or {}
    for gid in list(groups.keys()):
        try:
            await context.bot.send_message(chat_id=int(gid), text=notice)
        except Exception:
            logger.exception("Failed to send notice to group %s", gid)
    await update.message.reply_text("✅ Price updated notice sent.")


# ---------------- Send A Message To All ---------------- #
@require_authorized
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Only owner can broadcast.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /message <text>")
        return
    text = " ".join(context.args).strip()
    groups = load_json(GROUPS_FILE) or {}
    for gid in list(groups.keys()):
        try:
            await context.bot.send_message(chat_id=int(gid), text=text)
        except Exception:
            logger.exception("Failed to send broadcast to group %s", gid)
    for admin in load_admins():
        try:
            await context.bot.send_message(chat_id=admin, text=text)
        except Exception:
            logger.exception("Failed to send broadcast to admin %s", admin)
    await update.message.reply_text("✅ Broadcast sent.")


# ---------------- Leaderboard (With Like Count)---------------- #
@require_authorized
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    logs = load_logs()
    players = {}
    for day, groups in logs.items():
        group = groups.get(gid, [])
        for entry in group:
            uid = entry["uid"]
            players.setdefault(uid, {"name": entry.get("nickname", "N/A"), "likes": 0})
            players[uid]["likes"] += entry.get("likes_given", 1)
    top = sorted(players.items(), key=lambda x: x[1]["likes"], reverse=True)[:10]
    if not top:
        await update.message.reply_text("📭 No likes sent in this group yet.")
        return
    msg = "🏆 Top players:\n"
    for i, (uid, info) in enumerate(top, 1):
        msg += f"{i}. {info['name']} | UID: {uid} | Likes: {info['likes']}\n"
    await update.message.reply_text(msg)


# ---------------- Roport (Last 3 Days ) ---------------- #
@require_authorized
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    today = date.today()
    last_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    wallets = load_json(WALLET_FILE) or {}
    recharges = load_json(RECHARGES_FILE) or {}
    orders = load_json(ORDERS_FILE) or {}
    msg_lines = []
    for d in reversed(last_days):
        topups_count = topups_total = 0
        recharges_count = recharges_total = 0
        for oid, o in orders.items():
            if o.get("group") == gid and o.get("status") == "Accepted" and o.get("date") == d:
                topups_count += 1
                topups_total += float(o.get("cost", 0))
        for rid, r in recharges.items():
            if r.get("group") == gid and r.get("date") == d:
                recharges_count += 1
                recharges_total += float(r.get("amount", 0))
        end_balance = wallets.get(gid, 0.0)
        msg_lines.append(
            f"📊 Report for {d}:\n"
            f"Likes: {topups_count} (Spent: {topups_total:.2f} LKR)\n"
            f"Recharges: {recharges_count} (Total: {recharges_total:.2f} LKR)\n"
            f"End Balance: {end_balance:.2f} LKR\n"
        )
    await update.message.reply_text("\n".join(msg_lines))


# ---------------- Check Player Likes With UID ---------------- #
@require_authorized
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /check <uid>")
        return
    uid = context.args[0]
    logs = load_logs()
    schedules = load_schedules()
    completed = 0
    last_like = "N/A"
    name = "N/A"
    level = "N/A"
    for day, groups in logs.items():
        group = groups.get(gid, [])
        for entry in group:
            if entry["uid"] == uid:
                completed += entry.get("likes_given", 1)
                name = entry.get("nickname", name)
                level = entry.get("level", level)
                last_like = entry.get("time", last_like)
    sch = schedules.get(gid, {}).get(uid)
    ongoing = sch["days_left"] if sch and sch.get("active") else 0
    await update.message.reply_text(f"📋 Player Info\n• Name: {name}\n• UID: {uid}\n• Level: {level}\n• Completed likes: {completed}\n• Ongoing days left: {ongoing}\n• Last like: {last_like}")


# ---------------- Id Info Check ---------------- #
@require_authorized
async def idinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait_message = await update.message.reply_text("🔄 Processing your request, please wait...")
    try:
        if len(context.args) != 1:
            await wait_message.edit_text("❌ Invalid format.\n\nUse:\n<code>/idinfo &lt;uid&gt;</code>", parse_mode="HTML")
            return
        player_id = context.args[0]
        default_region = "sg"
        url = f"https://info-api-six.vercel.app/player-info?region={default_region}&uid={player_id}"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await wait_message.edit_text("❌ Failed to retrieve data from the UID.", parse_mode="HTML")
                    return
                player = await resp.json()
        if not player or not isinstance(player, dict) or not player.get("basicInfo"):
            await wait_message.edit_text(f"❌ No player found with ID <code>{player_id}</code>.", parse_mode="HTML")
            return
        account_info = player.get("basicInfo", {})
        region = account_info.get("region", default_region)
        def format_time(timestamp):
            try:
                return datetime.fromtimestamp(int(timestamp), tz=pytz.UTC).strftime('%m/%d/%Y, %I:%M:%S %p') if timestamp else "N/A"
            except Exception:
                return "N/A"
        account_created = format_time(account_info.get("createAt"))
        last_login = format_time(account_info.get("lastLoginAt"))
        player_name = html.escape(account_info.get("nickname", "Unknown"))
        reply = (
            f"┌<b>👤 Player Info</b>\n"
            f"├─ <b>Player Name:</b> {player_name}\n"
            f"├─ <b>ID:</b> {player_id}\n"
            f"├─ <b>Level:</b> {account_info.get('level', 'N/A')} (Exp: {account_info.get('exp', 'N/A')})\n"
            f"├─ <b>Likes:</b> {account_info.get('liked', 'N/A')}\n"
            f"├─ <b>Created At:</b> {account_created}\n"
            f"└─ <b>Last Login:</b> {last_login}\n\n"
        )
        reply_to_id = update.message.reply_to_message.message_id if update.message.reply_to_message else update.message.message_id
        await wait_message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply, parse_mode="HTML", reply_to_message_id=reply_to_id)

        async def fetch_and_resize_image(url: str, caption: str, size: tuple[int, int]):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200 and resp.content_type.startswith("image"):
                            img_bytes = await resp.read()
                            image = Image.open(BytesIO(img_bytes))
                            image = image.resize(size)
                            output = BytesIO()
                            image.save(output, format="PNG")
                            output.seek(0)
                            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=output, caption=caption, reply_to_message_id=reply_to_id)
                        else:
                            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{caption} unavailable", reply_to_message_id=reply_to_id)
            except Exception as e:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{caption} error: <code>{html.escape(str(e))}</code>", reply_to_message_id=reply_to_id, parse_mode="HTML")

        avatar_url = f"https://gmg-avatar-banner.vercel.app/Gmg-avatar-banner?uid={player_id}&region={region}&key=IDK"
        await fetch_and_resize_image(avatar_url, "🖼 Player Avatar", (326, 98))
        clothing_url = f"https://ffoutfitapis.vercel.app/outfit-image?uid={player_id}&region={region}&key=99day"
        await fetch_and_resize_image(clothing_url, "👕 Player Clothing", (300, 300))

    except Exception as e:
        try:
            await wait_message.edit_text(f"❌ An error occurred: <code>{html.escape(str(e))}</code>", parse_mode="HTML")
        except Exception:
            pass

# ---------------- MAIN ---------------- #
import asyncio

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register all handlers (same as before)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("access", access))
    app.add_handler(CommandHandler("like", like_command))
    app.add_handler(CommandHandler("idinfo", idinfo))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("add", add_funds))
    app.add_handler(CommandHandler("remove", remove_funds))
    app.add_handler(CommandHandler("addgroup", add_group))
    app.add_handler(CommandHandler("removegroup", remove_group))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("gredeem", gredeem))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("acceptez", acceptez))
    app.add_handler(CommandHandler("rejectez", rejectez))
    app.add_handler(CommandHandler("price", price_notice))
    app.add_handler(CommandHandler("message", broadcast_message))

    # Safe Job Queue setup
    jq = getattr(app, "job_queue", None)
    if jq:
        jq.run_repeating(auto_like_scheduler, interval=60, first=10)
    else:
        print("⚠️ JobQueue not available — scheduler disabled.")

    print("✅ Starting bot polling...")
    await app.run_polling(close_loop=False)
    print("🤖 Bot stopped cleanly.")

def main():
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot stopped manually.")

if __name__ == "__main__":
    main()
