"""The product's website: the pages, accounts, the download (counted), first-party traffic statistics and the admin dashboard.

Security, in short (details on /security):
  - every response carries a strict Content-Security-Policy (only this site's own scripts and styles: no inline code, no third party), frame-ancestors
    'none', nosniff, a strict referrer policy and a permissions policy; HSTS and Secure cookies when the site is served over https
  - every form and every JS write carries a CSRF token (double-submit: a random cookie and the same value in the form or header)
  - passwords: scrypt with a per-user salt; sessions: a random token in an HttpOnly, SameSite=Lax cookie, only its hash in the database; a new token at
    each sign-in; sign-in and sign-up are rate-limited per address and per account (an account locks for 15 minutes after 5 wrong passwords)
  - every SQL statement is parameterised; every input has a length limit; the download only ever serves the release named in latest.json
Statistics: no cookies for them, no IP address kept (a daily-salted hash), Do Not Track and Global Privacy Control are honoured, known bots are not
counted.

Run:  python app.py            (http://127.0.0.1:8765)      python manage.py --help   (make an admin, show the counts)
"""
import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import quote, urlparse

from flask import Flask, abort, g, jsonify, make_response, redirect, render_template, request, send_file, url_for

import db
from config import CFG, HERE, secret_key

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config.update(SECRET_KEY=secret_key(), MAX_CONTENT_LENGTH=64 * 1024, SEND_FILE_MAX_AGE_DEFAULT=7 * 86400, TEMPLATES_AUTO_RELOAD=False,
                  JSON_SORT_KEYS=False)

PAGES = [("/", "Home", 1.0), ("/features", "Features", 0.9), ("/how-it-works", "How it works", 0.8), ("/download", "Download", 0.9),
         ("/faq", "FAQ", 0.6), ("/contact", "Contact", 0.5), ("/security", "Security", 0.4), ("/privacy", "Privacy", 0.3), ("/terms", "Terms", 0.3)]
NAV = [("/features", "Features"), ("/how-it-works", "How it works"), ("/faq", "FAQ"), ("/download", "Download")]
EVENT_NAMES = {"scroll_25", "scroll_50", "scroll_75", "scroll_100", "cta", "nav", "faq_open", "video", "copy_hash", "time_30s", "time_120s"}
BOT = re.compile(r"(?i)bot|crawl|spider|slurp|headless|lighthouse|pagespeed|curl|wget|python-requests|httpx|aiohttp|go-http|java/|monitor|preview|scan")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
SESSION_COOKIE, CSRF_COOKIE = "sid", "csrf"


# ---------------------------------------------------------------------------------------------- the database for this request
def con():
    if "con" not in g:
        g.con = db.connect()
    return g.con


@app.teardown_appcontext
def _close(_exc):
    c = g.pop("con", None)
    if c is not None:
        c.close()


def now():
    return time.time()


