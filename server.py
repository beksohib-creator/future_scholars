"""Future Scholars Mentorship — Telegram bot + Mini App server.

Faqat Python standart kutubxonasi ishlatiladi (qo'shimcha o'rnatish shart emas).
Ishga tushirish:  python server.py
"""
import hashlib
import hmac
import json
import mimetypes
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
WEBAPP_DIR = BASE / "webapp"
DB_PATH = BASE / "data.db"


# ---------------------------------------------------------------- config
def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(BASE / ".env")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID") or 0)
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
PORT = int(os.environ.get("PORT") or 8080)
DEV_MODE = os.environ.get("DEV_MODE", "0") == "1"
DB_PATH = Path(os.environ.get("DB_PATH") or DB_PATH)


# ---------------------------------------------------------------- schema
# Google Sheet varaqlari asosida. "admin": True — faqat mentor (admin) to'ldiradi.
S = "text"
SCHEMA = {
    "universities": {
        "title": "Universitetlar",
        "icon": "🎓",
        "hint": "6–10 ta universitet. Rasmiy saytdan ma'lumot oling va har qatorga havola qo'ying. Tekshirilgan sanani yozing.",
        "limit": 10,
        "fields": [
            {"key": "name", "label": "Universitet", "type": S, "required": True},
            {"key": "country", "label": "Davlat", "type": S},
            {"key": "major", "label": "Dastur (major)", "type": S},
            {"key": "deadline", "label": "Ariza muddati", "type": S},
            {"key": "english", "label": "Ingliz tili testi (qaysi, minimal ball)", "type": S},
            {"key": "exemption", "label": "Inglizcha maktab uchun istisno bormi?", "type": "select",
             "options": ["Ha", "Yo'q", "Aniq emas"]},
            {"key": "sat", "label": "SAT/ACT", "type": "select",
             "options": ["Talab qilinadi", "Ixtiyoriy", "Talab qilinmaydi", "Aniq emas"]},
            {"key": "admissions_url", "label": "Qabul talablari sahifasi (havola)", "type": "url"},
            {"key": "aid", "label": "Xalqaro talabaga moliyaviy yordam (qisqacha)", "type": "textarea"},
            {"key": "aid_url", "label": "Moliyaviy yordam sahifasi (havola)", "type": "url"},
            {"key": "extra", "label": "Qo'shimcha talablar (insho, tavsiyanoma va h.k.)", "type": "textarea"},
            {"key": "level", "label": "Daraja", "type": "select", "options": ["Reach", "Match", "Safety"]},
            {"key": "checked", "label": "Ma'lumot tekshirilgan sana", "type": "date"},
        ],
    },
    "activities": {
        "title": "Faoliyatlar",
        "icon": "🏅",
        "hint": "Qilgan hamma narsangiz: sana, nima qildingiz, necha soat. Soatlar avtomatik hisoblanadi.",
        "limit": 50,
        "fields": [
            {"key": "date", "label": "Sana", "type": "date", "required": True},
            {"key": "name", "label": "Faoliyat", "type": S, "required": True},
            {"key": "kind", "label": "Turi", "type": "select",
             "options": ["Akademik", "Sport", "Volunteering", "Loyiha", "Musobaqa", "Kurs", "Boshqa"]},
            {"key": "hours", "label": "Soat", "type": "number"},
            {"key": "result", "label": "Nima qildim / natija", "type": "textarea"},
            {"key": "proof", "label": "Isbot (havola)", "type": "textarea"},
        ],
    },
    "weekly": {
        "title": "Haftalik reja",
        "icon": "🗓",
        "hint": "Mentor vazifalarni beradi. Holatni va natijani siz yangilaysiz. Ball va izohni mentor yozadi.",
        "limit": 100,
        "admin_create": True,
        "fields": [
            {"key": "week", "label": "Hafta", "type": "number", "admin": True},
            {"key": "range", "label": "Sana oralig'i", "type": S, "admin": True},
            {"key": "task", "label": "Vazifa", "type": "textarea", "admin": True, "required": True},
            {"key": "due", "label": "Muddat", "type": S, "admin": True},
            {"key": "deliverable", "label": "Nima yuboriladi (natija)", "type": "textarea"},
            {"key": "status", "label": "Holat", "type": "select",
             "options": ["Boshlanmagan", "Jarayonda", "Bajarildi"]},
            {"key": "proof", "label": "Isbot (havola)", "type": "textarea"},
            {"key": "mentor_note", "label": "Mentor izohi", "type": "textarea", "admin": True},
            {"key": "score", "label": "Ball (1–5)", "type": "select", "options": ["1", "2", "3", "4", "5"],
             "admin": True},
        ],
    },
    "tests": {
        "title": "Testlar",
        "icon": "📝",
        "hint": "IELTS, SAT va boshqa testlar bo'yicha natijalar va maqsadlar.",
        "limit": 30,
        "fields": [
            {"key": "test", "label": "Test", "type": S, "required": True},
            {"key": "date", "label": "Topshirgan sana", "type": "date"},
            {"key": "score", "label": "Natija (ball)", "type": S},
            {"key": "target", "label": "Maqsadli ball", "type": S},
            {"key": "next", "label": "Keyingi urinish sanasi", "type": "date"},
            {"key": "note", "label": "Izoh", "type": "textarea"},
        ],
    },
}


