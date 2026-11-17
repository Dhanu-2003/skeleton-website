"""The website's command line (run on the server only).

    python manage.py init                      make the database
    python manage.py make-admin EMAIL          give an existing account the admin role (the dashboard at /admin)
    python manage.py stats [DAYS]              page views, visitors and downloads of the last DAYS days (30)
    python manage.py prune                     remove statistics older than about a year
    python manage.py og                        render the share picture (static/img/og.png) with the browser on this machine
"""
import os
import subprocess
import sys
import time

import db
from config import CFG, HERE


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    db.init()
    c = db.connect()
    if cmd == "init":
        print("Database ready:", db.PATH)
    elif cmd == "make-admin" and len(argv) == 2:
        n = c.execute("UPDATE users SET role='admin' WHERE email=?", (argv[1].strip().lower(),)).rowcount
        print("Done: that account is an admin now." if n else "No account with that email: sign up on the website first.")
        return 0 if n else 1
    elif cmd == "stats":
        days = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 30
        since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - (days - 1) * 86400))
        v = c.execute("SELECT COUNT(*), COUNT(DISTINCT visitor || day) FROM pageviews WHERE day >= ?", (since,)).fetchone()
        d = c.execute("SELECT COUNT(*) FROM downloads WHERE day >= ?", (since,)).fetchone()[0]
        print(f"Last {days} days: {v[0]} page views, {v[1]} visitor-days, {d} downloads. All time downloads: "
              f"{c.execute('SELECT COUNT(*) FROM downloads').fetchone()[0]}")
    elif cmd == "prune":
        db.prune(c)
        print("Old statistics removed.")
    elif cmd == "og":
        return og()
    else:
        print(__doc__)
        return 1
    return 0


def og():
    """static/img/og.png: the /og-card page (1200 x 630) photographed by Edge or Chrome without a window. The website must be running."""
    out = os.path.join(HERE, "static", "img", "og.png")
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.isfile(exe):
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--screenshot={out}", "--window-size=1200,630",
                            CFG["site_url"].rstrip("/") + "/og-card"], timeout=60, capture_output=True)
            print("Written:", out if os.path.isfile(out) else "(the browser did not write it: is the website running?)")
            return 0
    print("No Edge or Chrome found.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
