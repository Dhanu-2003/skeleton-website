"""The static website (for GitHub Pages: files only, no server, no database), written into dist/.

    python freeze.py --site-url https://<owner>.github.io/<repo> --repo <owner>/<repo>

Every public page is rendered by the app itself in its static mode (no accounts, no contact form, the download is the GitHub Release's file and its count is
GitHub's own), and every link is moved under the site's sub-path (a project site lives at /<repo>/). The app's own tests still run on the full site."""
import argparse
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))

PAGES = ["/", "/features", "/how-it-works", "/download", "/faq", "/contact", "/security", "/privacy", "/terms"]
FILES = ["/robots.txt", "/sitemap.xml", "/manifest.webmanifest", "/.well-known/security.txt"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--repo", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    a = ap.parse_args()
    site_url = a.site_url.rstrip("/")
    base = urlparse(site_url).path.rstrip("/")      # ("/<repo>" for a project site, "" for a user site or a custom domain)
    os.environ.update(SITE_STATIC="1", SITE_TRACK="0", SITE_SITE_URL=site_url, SITE_GITHUB_REPO=a.repo, SITE_DATA_DIR=tempfile.mkdtemp(prefix="freeze_"))
    sys.path.insert(0, HERE)
    import app as site

    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    c = site.app.test_client()
    ua = {"User-Agent": "freeze"}

    def fix(text):
        """Every link of this site under its sub-path; links to other sites and in-page anchors are left as they are."""
        if not base:
            return text
        text = re.sub(r'(\s(?:href|src|action)=")/(?!/)', lambda m: m.group(1) + base + "/", text)
        return text

    def write(rel, body):
        p = os.path.join(out, rel.lstrip("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(body)

    for path in PAGES:
        r = c.get(path, headers=ua)
        if r.status_code != 200:
            raise SystemExit(f"{path}: {r.status_code}")
        write("index.html" if path == "/" else path.strip("/") + "/index.html", fix(r.get_data(as_text=True)).encode("utf-8"))
    r = c.get("/no-such-page-for-the-404", headers=ua)
    write("404.html", fix(r.get_data(as_text=True)).encode("utf-8"))
    for path in FILES:
        r = c.get(path, headers=ua)
        body = r.get_data(as_text=True)
        if path == "/manifest.webmanifest":
            body = body.replace('"start_url": "/"', f'"start_url": "{base}/"').replace('"/static/', f'"{base}/static/')
        if path == "/sitemap.xml":      # (only the pages the static site has)
            body = re.sub(r"<url><loc>[^<]*/(?:login|register|account|admin)[^<]*</loc>.*?</url>", "", body)
        write(path, body.encode("utf-8"))
    shutil.copytree(os.path.join(HERE, "static"), os.path.join(out, "static"), ignore=shutil.ignore_patterns("*.map"))
    write(".nojekyll", b"")      # (GitHub Pages serves every file as it is, the .well-known folder too)
    n = sum(len(f) for _d, _s, f in os.walk(out))
    print(f"Static site written: {out} ({n} files), base path '{base or '/'}', site {site_url}")


if __name__ == "__main__":
    main()
