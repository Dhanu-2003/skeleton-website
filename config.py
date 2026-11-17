"""The website's settings, in one place. Everything can be changed in config.json (next to this file) or by environment variables; nothing secret is
kept in the code. The product's name is ONE setting (site_name): every page, title and tag uses it."""
import json
import os
import secrets

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "site_name": "Nova",
    "tagline": "Your hardware engineer, on your desk.",
    "description": "Paste any working embedded code base and chat. It finds the board, installs the tools, builds, flashes, debugs and reads the output, "
                   "from the command line, with the AI model you choose.",
    "site_url": "http://127.0.0.1:8765",          # the public address (https in production: cookies become Secure and HSTS is sent)
    "releases_dir": os.path.normpath(os.path.join(HERE, "..", "nova-windows", "packaging", "build", "out")),
    "data_dir": os.path.join(HERE, "data"),
    "contact_email": "",                            # shown on the contact and security pages when set
    "track": True,                                  # first-party traffic statistics (no cookies for it, no third party)
    "session_days": 14,
    # the static site (GitHub Pages: files only, no server, no database): accounts and the contact form are left out, the download is the GitHub
    # Release's file, and the download count is GitHub's own count of it
    "static": False,
    "release_json": os.path.join(HERE, "release.json"),     # {version, file, size, sha256, notes, built, download_url}
    "github_repo": "",                                       # owner/name: where the release (and its download count) is
}


def _load():
    cfg = dict(DEFAULTS)
    p = os.path.join(HERE, "config.json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    for k in DEFAULTS:
        env = os.environ.get("SITE_" + k.upper())
        if env is not None:
            cfg[k] = type(DEFAULTS[k])(env) if not isinstance(DEFAULTS[k], bool) else env.lower() in ("1", "true", "yes")
    cfg["https"] = str(cfg["site_url"]).startswith("https://")
    os.makedirs(cfg["data_dir"], exist_ok=True)
    return cfg


CFG = _load()


def secret_key():
    """A random key made once and kept in data/secret.key (never in the code or in git)."""
    p = os.path.join(CFG["data_dir"], "secret.key")
    if not os.path.isfile(p):
        with open(p, "w", encoding="ascii") as f:
            f.write(secrets.token_hex(32))
    with open(p, encoding="ascii") as f:
        return f.read().strip()