# ---------------------------------------------------------------- database
_db_lock = threading.Lock()


def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


DB = db()
with _db_lock:
    DB.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            tg_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            section TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rec ON records(user_id, section);
        """
    )
    DB.commit()


def q(sql, args=(), one=False, commit=False):
    with _db_lock:
        cur = DB.execute(sql, args)
        if commit:
            DB.commit()
            return cur
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def is_member(uid):
    return uid == ADMIN_ID or q("SELECT 1 FROM users WHERE tg_id=?", (uid,), one=True) is not None


def list_users():
    return [dict(r) for r in q("SELECT tg_id, name, created_at FROM users ORDER BY created_at")]


def add_user(tg_id, name):
    q("INSERT INTO users(tg_id,name,created_at) VALUES(?,?,?) "
      "ON CONFLICT(tg_id) DO UPDATE SET name=excluded.name",
      (tg_id, name, int(time.time())), commit=True)


def remove_user(tg_id):
    q("DELETE FROM users WHERE tg_id=?", (tg_id,), commit=True)
    q("DELETE FROM records WHERE user_id=?", (tg_id,), commit=True)


def get_records(uid, section):
    rows = q("SELECT id, data, created_at, updated_at FROM records WHERE user_id=? AND section=? ORDER BY id",
             (uid, section))
    return [{"id": r["id"], **json.loads(r["data"]), "_updated": r["updated_at"]} for r in rows]


def stats_for(uid):
    uni = get_records(uid, "universities")
    act = get_records(uid, "activities")
    wk = get_records(uid, "weekly")
    tests = get_records(uid, "tests")
    by_kind = {o: 0.0 for o in SCHEMA["activities"]["fields"][2]["options"]}
    total = 0.0
    for a in act:
        try:
            h = float(a.get("hours") or 0)
        except ValueError:
            h = 0
        total += h
        if a.get("kind") in by_kind:
            by_kind[a["kind"]] += h
    done = sum(1 for w in wk if w.get("status") == "Bajarildi")
    scores = [int(w["score"]) for w in wk if str(w.get("score", "")).isdigit()]
    return {
        "universities": len(uni),
        "activities": len(act),
        "hours_total": round(total, 2),
        "hours_by_kind": {k: round(v, 2) for k, v in by_kind.items()},
        "tasks_total": len(wk),
        "tasks_done": done,
        "tasks_percent": round(done * 100 / len(wk)) if wk else 0,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "tests": len(tests),
    }


def clean_data(section, payload, is_admin, existing=None):
    """Faqat sxemadagi maydonlarni qabul qiladi va ruxsatlarni tekshiradi."""
    out = dict(existing or {})
    for f in SCHEMA[section]["fields"]:
        k = f["key"]
        if k not in payload:
            continue
        if f.get("admin") and not is_admin:
            continue
        v = payload[k]
        v = "" if v is None else str(v).strip()[:3000]
        if f["type"] == "select" and v and v not in f["options"]:
            raise ValueError(f"'{f['label']}' uchun noto'g'ri qiymat")
        if f["type"] == "number" and v:
            try:
                float(v.replace(",", "."))
                v = v.replace(",", ".")
            except ValueError:
                raise ValueError(f"'{f['label']}' son bo'lishi kerak")
        out[k] = v
    for f in SCHEMA[section]["fields"]:
        if f.get("required") and not out.get(f["key"]):
            raise ValueError(f"'{f['label']}' to'ldirilishi shart")
    return out


# ---------------------------------------------------------------- telegram auth
def verify_init_data(init_data):
    """Telegram WebApp initData imzosini tekshiradi. To'g'ri bo'lsa user dict qaytaradi."""
    if not init_data or not BOT_TOKEN:
        return None
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)
    recv_hash = data.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return None
    if time.time() - int(data.get("auth_date", 0)) > 7 * 86400:
        return None
    try:
        return json.loads(data.get("user", "{}"))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- telegram bot
