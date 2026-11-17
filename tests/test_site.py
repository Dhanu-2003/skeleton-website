"""The website, end to end, against a scratch database and a scratch release folder (nothing real is touched).

    python tests/test_site.py
"""
import json
import os
import re
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="site_test_")
REL = os.path.join(TMP, "releases")
os.makedirs(REL)
with open(os.path.join(REL, "AppSetup-9.9.9.exe"), "wb") as f:
    f.write(b"MZ" + b"\0" * 4096)
with open(os.path.join(REL, "secret.txt"), "w") as f:
    f.write("not for download")
with open(os.path.join(REL, "latest.json"), "w") as f:
    json.dump({"version": "9.9.9", "url": "AppSetup-9.9.9.exe", "sha256": "ab" * 32, "notes": "Test notes.", "built": "2026-01-01"}, f)
os.environ.update(SITE_DATA_DIR=os.path.join(TMP, "data"), SITE_RELEASES_DIR=REL, SITE_SITE_URL="https://example.test", SITE_SITE_NAME="Testapp")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as site  # noqa: E402
import db  # noqa: E402

FAILS = []


def ck(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  [{str(detail)[:300]}]"))
    if not ok:
        FAILS.append(name)


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
c = site.app.test_client()


def csrf_of(client):
    r = client.get("/contact", headers=UA)
    m = re.search(rb'name="csrf-token" content="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def q(sql, *a):
    con = db.connect()
    try:
        return con.execute(sql, a).fetchall()
    finally:
        con.close()


# ---- every page, and what search engines read
for path in ["/", "/features", "/how-it-works", "/download", "/faq", "/contact", "/security", "/privacy", "/terms", "/login", "/register"]:
    r = c.get(path, headers=UA)
    ok = r.status_code == 200 and b"<title>" in r.data and b'name="description"' in r.data and b'rel="canonical"' in r.data and b"og:image" in r.data
    ck(f"{path}: 200, a title, a description, a canonical link and a share picture", ok, r.status_code)
home = c.get("/", headers=UA).data.decode()
ck("the name is one setting: it is used, and no other product name is hard-coded in the pages", "Testapp" in home and "Nova" not in home)
ck("one h1 on the home page", home.count("<h1") == 1)
ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
ck("structured data for search engines (the app, its version, free)", ld and json.loads(ld.group(1))["@graph"][2]["softwareVersion"] == "9.9.9")
faq = c.get("/faq", headers=UA).data.decode()
blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', faq, re.S)
ck("the FAQ page has its own FAQ structured data", any('"FAQPage"' in b and "Which boards" in b for b in blocks))
r = c.get("/robots.txt")
ck("robots.txt: everything public is open, admin and accounts are not, the sitemap is named", b"Disallow: /admin" in r.data and b"Sitemap: https://example.test/sitemap.xml" in r.data)
r = c.get("/sitemap.xml")
ck("sitemap.xml lists the public pages with the public address", b"<loc>https://example.test/features</loc>" in r.data and b"/admin" not in r.data)
ck("security.txt is there", c.get("/.well-known/security.txt").status_code == 200)
ck("a page that does not exist: 404 with a page", c.get("/no-such", headers=UA).status_code == 404)

# ---- the security headers
h = c.get("/", headers=UA).headers
csp = h.get("Content-Security-Policy", "")
ck("CSP: only this site's own scripts and styles, no framing, no plugins", "script-src 'self'" in csp and "style-src 'self'" in csp and "frame-ancestors 'none'" in csp
   and "object-src 'none'" in csp and "unsafe" not in csp, csp)
ck("https: HSTS and upgrade-insecure-requests", "max-age=" in h.get("Strict-Transport-Security", "") and "upgrade-insecure-requests" in csp)
ck("nosniff, no framing, a strict referrer policy, a permissions policy", h.get("X-Content-Type-Options") == "nosniff" and h.get("X-Frame-Options") == "DENY"
   and h.get("Referrer-Policy") == "strict-origin-when-cross-origin" and "camera=()" in h.get("Permissions-Policy", ""))
ck("no inline script or style attribute in any page (the CSP would block it)", not any(re.search(r"<script(?![^>]*\bsrc=)(?![^>]*ld\+json)[^>]*>\s*\S", c.get(p, headers=UA).data.decode())
                                                                                      or re.search(r"\sstyle=\"", c.get(p, headers=UA).data.decode())
                                                                                      for p in ["/", "/features", "/download", "/login", "/register", "/faq", "/how-it-works"]))
cookies = site.app.test_client().get("/", headers=UA).headers.get_all("Set-Cookie")
ck("the CSRF cookie is HttpOnly, SameSite=Lax and Secure (https)", any("csrf=" in x and "HttpOnly" in x and "SameSite=Lax" in x and "Secure" in x for x in cookies), cookies)

# ---- accounts
tok = csrf_of(c)
r = c.post("/register", data={"name": "Ann", "email": "ann@example.test", "password": "short", "password2": "short", "csrf": tok}, headers=UA)
ck("a short password is refused", b"at least 10 characters" in r.data)
r = c.post("/register", data={"name": "Ann", "email": "ann@example.test", "password": "correct horse 42", "password2": "correct horse 42"}, headers=UA)
ck("a form without its CSRF token is refused", r.status_code == 400)
r = c.post("/register", data={"name": "Ann", "email": "ann@example.test", "password": "correct horse 42", "password2": "correct horse 42", "csrf": tok}, headers=UA)
ck("sign up: the account is made and signed in", r.status_code == 302 and "/account" in r.headers["Location"] and any("sid=" in x for x in r.headers.get_all("Set-Cookie")))
row = q("SELECT * FROM users WHERE email='ann@example.test'")[0]
ck("the password is not stored: an scrypt hash with its own salt", row["pw_hash"].startswith("scrypt$") and "correct horse" not in row["pw_hash"])
ck("a new account is never an admin by itself", row["role"] == "user")
ck("only the session token's hash is kept", len(q("SELECT token_hash FROM sessions")[0]["token_hash"]) == 64)
r = c.get("/account", headers=UA)
ck("the account page", r.status_code == 200 and b"Hello, Ann" in r.data or b"Welcome, Ann" in r.data)
ck("an ordinary account cannot open the dashboard or its data", c.get("/admin", headers=UA).status_code == 403 and c.get("/api/admin/stats").status_code == 403)
c.post("/logout", data={"csrf": csrf_of(c)}, headers=UA)
ck("sign out: the account page asks to sign in again", c.get("/account", headers=UA).status_code == 302)

c2 = site.app.test_client()
t2 = csrf_of(c2)
r = c2.post("/login", data={"email": "ann@example.test", "password": "wrong password 1", "csrf": t2}, headers=UA)
r_unknown = c2.post("/login", data={"email": "nobody@example.test", "password": "wrong password 1", "csrf": t2}, headers=UA)
ck("a wrong password and an unknown email get the same answer (no account guessing)", b"That email or password is not right." in r.data and b"That email or password is not right." in r_unknown.data)
for _ in range(5):
    c2.post("/login", data={"email": "ann@example.test", "password": "wrong password 1", "csrf": t2}, headers=UA)
r = c2.post("/login", data={"email": "ann@example.test", "password": "correct horse 42", "csrf": t2}, headers=UA)
ck("after 5 wrong passwords the account locks, even for the right one", b"locked" in r.data, r.data[-400:])
con = db.connect(); con.execute("UPDATE users SET locked_until=0, failed=0"); con.execute("DELETE FROM attempts"); con.close()
r = c2.post("/login?next=//evil.example/x", data={"email": "ann@example.test", "password": "correct horse 42", "csrf": t2, "next": "//evil.example/x"}, headers=UA)
ck("sign in works, and never sends you to another site afterwards", r.status_code == 302 and r.headers["Location"].endswith("/account"), r.headers.get("Location"))
c3 = site.app.test_client()
t3 = csrf_of(c3)
for i in range(21):
    r = c3.post("/login", data={"email": f"x{i}@example.test", "password": "whatever 12345", "csrf": t3}, headers=UA)
ck("too many tries from one address: it is slowed down", b"Too many tries" in r.data)
con = db.connect(); con.execute("DELETE FROM attempts"); con.close()

# password change signs out everywhere else
other = site.app.test_client()
to = csrf_of(other)
other.post("/login", data={"email": "ann@example.test", "password": "correct horse 42", "csrf": to}, headers=UA)
ck("(signed in on a second device)", other.get("/account", headers=UA).status_code == 200)
r = c2.post("/account/password", data={"old": "correct horse 42", "new": "battery staple 77", "csrf": csrf_of(c2)}, headers=UA)
ck("changing the password keeps you signed in here", c2.get("/account", headers=UA).status_code == 200)
ck("and signs the other device out", other.get("/account", headers=UA).status_code == 302)

# ---- the admin
con = db.connect(); con.execute("UPDATE users SET role='admin' WHERE email='ann@example.test'"); con.close()
ck("an admin opens the dashboard", c2.get("/admin", headers=UA).status_code == 200)

# ---- statistics: page views, honest about privacy
con = db.connect(); con.execute("DELETE FROM pageviews"); con.close()
c4 = site.app.test_client()
c4.get("/features?utm_source=newsletter", headers={**UA, "Referer": "https://search.example/q"})
c4.get("/download", headers=UA)
rows = q("SELECT * FROM pageviews ORDER BY id")
ck("a page view is counted, with the referrer's name and the campaign", len(rows) == 2 and rows[0]["ref_host"] == "search.example" and rows[0]["utm_source"] == "newsletter")
ck("no IP address is stored: a visitor is a hash", all("127.0.0.1" not in json.dumps(dict(r)) for r in rows) and len(rows[0]["visitor"]) == 20)
ck("the same browser on the same day is the same visitor", rows[0]["visitor"] == rows[1]["visitor"])
c4.get("/faq", headers={**UA, "DNT": "1"})
c4.get("/faq", headers={**UA, "Sec-GPC": "1"})
c4.get("/faq", headers={"User-Agent": "Googlebot/2.1"})
ck("Do Not Track, Global Privacy Control and bots are not counted", len(q("SELECT * FROM pageviews")) == 2)
c2.get("/admin", headers=UA)
ck("the admin's own pages are not counted", len(q("SELECT * FROM pageviews")) == 2)

# events (the beacon)
r = c4.post("/api/event", data=json.dumps({"name": "scroll_50", "path": "/"}), headers={**UA, "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"})
ck("an event from the site's own page is counted", r.status_code == 204 and q("SELECT name FROM events")[0]["name"] == "scroll_50")
r = c4.post("/api/event", data=json.dumps({"name": "scroll_50"}), headers={**UA, "Content-Type": "application/json", "Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"})
ck("an event from another site is refused", r.status_code == 403)
r = c4.post("/api/event", data=json.dumps({"name": "anything_else"}), headers={**UA, "Content-Type": "application/json"})
ck("only known event names are accepted", r.status_code == 400)

# ---- the download: served and counted
before = len(q("SELECT * FROM downloads"))
r = c4.get("/download/latest", headers=UA)
ck("the installer is served as a download", r.status_code == 200 and "attachment" in r.headers.get("Content-Disposition", "") and r.data.startswith(b"MZ"))
ck("and counted", len(q("SELECT * FROM downloads")) == before + 1 and q("SELECT version FROM downloads")[-1]["version"] == "9.9.9")
c4.get("/download/latest", headers={**UA, "Range": "bytes=2048-"})
ck("a resumed download is not counted twice", len(q("SELECT * FROM downloads")) == before + 1)
c4.get("/download/latest", headers={"User-Agent": "curl/8.0"})
ck("a bot's download is not counted", len(q("SELECT * FROM downloads")) == before + 1)
ck("the public count", c4.get("/api/downloads").get_json()["total"] == before + 1)
c2.get("/download/latest", headers=UA)
ck("a signed-in download is listed on the account page", b"9.9.9" in c2.get("/account", headers=UA).data)
with open(os.path.join(REL, "latest.json"), "w") as f:
    json.dump({"version": "6.6.6", "url": "../data/site.db"}, f)
ck("only the release named as a plain file is ever served (no path tricks)", c4.get("/download/latest", headers=UA).status_code == 404)
with open(os.path.join(REL, "latest.json"), "w") as f:
    json.dump({"version": "6.6.6", "url": "secret.txt"}, f)
ck("and only an installer file", c4.get("/download/latest", headers=UA).status_code == 404)

# ---- the admin's statistics
j = c2.get("/api/admin/stats?days=7").get_json()
ck("the dashboard's data: days, views, visitors, downloads, top pages, referrers, versions", len(j["days"]) == 7 and sum(j["views"]) >= 2 and sum(j["downloads"]) >= 2
   and any(r["key"] == "/features" for r in j["top_pages"]) and any(r["key"] == "search.example" for r in j["referrers"]) and j["versions"][0]["key"] == "9.9.9", j)

# ---- the contact form
t5 = csrf_of(c4)
r = c4.post("/contact", data={"name": "Bo", "email": "bo@example.test", "body": "Does it work with my board?", "csrf": t5}, headers=UA)
ck("a message is kept", b"Thank you" in r.data and q("SELECT body FROM messages")[0]["body"] == "Does it work with my board?")
c4.post("/contact", data={"name": "Bot", "email": "b@example.test", "body": "buy cheap things now", "website": "http://spam", "csrf": t5}, headers=UA)
ck("the hidden field catches bots", len(q("SELECT * FROM messages")) == 1)
ck("the admin sees it", b"Does it work with my board?" in c2.get("/admin", headers=UA).data)

# ---- deleting the account
r = c2.post("/account/delete", data={"password": "wrong one 123456", "csrf": csrf_of(c2)}, headers=UA)
ck("delete needs the password", len(q("SELECT * FROM users")) == 1)
r = c2.post("/account/delete", data={"password": "battery staple 77", "csrf": csrf_of(c2)}, headers=UA)
ck("delete: the account is gone; the counts stay, without the name", len(q("SELECT * FROM users")) == 0 and len(q("SELECT * FROM downloads")) >= 2
   and all(r["user_id"] is None for r in q("SELECT user_id FROM downloads")))

shutil.rmtree(TMP, ignore_errors=True)
print("\nALL PASS" if not FAILS else f"\nFAILURES: {FAILS}")
sys.exit(1 if FAILS else 0)
