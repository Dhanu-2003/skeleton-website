# The product website

The public site for the app: pages, accounts, a counted download, first-party traffic statistics and an admin dashboard. It runs on this laptop
for now; it is ready to be put online (see the end).

## Run it here

```
pip install -r requirements.txt
python app.py              # http://127.0.0.1:8765  (or double-click run.cmd)
```

Sign up on the site, then make that account an admin (only possible from the server's command line):

```
python manage.py make-admin you@example.com
```

The dashboard is at `/admin`. Other commands: `python manage.py stats 30`, `python manage.py prune`, `python manage.py og` (the share picture).

## Settings

One file, `config.json` (copy `config.example.json`), or environment variables `SITE_<NAME>`:

| setting | what it is |
|---|---|
| `site_name` | the product's name, used on every page, title and tag (change it here only) |
| `site_url` | the public address; with `https://` cookies become Secure and HSTS is sent |
| `releases_dir` | where `latest.json` and the installer are (default: the app's build output) |
| `contact_email` | shown on the contact and security pages |
| `track` | first-party statistics on or off |

The download serves exactly the installer `latest.json` names and counts it. To publish a new version, put the new installer and its
`latest.json` in `releases_dir`.

## What is where

```
app.py          pages, accounts, the download, the statistics, the dashboard API, the security headers
db.py           the SQLite database (data/site.db) and its tables
config.py       the settings; the secret key is made once in data/secret.key (never in git)
manage.py       the server-side commands
templates/      the pages (Jinja)
static/css      the look
static/js       main.js (motion, popups, statistics beacon), scene3d.js (the 3D board), admin.js (the dashboard), early.js
static/vendor   GSAP + ScrollTrigger, Lenis, Three.js (served from here: no CDN, so the strict CSP can stay)
tests/          python tests/test_site.py
```

## Security

- **Browser policy:** a strict Content-Security-Policy (no inline code, no third parties), no framing, nosniff, a strict referrer policy and a permissions policy, plus HSTS on https.
- **Forms:** every form and write has a CSRF token.
- **Passwords:** stored as scrypt hashes.
- **Sessions:** the token cookie is HttpOnly and SameSite; only its hash is stored, and it rotates at sign-in.
- **Rate limits:** on sign-in, sign-up and contact. An account locks for 15 minutes after five wrong passwords.
- **Admins:** made only from the server's command line, never by signing up.
- **Queries:** parameterised SQL everywhere, with length limits on all input.

## Statistics

- **Counted:** page views, unique visitors per day and downloads, plus a few actions (scroll depth, button presses, the FAQ).
- **Privacy:** no IP address is stored (a visitor is a daily-salted hash) and no cookies are used for it. Do Not Track, Global Privacy Control and known bots are not counted. Data older than about a year is pruned.

## Publish on GitHub Pages (static, no database)

```
powershell -ExecutionPolicy Bypass -File publish.ps1            # repository: <you>/nova-website (public)
```

It makes a separate public repository for the website and switches on Pages, built by `.github/workflows/pages.yml` (it runs the tests, then
`freeze.py` writes the static site). It then publishes the installer as a GitHub Release. The site needs no server:

- **Download button:** it points at the release file.
- **Download count:** it's GitHub's own count, shown live on the page.
- **Left out:** accounts, the contact form and the dashboard, because they need the server.

Run the script again after building a new installer to publish that version.

## Putting it online with the server (accounts, statistics)

1. A server with Python 3.11+, `pip install -r requirements.txt`.
2. `config.json` with the real `site_url` (https) and `contact_email`.
3. Run it behind a reverse proxy that terminates HTTPS (Caddy, nginx, IIS), for example `waitress-serve --listen=127.0.0.1:8765 app:app`.
4. `python manage.py make-admin you@example.com`, then `python manage.py og` once for the share picture.
5. Back up `data/` (the database and the secret key).

Libraries: GSAP (standard no-charge licence), Lenis (MIT), Three.js (MIT). Their licence files are in `static/vendor`.