def tg(method, **params):
    if not BOT_TOKEN:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"[tg] {method} xato: {e}")
        return None


def open_button(text="📲 Ilovani ochish"):
    if not WEBAPP_URL:
        return None
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": WEBAPP_URL}}]]}


def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if markup:
        params["reply_markup"] = markup
    return tg("sendMessage", **params)


ADMIN_HELP = (
    "<b>Admin buyruqlari</b>\n"
    "/add <code>ID Ism</code> — foydalanuvchi qo'shish\n"
    "/remove <code>ID</code> — o'chirish\n"
    "/users — ro'yxat\n"
    "/app — ilovani ochish\n\n"
    "Foydalanuvchini ilova ichidagi «👥 O'quvchilar» bo'limidan ham qo'shishingiz mumkin."
)


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    uid = msg.get("from", {}).get("id")
    text = (msg.get("text") or "").strip()
    cmd, _, rest = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    is_admin = uid == ADMIN_ID

    if is_admin and cmd == "/add":
        parts = rest.split(maxsplit=1)
        if not parts or not parts[0].lstrip("-").isdigit():
            return send(chat_id, "Format: /add <code>123456789 Ism Familiya</code>")
        new_id, name = int(parts[0]), (parts[1] if len(parts) > 1 else parts[0])
        add_user(new_id, name)
        send(chat_id, f"✅ Qo'shildi: <b>{name}</b> (<code>{new_id}</code>)")
        send(new_id, "Siz Future Scholars Mentorship ilovasiga qo'shildingiz! 🎉", open_button())
        return
    if is_admin and cmd == "/remove":
        if not rest.strip().lstrip("-").isdigit():
            return send(chat_id, "Format: /remove <code>123456789</code>")
        remove_user(int(rest.strip()))
        return send(chat_id, "🗑 O'chirildi.")
    if is_admin and cmd == "/users":
        us = list_users()
        if not us:
            return send(chat_id, "Hali foydalanuvchi yo'q.")
        return send(chat_id, "\n".join(f"• {u['name']} — <code>{u['tg_id']}</code>" for u in us))
    if is_admin and cmd == "/help":
        return send(chat_id, ADMIN_HELP)

    if is_member(uid):
        hello = "Salom, mentor! 👋\n\n" + ADMIN_HELP if is_admin else \
            "Salom! 👋 Ish jadvalingizni ilovada to'ldirib boring. Har hafta yangilang."
        if not WEBAPP_URL:
            hello += "\n\n⚠️ WEBAPP_URL .env faylida ko'rsatilmagan."
        return send(chat_id, hello, open_button())

    first = msg.get("from", {}).get("first_name", "")
    send(chat_id, f"Siz hali ro'yxatda yo'qsiz.\nSizning ID: <code>{uid}</code>\nMentoringizga yuboring.")
    if ADMIN_ID:
        send(ADMIN_ID, f"🔔 Yangi so'rov: <b>{first}</b> (<code>{uid}</code>)\n"
                       f"Qo'shish uchun: <code>/add {uid} {first}</code>")


