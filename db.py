"""The website's database: one SQLite file (data/site.db). Every query is parameterised; nothing a visitor types is ever put into SQL text.

    users        accounts (the password is never stored: an scrypt hash with its own salt)
    sessions     signed-in browsers (only a hash of the cookie's token is kept, so a copy of the database cannot sign anyone in)
    pageviews    one row per page seen (no IP address: a visitor is a hash of a salt that changes every day, the address and the browser)
    events       what visitors do on a page (scroll depth, a button pressed)
    downloads    one row per download of the installer
    attempts     sign-in and sign-up attempts, for the rate limits
    messages     the contact form
    salts        the day's random salt for the visitor hash (the old ones are deleted, so a visitor cannot be followed from one day to the next)
"""
import os
import secrets
import sqlite3
import time

from config import CFG

PATH = os.path.join(CFG["data_dir"], "site.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, name TEXT NOT NULL, pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', created REAL NOT NULL, last_login REAL, failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created REAL NOT NULL, expires REAL NOT NULL,
    ua TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pageviews (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, day TEXT NOT NULL, path TEXT NOT NULL, ref_host TEXT NOT NULL DEFAULT '', utm_source TEXT NOT NULL DEFAULT '',
    visitor TEXT NOT NULL, device TEXT NOT NULL DEFAULT '', browser TEXT NOT NULL DEFAULT '', user_id INTEGER
);
CREATE INDEX IF NOT EXISTS pv_day ON pageviews(day);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, day TEXT NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL DEFAULT '', value TEXT NOT NULL DEFAULT '',
    visitor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ev_day ON events(day);
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, day TEXT NOT NULL, version TEXT NOT NULL, file TEXT NOT NULL, visitor TEXT NOT NULL, user_id INTEGER,
    ref_host TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS dl_day ON downloads(day);
CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS at_key ON attempts(kind, key, ts);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL, body TEXT NOT NULL, user_id INTEGER, handled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS salts (day TEXT PRIMARY KEY, salt TEXT NOT NULL);
"""


def connect(path=None):
    con = sqlite3.connect(path or PATH, timeout=10, isolation_level=None)      # (autocommit: each statement is its own transaction)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    return con


def init(path=None):
    con = connect(path)
    con.executescript(SCHEMA)
    con.close()


def day_salt(con, day):
    """The day's salt (made once a day; the salts of older days are deleted)."""
    row = con.execute("SELECT salt FROM salts WHERE day=?", (day,)).fetchone()
    if row:
        return row["salt"]
    salt = secrets.token_hex(16)
    con.execute("INSERT OR IGNORE INTO salts(day, salt) VALUES(?,?)", (day, salt))
    con.execute("DELETE FROM salts WHERE day < ?", (day,))
    return con.execute("SELECT salt FROM salts WHERE day=?", (day,)).fetchone()["salt"]


def prune(con, keep_days=400):
    """Statistics older than about a year, and old attempts, are removed."""
    cut = time.time() - keep_days * 86400
    for t in ("pageviews", "events"):
        con.execute(f"DELETE FROM {t} WHERE ts < ?", (cut,))      # (t is one of the two fixed names above, never input)
    con.execute("DELETE FROM attempts WHERE ts < ?", (time.time() - 86400,))
    con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
