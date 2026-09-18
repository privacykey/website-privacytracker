#!/usr/bin/env python3
"""
pin-page-revisions.py — stamp each page's latest commit into the page itself.

Usage:
    python3 scripts/pin-page-revisions.py               # privacy.html + legal.html
    python3 scripts/pin-page-revisions.py legal.html    # just one page

How it works
------------
privacy.html and legal.html each carry three kinds of marker element:

    <a data-page-commit-link href="https://github.com/…/commit/<full sha>">
    <span data-page-commit>abc1234</span>           (a <code> works too)
    <time data-page-commit-date datetime="2026-09-18">2026-09-18</time>

For each page this script:
  1. Asks git for the most recent commit that touched the file, skipping
     the pin commits this script itself produces (matched by their fixed
     subject line, PIN_SUBJECT). Without that exclusion every run would
     pin the previous pin and the chain would never settle; with it, a
     re-run against an already-pinned page is a no-op.
  2. Rewrites every marker in the page: the link's href gets the full
     hash, the hash element gets the 7-character short form, the <time>
     gets the committer date in both `datetime` and its text.
  3. Writes the page back only if something changed.

Regex-based and stdlib-only, like update-versions.py, so it stays
trivially auditable. It must run inside a checkout that has history
(fetch-depth: 0 in CI); a shallow clone makes git report the wrong
commit. It reads git, not the working tree, so uncommitted edits to a
page are not reflected until they are committed.

Exit codes
----------
  0 — success (whether or not anything changed)
  1 — usage or git error
  2 — a page is missing one of its markers (fail loudly rather than
      silently pinning nothing)

The GitHub Action checks `git diff --quiet` afterwards, so no special
"changes were made" exit code is needed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
#  Paths + constants
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parent

REPO_URL    = "https://github.com/privacykey/website-privacytracker"
PAGES       = ("privacy.html", "legal.html")
SHORT_LEN   = 7

# Subject line of the commits the workflow makes. Must match the
# workflow's `git commit -m` exactly — it is how those commits are
# recognised and skipped when looking for "the latest real change".
PIN_SUBJECT = "chore(pages): pin page revisions"

# An opening tag that carries the given attribute name exactly. The
# lookahead stops `data-page-commit` from also matching the longer
# `data-page-commit-link` / `data-page-commit-date`.
def _open_tag(attr: str) -> re.Pattern[str]:
    return re.compile(
        r'<(?P<tag>[a-zA-Z][\w-]*)'
        r'(?P<attrs>[^>]*?\s' + re.escape(attr) + r'(?=[\s>=])[^>]*)'
        r'>'
    )

# Same, plus the element's text and closing tag. Text is [^<]* — the
# markers are leaf elements by design (hash and date only).
def _leaf(attr: str) -> re.Pattern[str]:
    return re.compile(
        r'(?P<open><(?P<tag>[a-zA-Z][\w-]*)'
        r'[^>]*?\s' + re.escape(attr) + r'(?=[\s>=])[^>]*>)'
        r'(?P<inner>[^<]*)'
        r'(?P<close></(?P=tag)>)'
    )

LINK_TAG = _open_tag("data-page-commit-link")
HASH_EL  = _leaf("data-page-commit")
DATE_EL  = _leaf("data-page-commit-date")


# ──────────────────────────────────────────────────────────────────────
#  git
# ──────────────────────────────────────────────────────────────────────

def latest_commit(page: str) -> tuple[str, str]:
    """Return (full sha, YYYY-MM-DD committer date) of the newest non-pin
    commit that touched `page`."""
    cmd = [
        "git", "log", "-1", "--format=%H %cs",
        "--fixed-strings", f"--grep={PIN_SUBJECT}", "--invert-grep",
        "--", page,
    ]
    try:
        out = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        sys.exit(f"error: git log failed for {page}: {detail.strip()}")
    if not out:
        sys.exit(f"error: git has no commits touching {page} "
                 "(shallow clone? run with full history)")
    sha, date = out.split(" ", 1)
    return sha, date


# ──────────────────────────────────────────────────────────────────────
#  Rewriting a page
# ──────────────────────────────────────────────────────────────────────

def _set_attr(open_tag: str, name: str, value: str) -> str:
    """Replace name="…" inside an opening tag, or append it if absent."""
    pat = re.compile(r'(\s' + re.escape(name) + r'=")[^"]*(")')
    if pat.search(open_tag):
        return pat.sub(lambda m: m.group(1) + value + m.group(2), open_tag, count=1)
    return open_tag[:-1] + f' {name}="{value}">'


def rewrite(html: str, sha: str, date: str) -> tuple[str, dict[str, int]]:
    """Return (new_html, counts) where counts says how many of each
    marker were found — the caller treats zero as an error."""
    counts = {"link": 0, "hash": 0, "date": 0}
    short  = sha[:SHORT_LEN]
    url    = f"{REPO_URL}/commit/{sha}"

    def link(m: re.Match) -> str:
        counts["link"] += 1
        return _set_attr(m.group(0), "href", url)

    def hash_el(m: re.Match) -> str:
        counts["hash"] += 1
        return f"{m.group('open')}{short}{m.group('close')}"

    def date_el(m: re.Match) -> str:
        counts["date"] += 1
        opened = _set_attr(m.group("open"), "datetime", date)
        return f"{opened}{date}{m.group('close')}"

    html = LINK_TAG.sub(link, html)
    html = HASH_EL.sub(hash_el, html)
    html = DATE_EL.sub(date_el, html)
    return html, counts


# ──────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    pages = argv[1:] or list(PAGES)
    status = 0

    for page in pages:
        path = REPO_ROOT / page
        if not path.is_file():
            print(f"error: {page} not found at {path}", file=sys.stderr)
            return 1

        sha, date = latest_commit(page)
        html = path.read_text(encoding="utf-8")
        new_html, counts = rewrite(html, sha, date)

        missing = [k for k, n in counts.items() if n == 0]
        if missing:
            print(f"error: {page} has no {', '.join(missing)} marker(s) — "
                  "restore the data-page-commit* elements", file=sys.stderr)
            status = 2
            continue

        label = f"{page:14} {sha[:SHORT_LEN]} {date}"
        if new_html == html:
            print(f"{label}  (already pinned)")
        else:
            path.write_text(new_html, encoding="utf-8")
            print(f"{label}  pinned "
                  f"({counts['link']} link, {counts['hash']} hash, {counts['date']} date markers)")

    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