def bot_loop():
    if not BOT_TOKEN:
        print("[bot] BOT_TOKEN yo'q — bot ishga tushmadi (faqat web server).")
        return
    me = tg("getMe")
    print(f"[bot] ishga tushdi: @{(me or {}).get('result', {}).get('username')}")
    if WEBAPP_URL:
        tg("setChatMenuButton", menu_button={"type": "web_app", "text": "Ilova", "web_app": {"url": WEBAPP_URL}})
    tg("setMyCommands", commands=[{"command": "start", "description": "Ilovani ochish"}])
    offset = 0
    while True:
        res = tg("getUpdates", offset=offset, timeout=50, allowed_updates=["message"])
        if not res or not res.get("ok"):
            time.sleep(3)
            continue
        for upd in res["result"]:
            offset = upd["update_id"] + 1
            if "message" in upd:
                try:
                    handle_message(upd["message"])
                except Exception as e:  # noqa: BLE001
                    print(f"[bot] xato: {e}")


# ---------------------------------------------------------------- http api
class Handler(BaseHTTPRequestHandler):
    server_version = "Mentorship/1.0"

    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} {fmt % args}")

    # --- helpers
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def err(self, status, msg):
        self.send_json({"error": msg}, status)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200_000:
            raise ValueError("Juda katta so'rov")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def auth(self):
        """(uid, is_admin, user_dict) yoki None."""
        user = verify_init_data(self.headers.get("X-Init-Data", ""))
        if not user and DEV_MODE:
            dev = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("dev_user", [""])[0] \
                or self.headers.get("X-Dev-User", "")
            if dev.lstrip("-").isdigit():
                user = {"id": int(dev), "first_name": "Dev"}
        if not user:
            return None
        uid = int(user["id"])
        return uid, uid == ADMIN_ID, user

    def target_uid(self, uid, is_admin, params):
        """Admin istalgan foydalanuvchini ko'ra oladi, oddiy foydalanuvchi faqat o'zini."""
        if is_admin and params.get("user_id", [""])[0].lstrip("-").isdigit():
            return int(params["user_id"][0])
        return uid

    # --- static
    def serve_static(self, path):
        rel = path.lstrip("/") or "index.html"
        f = (WEBAPP_DIR / rel).resolve()
        if WEBAPP_DIR.resolve() not in f.parents or not f.is_file():
            f = WEBAPP_DIR / "index.html"
        data = f.read_bytes()
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # --- routing
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        u = urllib.parse.urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self.serve_static(u.path) if method == "GET" else self.err(405, "Method not allowed")
        try:
            self.api(method, u.path[5:].strip("/").split("/"), urllib.parse.parse_qs(u.query))
        except ValueError as e:
            self.err(400, str(e))
        except Exception as e:  # noqa: BLE001
            print(f"[http] xato: {e!r}")
            self.err(500, "Server xatosi")

    def api(self, method, parts, params):
        a = self.auth()
        if not a:
            return self.err(401, "Telegram orqali oching")
        uid, is_admin, tguser = a
        if not is_member(uid):
            return self.err(403, f"Siz ro'yxatda yo'qsiz. ID: {uid}")

        # GET /api/me
        if parts == ["me"] and method == "GET":
            row = q("SELECT name FROM users WHERE tg_id=?", (uid,), one=True)
            return self.send_json({
                "id": uid, "is_admin": is_admin,
                "name": row["name"] if row else (tguser.get("first_name") or "Mentor"),
                "schema": SCHEMA,
                "users": list_users() if is_admin else [],
            })

        # Admin: foydalanuvchilar
        if parts[0] == "users":
            if not is_admin:
                return self.err(403, "Faqat admin")
            if method == "GET":
                return self.send_json([{**u, "stats": stats_for(u["tg_id"])} for u in list_users()])
            if method == "POST":
                b = self.body()
                tid = str(b.get("tg_id", "")).strip()
                name = str(b.get("name", "")).strip()[:100]
                if not tid.lstrip("-").isdigit():
                    raise ValueError("Telegram ID raqam bo'lishi kerak")
                if not name:
                    raise ValueError("Ism kiriting")
                add_user(int(tid), name)
                threading.Thread(target=send, args=(int(tid),
                                 "Siz Future Scholars Mentorship ilovasiga qo'shildingiz! 🎉", open_button()),
                                 daemon=True).start()
                return self.send_json({"ok": True})
            if method == "DELETE" and len(parts) == 2 and parts[1].lstrip("-").isdigit():
                remove_user(int(parts[1]))
                return self.send_json({"ok": True})

        # GET /api/stats
        if parts == ["stats"] and method == "GET":
            return self.send_json(stats_for(self.target_uid(uid, is_admin, params)))

        # /api/records/<section>[/<id>]
        if parts[0] == "records" and len(parts) >= 2 and parts[1] in SCHEMA:
            section = parts[1]
            sch = SCHEMA[section]
            target = self.target_uid(uid, is_admin, params)
            if target != uid and not q("SELECT 1 FROM users WHERE tg_id=?", (target,), one=True):
                return self.err(404, "Foydalanuvchi topilmadi")
            if method == "GET" and len(parts) == 2:
                return self.send_json(get_records(target, section))
            if method == "POST" and len(parts) == 2:
                if sch.get("admin_create") and not is_admin:
                    return self.err(403, "Bu bo'limga faqat mentor vazifa qo'shadi")
                cnt = q("SELECT COUNT(*) c FROM records WHERE user_id=? AND section=?", (target, section), one=True)
                if cnt["c"] >= sch["limit"]:
                    raise ValueError(f"Eng ko'pi {sch['limit']} ta yozuv")
                data = clean_data(section, self.body(), is_admin)
                now = int(time.time())
                cur = q("INSERT INTO records(user_id,section,data,created_at,updated_at) VALUES(?,?,?,?,?)",
                        (target, section, json.dumps(data, ensure_ascii=False), now, now), commit=True)
                return self.send_json({"ok": True, "id": cur.lastrowid})
            if len(parts) == 3 and parts[2].isdigit():
                rid = int(parts[2])
                row = q("SELECT data FROM records WHERE id=? AND user_id=? AND section=?",
                        (rid, target, section), one=True)
                if not row:
                    return self.err(404, "Topilmadi")
                if method == "PUT":
                    data = clean_data(section, self.body(), is_admin, json.loads(row["data"]))
                    q("UPDATE records SET data=?, updated_at=? WHERE id=?",
                      (json.dumps(data, ensure_ascii=False), int(time.time()), rid), commit=True)
                    return self.send_json({"ok": True})
                if method == "DELETE":
                    if sch.get("admin_create") and not is_admin:
                        return self.err(403, "Faqat mentor o'chira oladi")
                    q("DELETE FROM records WHERE id=?", (rid,), commit=True)
                    return self.send_json({"ok": True})

        return self.err(404, "Topilmadi")


def main():
    if not BOT_TOKEN:
        print("⚠️  .env faylida BOT_TOKEN yo'q.")
    if not ADMIN_ID:
        print("⚠️  .env faylida ADMIN_ID yo'q.")
    if DEV_MODE:
        print("⚠️  DEV_MODE=1 — imzosiz kirish yoqilgan. Ishda o'chiring!")
    threading.Thread(target=bot_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[http] http://localhost:{PORT} da ishlayapti")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