def today():
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------------------------- the release (from the app's own build folder)
def release():
    """The newest installer as latest.json names it, or None. Only a plain file name next to latest.json is ever served."""
    if CFG["static"]:      # (the static site: the release as release.json describes it; the file is the GitHub Release's)
        try:
            with open(CFG["release_json"], encoding="utf-8") as f:
                j = json.load(f)
        except (OSError, ValueError):
            return None
        url = str(j.get("download_url") or "")
        if not url.startswith("https://"):
            return None
        size = int(j.get("size") or 0)
        return {"version": str(j.get("version") or "")[:20], "file": os.path.basename(str(j.get("file") or url))[:120], "path": "", "size": size,
                "size_mb": round(size / (1 << 20)), "sha256": str(j.get("sha256") or "")[:64], "notes": str(j.get("notes") or "")[:2000],
                "built": str(j.get("built") or "")[:20], "url": url}
    p = os.path.join(CFG["releases_dir"], "latest.json")
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return None
    name = os.path.basename(str(j.get("url") or ""))
    if not name or name != str(j.get("url")) or not name.lower().endswith((".exe", ".msi", ".zip")):
        return None
    path = os.path.join(CFG["releases_dir"], name)
    if not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    return {"version": str(j.get("version") or "")[:20], "file": name, "path": path, "size": size, "size_mb": round(size / (1 << 20)),
            "sha256": str(j.get("sha256") or "")[:64], "notes": str(j.get("notes") or "")[:2000], "built": str(j.get("built") or "")[:20],
            "url": "/download/latest"}


def download_total():
    if CFG["static"]:
        return 0      # (the static site: the count is GitHub's, read by the page itself)
    return con().execute("SELECT COUNT(*) FROM downloads").fetchone()[0]


# ---------------------------------------------------------------------------------------------- who is this (visitor, account)
def visitor():
    """A visitor for the statistics: a hash of the day's salt, the address and the browser (no address is kept; tomorrow it is someone new)."""
    day = today()
    salt = db.day_salt(con(), day)
    raw = f"{salt}|{request.remote_addr or ''}|{request.headers.get('User-Agent', '')[:300]}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def ua_kind():
    ua = request.headers.get("User-Agent", "")
    device = "tablet" if re.search(r"(?i)ipad|tablet", ua) else "mobile" if re.search(r"(?i)mobi|android|iphone", ua) else "desktop"
    for name, rx in (("Edge", r"Edg/"), ("Opera", r"OPR/"), ("Chrome", r"Chrome/"), ("Firefox", r"Firefox/"), ("Safari", r"Safari/")):
        if re.search(rx, ua):
            return device, name
    return device, "Other"


def is_bot():
    ua = request.headers.get("User-Agent", "")
    return not ua or bool(BOT.search(ua))


def no_track():
    return request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1"


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


@app.before_request
def _who():
    g.user = None
    tok = request.cookies.get(SESSION_COOKIE, "")
    if tok and len(tok) < 200:
        row = con().execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires > ?", (_hash(tok), now())).fetchone()
        g.user = dict(row) if row else None
    g.csrf = request.cookies.get(CSRF_COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", g.csrf or ""):
        g.csrf, g.new_csrf = secrets.token_urlsafe(32), True


def csrf_ok():
    sent = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
    have = request.cookies.get(CSRF_COOKIE, "")
    return bool(have) and hmac.compare_digest(sent, have)


def require_csrf():
    if not csrf_ok():
        abort(400, "The form expired. Reload the page and try again.")


def login_required(admin=False):
    if not g.user:
        return redirect(url_for("login", next=request.path))
    if admin and g.user.get("role") != "admin":
        abort(403)
    return None


# ---------------------------------------------------------------------------------------------- the rate limits
def limited(kind, key, most, window):
    """True when `key` already did `kind` `most` times in the last `window` seconds (the attempt is counted)."""
    c = con()
    n = c.execute("SELECT COUNT(*) FROM attempts WHERE kind=? AND key=? AND ts > ?", (kind, key, now() - window)).fetchone()[0]
    c.execute("INSERT INTO attempts(ts, kind, key) VALUES(?,?,?)", (now(), kind, key))
    return n >= most


def ip_key():
    return hashlib.sha256((request.remote_addr or "").encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------------------------- passwords and sessions
def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


def check_pw(pw, stored):
    try:
        _alg, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except (ValueError, TypeError):
        return False


_DUMMY = None


def dummy_check(pw):
    """The same work for an unknown email as for a known one (the answer's timing does not tell which emails have an account)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_pw(secrets.token_hex(8))
    check_pw(pw, _DUMMY)


def password_problem(pw, email=""):
    if len(pw) < 10:
        return "Use at least 10 characters."
    if len(pw) > 200:
        return "Use at most 200 characters."
    if len(set(pw)) < 5:
        return "Use a less repetitive password."
    if email and pw.lower() in email.lower():
        return "Do not use your email as the password."
    return ""


def start_session(resp, user_id):
    tok = secrets.token_urlsafe(32)
    c = con()
    c.execute("INSERT INTO sessions(token_hash, user_id, created, expires, ua) VALUES(?,?,?,?,?)",
              (_hash(tok), user_id, now(), now() + CFG["session_days"] * 86400, request.headers.get("User-Agent", "")[:200]))
    c.execute("UPDATE users SET last_login=?, failed=0, locked_until=0 WHERE id=?", (now(), user_id))
    resp.set_cookie(SESSION_COOKIE, tok, max_age=CFG["session_days"] * 86400, httponly=True, samesite="Lax", secure=CFG["https"], path="/")
    resp.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), max_age=CFG["session_days"] * 86400, httponly=True, samesite="Lax", secure=CFG["https"], path="/")
    return resp


def end_session(resp):
    tok = request.cookies.get(SESSION_COOKIE, "")
    if tok:
        con().execute("DELETE FROM sessions WHERE token_hash=?", (_hash(tok),))
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


def safe_next(n):
    n = str(n or "")
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n and len(n) < 300 else "/account"


# ---------------------------------------------------------------------------------------------- every response: the security headers, and the page view
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; manifest-src 'self'; worker-src 'self'")


@app.after_request
def _after(resp):
    resp.headers["Content-Security-Policy"] = CSP + ("; upgrade-insecure-requests" if CFG["https"] else "")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if CFG["https"]:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if resp.mimetype == "text/html":
        resp.headers.setdefault("Cache-Control", "no-store" if g.get("user") else "no-cache")
    if g.get("new_csrf"):
        resp.set_cookie(CSRF_COOKIE, g.csrf, max_age=CFG["session_days"] * 86400, httponly=True, samesite="Lax", secure=CFG["https"], path="/")
    try:
        _count_view(resp)
    except Exception:  # noqa: BLE001  (statistics never break a page)
        pass
    return resp


def _count_view(resp):
    if not CFG["track"] or request.method != "GET" or resp.status_code != 200 or resp.mimetype != "text/html":
        return
    if request.path.startswith(("/admin", "/account")) or is_bot() or no_track():
        return
    ref = request.headers.get("Referer", "")
    ref_host = (urlparse(ref).hostname or "")[:120] if ref else ""
    if ref_host and ref_host == (urlparse(CFG["site_url"]).hostname or request.host.split(":")[0]):
        ref_host = ""      # (moving between this site's own pages is not a referrer)
    device, browser = ua_kind()
    con().execute("INSERT INTO pageviews(ts, day, path, ref_host, utm_source, visitor, device, browser, user_id) VALUES(?,?,?,?,?,?,?,?,?)",
                  (now(), today(), request.path[:200], ref_host, (request.args.get("utm_source") or "")[:60], visitor(), device, browser,
                   (g.user or {}).get("id")))


# ---------------------------------------------------------------------------------------------- the pages
_asset_v = {}


def asset(rel):
    """A static file's address with its version (the file's change time): browsers keep it a week and fetch it again when it changes."""
    p = os.path.join(HERE, "static", rel)
    try:
        v = _asset_v.get(rel) or str(int(os.path.getmtime(p)))
    except OSError:
        v = "0"
    _asset_v[rel] = v
    return url_for("static", filename=rel) + "?v=" + v


@app.template_filter("datetime")
def _fmt_time(ts):
    try:
        return _dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError):
        return ""


@app.context_processor
def _ctx():
    return {"site": CFG, "user": g.get("user"), "csrf_token": g.get("csrf", ""), "asset": asset, "nav": NAV, "year": _dt.date.today().year,
            "canonical": CFG["site_url"].rstrip("/") + (request.path if request.path != "/" else "/")}


def page(tpl, title, description, **kw):
    return render_template(tpl, title=title, description=description, **kw)


@app.get("/")
def home():
    return page("index.html", f"{CFG['site_name']}: {CFG['tagline']}", CFG["description"], rel=release(), downloads=download_total())


@app.get("/features")
def features():
    return page("features.html", f"Features | {CFG['site_name']}",
                "Code base to running board from one chat: tool discovery, build, flash, debug, live board output, a terminal with an AI at the prompt, "
                "VS Code-style changes and Git push.", rel=release())


@app.get("/how-it-works")
def how():
    return page("how.html", f"How it works | {CFG['site_name']}",
                "From a code base link to a board that runs: read, find the board, install the tools, build, flash, check the output, debug.", rel=release())


@app.get("/download")
def download_page():
    return page("download.html", f"Download {CFG['site_name']} for Windows", f"Download {CFG['site_name']} for Windows 10 and 11 (64-bit).",
                rel=release(), downloads=download_total())


@app.get("/faq")
def faq():
    return page("faq.html", f"FAQ | {CFG['site_name']}", f"Answers about {CFG['site_name']}: boards, tools, AI models, privacy and the setup.")


@app.get("/security")
def security_page():
    return page("security.html", f"Security | {CFG['site_name']}", "How this website and the app keep your account and your code safe.")


@app.get("/privacy")
def privacy():
    return page("privacy.html", f"Privacy | {CFG['site_name']}", "What this website stores, and what it does not.")


@app.get("/terms")
def terms():
    return page("terms.html", f"Terms | {CFG['site_name']}", f"The terms for using this website and {CFG['site_name']}.")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    sent, err, form = False, "", {}
    if request.method == "POST":
        require_csrf()
        form = {k: (request.form.get(k) or "").strip() for k in ("name", "email", "body")}
        if request.form.get("website"):      # (a field people never see: only a bot fills it)
            sent = True
        elif limited("contact", ip_key(), 5, 3600):
            err = "Too many messages from here. Try again in an hour."
        elif not (1 <= len(form["name"]) <= 80) or not EMAIL.match(form["email"]) or not (10 <= len(form["body"]) <= 4000):
            err = "Give your name, a valid email and a message of at least 10 characters."
        else:
            con().execute("INSERT INTO messages(ts, name, email, body, user_id) VALUES(?,?,?,?,?)",
                          (now(), form["name"], form["email"], form["body"], (g.user or {}).get("id")))
            sent, form = True, {}
    return page("contact.html", f"Contact | {CFG['site_name']}", f"Write to the team behind {CFG['site_name']}.", sent=sent, err=err, form=form)


# ---------------------------------------------------------------------------------------------- accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect("/account")
    err, form = "", {}
    if request.method == "POST":
        require_csrf()
        form = {"name": (request.form.get("name") or "").strip()[:80], "email": (request.form.get("email") or "").strip().lower()[:254]}
        pw = request.form.get("password") or ""
        if limited("register", ip_key(), 5, 3600):
            err = "Too many accounts made from here. Try again in an hour."
        elif not form["name"] or not EMAIL.match(form["email"]):
            err = "Give your name and a valid email."
        elif password_problem(pw, form["email"]):
            err = password_problem(pw, form["email"])
        elif pw != (request.form.get("password2") or ""):
            err = "The two passwords are not the same."
        elif con().execute("SELECT 1 FROM users WHERE email=?", (form["email"],)).fetchone():
            err = "That email already has an account: sign in instead."
        else:
            cur = con().execute("INSERT INTO users(email, name, pw_hash, role, created) VALUES(?,?,?,?,?)",
                                (form["email"], form["name"], hash_pw(pw), "user", now()))      # (an admin is only ever made on the server: manage.py make-admin)
            return start_session(redirect("/account?welcome=1"), cur.lastrowid)
    return page("register.html", f"Create an account | {CFG['site_name']}", f"Create your {CFG['site_name']} account.", err=err, form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(safe_next(request.args.get("next")))
    err, email = "", ""
    if request.method == "POST":
        require_csrf()
        email = (request.form.get("email") or "").strip().lower()[:254]
        pw = request.form.get("password") or ""
        if limited("login_ip", ip_key(), 20, 900) or limited("login_acct", hashlib.sha256(email.encode()).hexdigest()[:24], 10, 900):
            err = "Too many tries. Wait 15 minutes and try again."
        else:
            u = con().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if u is None:
                dummy_check(pw)
                err = "That email or password is not right."
            elif u["locked_until"] > now():
                err = "This account is locked for a few minutes after too many wrong passwords. Try again later."
            elif not check_pw(pw, u["pw_hash"]):
                failed = u["failed"] + 1
                con().execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (failed, now() + 900 if failed >= 5 else 0, u["id"]))
                err = "That email or password is not right."
            else:
                return start_session(redirect(safe_next(request.form.get("next") or request.args.get("next"))), u["id"])
    return page("login.html", f"Sign in | {CFG['site_name']}", f"Sign in to your {CFG['site_name']} account.", err=err, email=email,
                next=safe_next(request.args.get("next")))


@app.post("/logout")
def logout():
    require_csrf()
    return end_session(redirect("/"))


@app.get("/account")
def account():
    r = login_required()
    if r:
        return r
    mine = con().execute("SELECT version, ts FROM downloads WHERE user_id=? ORDER BY ts DESC LIMIT 20", (g.user["id"],)).fetchall()
    return page("account.html", f"Your account | {CFG['site_name']}", "Your account.", mine=mine, rel=release(),
                welcome=request.args.get("welcome") == "1", ok=request.args.get("ok", ""), err=request.args.get("err", ""))


@app.post("/account/password")
def account_password():
    r = login_required()
    if r:
        return r
    require_csrf()
    old, new = request.form.get("old") or "", request.form.get("new") or ""
    if not check_pw(old, g.user["pw_hash"]):
        return redirect("/account?err=" + quote("The current password is not right."))
    p = password_problem(new, g.user["email"])
    if p:
        return redirect("/account?err=" + quote(p))
    c = con()
    c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(new), g.user["id"]))
    c.execute("DELETE FROM sessions WHERE user_id=?", (g.user["id"],))      # (signed out everywhere, then signed in again here)
    return start_session(redirect("/account?ok=" + quote("Password changed. Other devices are signed out.")), g.user["id"])


@app.post("/account/delete")
def account_delete():
    r = login_required()
    if r:
        return r
    require_csrf()
    if not check_pw(request.form.get("password") or "", g.user["pw_hash"]):
        return redirect("/account?err=" + quote("The password is not right: the account was not deleted."))
    c = con()
    c.execute("UPDATE downloads SET user_id=NULL WHERE user_id=?", (g.user["id"],))
    c.execute("UPDATE pageviews SET user_id=NULL WHERE user_id=?", (g.user["id"],))
    c.execute("UPDATE messages SET user_id=NULL WHERE user_id=?", (g.user["id"],))
    c.execute("DELETE FROM users WHERE id=?", (g.user["id"],))
    resp = redirect("/?deleted=1")
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------------------------------------- the download (counted)
@app.get("/download/latest")
def download_file():
    rel = release()
    if not rel:
        abort(404)
    rng = request.headers.get("Range", "")
    if not is_bot() and (not rng or rng.replace(" ", "").startswith("bytes=0-")):      # (a resumed download is not a second one)
        ref = request.headers.get("Referer", "")
        con().execute("INSERT INTO downloads(ts, day, version, file, visitor, user_id, ref_host) VALUES(?,?,?,?,?,?,?)",
                      (now(), today(), rel["version"], rel["file"], visitor() if not no_track() else "dnt", (g.user or {}).get("id"),
                       (urlparse(ref).hostname or "")[:120] if ref else ""))
    resp = send_file(rel["path"], as_attachment=True, download_name=rel["file"], max_age=0, conditional=True, etag=True)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/api/downloads")
def api_downloads():
    rel = release()
    return jsonify(total=download_total(), version=(rel or {}).get("version", ""))


# ---------------------------------------------------------------------------------------------- what visitors do (a beacon from this site's own pages)
def same_origin():
    site = request.headers.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        return False
    origin = request.headers.get("Origin")
    return not origin or urlparse(origin).netloc == request.host


@app.post("/api/event")
def api_event():
    if not CFG["track"] or no_track() or is_bot():
        return ("", 204)
    if not same_origin():
        abort(403)
    if limited("event", ip_key(), 120, 60):
        return ("", 204)
    try:
        j = json.loads(request.get_data(as_text=True)[:2000] or "{}")
    except ValueError:
        abort(400)
    name = str(j.get("name") or "")
    if name not in EVENT_NAMES:
        abort(400)
    con().execute("INSERT INTO events(ts, day, name, path, value, visitor) VALUES(?,?,?,?,?,?)",
                  (now(), today(), name, str(j.get("path") or "")[:200], str(j.get("value") or "")[:120], visitor()))
    return ("", 204)


# ---------------------------------------------------------------------------------------------- the admin dashboard
@app.get("/admin")
def admin():
    r = login_required(admin=True)
    if r:
        return r
    msgs = con().execute("SELECT * FROM messages ORDER BY ts DESC LIMIT 50").fetchall()
    return page("admin.html", f"Dashboard | {CFG['site_name']}", "Traffic and downloads.", msgs=msgs)


@app.get("/api/admin/stats")
def admin_stats():
    if not g.user or g.user.get("role") != "admin":
        abort(403)
    days = max(1, min(365, int(request.args.get("days", "30") or 30) if str(request.args.get("days", "30")).isdigit() else 30))
    start = (_dt.datetime.utcnow() - _dt.timedelta(days=days - 1)).strftime("%Y-%m-%d")
    c = con()
    span = [(_dt.datetime.utcnow() - _dt.timedelta(days=days - 1 - i)).strftime("%Y-%m-%d") for i in range(days)]

    def per_day(sql):
        got = {r[0]: r[1] for r in c.execute(sql, (start,)).fetchall()}
        return [got.get(d, 0) for d in span]

    def top(sql, n=10):
        return [{"key": r[0] or "(direct)", "n": r[1]} for r in c.execute(sql, (start,)).fetchall()[:n]]
    return jsonify(
        days=span,
        views=per_day("SELECT day, COUNT(*) FROM pageviews WHERE day>=? GROUP BY day"),
        visitors=per_day("SELECT day, COUNT(DISTINCT visitor) FROM pageviews WHERE day>=? GROUP BY day"),
        downloads=per_day("SELECT day, COUNT(*) FROM downloads WHERE day>=? GROUP BY day"),
        top_pages=top("SELECT path, COUNT(*) n FROM pageviews WHERE day>=? GROUP BY path ORDER BY n DESC"),
        referrers=top("SELECT ref_host, COUNT(*) n FROM pageviews WHERE day>=? GROUP BY ref_host ORDER BY n DESC"),
        sources=top("SELECT utm_source, COUNT(*) n FROM pageviews WHERE day>=? AND utm_source != '' GROUP BY utm_source ORDER BY n DESC"),
        devices=top("SELECT device, COUNT(*) n FROM pageviews WHERE day>=? GROUP BY device ORDER BY n DESC"),
        browsers=top("SELECT browser, COUNT(*) n FROM pageviews WHERE day>=? GROUP BY browser ORDER BY n DESC"),
        versions=top("SELECT version, COUNT(*) n FROM downloads WHERE day>=? GROUP BY version ORDER BY n DESC"),
        events=top("SELECT name, COUNT(*) n FROM events WHERE day>=? GROUP BY name ORDER BY n DESC", 20),
        totals={"views": c.execute("SELECT COUNT(*) FROM pageviews").fetchone()[0],
                "visitors_today": c.execute("SELECT COUNT(DISTINCT visitor) FROM pageviews WHERE day=?", (today(),)).fetchone()[0],
                "downloads": c.execute("SELECT COUNT(*) FROM downloads").fetchone()[0],
                "users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "messages": c.execute("SELECT COUNT(*) FROM messages WHERE handled=0").fetchone()[0]})


@app.post("/admin/messages/<int:mid>/handled")
def admin_handled(mid):
    r = login_required(admin=True)
    if r:
        return r
    require_csrf()
    con().execute("UPDATE messages SET handled=1 WHERE id=?", (mid,))
    return redirect("/admin#messages")


# ---------------------------------------------------------------------------------------------- for search engines and browsers
@app.get("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /account\nDisallow: /api/\nDisallow: /download/latest\n\nSitemap: {CFG['site_url'].rstrip('/')}/sitemap.xml\n"
    return app.response_class(body, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    base = CFG["site_url"].rstrip("/")
    mod = _dt.datetime.utcfromtimestamp(max(os.path.getmtime(os.path.join(HERE, "templates", f)) for f in os.listdir(os.path.join(HERE, "templates")))).strftime("%Y-%m-%d")
    urls = "".join(f"<url><loc>{base}{p}</loc><lastmod>{mod}</lastmod><priority>{pr}</priority></url>" for p, _n, pr in PAGES)
    return app.response_class('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>",
                              mimetype="application/xml")


@app.get("/manifest.webmanifest")
def manifest():
    return app.response_class(json.dumps({"name": CFG["site_name"], "short_name": CFG["site_name"], "start_url": "/", "display": "standalone",
                                          "background_color": "#05060a", "theme_color": "#05060a",
                                          "icons": [{"src": "/static/img/icon.svg", "sizes": "any", "type": "image/svg+xml"}]}),
                              mimetype="application/manifest+json")


@app.get("/.well-known/security.txt")
def security_txt():
    exp = (_dt.datetime.utcnow() + _dt.timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
    contact = f"mailto:{CFG['contact_email']}" if CFG["contact_email"] else f"{CFG['site_url'].rstrip('/')}/contact"
    return app.response_class(f"Contact: {contact}\nExpires: {exp}\nPreferred-Languages: en\nCanonical: {CFG['site_url'].rstrip('/')}/.well-known/security.txt\n",
                              mimetype="text/plain")


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


@app.get("/og-card")
def og_card():
    """The picture shown when a link to the site is shared (rendered once into static/img/og.png)."""
    return page("og.html", CFG["site_name"], CFG["description"])


# ---------------------------------------------------------------------------------------------- errors
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)
@app.errorhandler(429)
@app.errorhandler(500)
def _error(e):
    code = getattr(e, "code", 500) or 500
    words = {400: "That request did not look right.", 403: "That page is not for this account.", 404: "This page does not exist.",
             405: "That is not how this page is used.", 413: "That was too much to send.", 429: "Too many requests. Slow down a little.",
             500: "Something went wrong on our side."}.get(code, "Something went wrong.")
    desc = getattr(e, "description", "") if code == 400 else ""
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error=words), code
    return make_response(render_template("error.html", title=f"{code} | {CFG['site_name']}", description=words, code=code, words=words, detail=desc), code)


def main():
    db.init()
    host, port = "127.0.0.1", int(os.environ.get("PORT", "8765"))
    try:
        from waitress import serve      # (a production-grade server when it is installed)
        print(f"{CFG['site_name']} website on http://{host}:{port}  (waitress)")
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        print(f"{CFG['site_name']} website on http://{host}:{port}  (Flask's own server: for this laptop only)")
        app.run(host=host, port=port, debug=False, threaded=True)


db.init()

if __name__ == "__main__":
    main()
