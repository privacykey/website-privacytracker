#!/usr/bin/env python3
"""
update-versions.py — sync legal.html version pills with the app's package.json.

Usage:
    python3 scripts/update-versions.py <path-or-url-to-package.json>

Examples:
    # Local checkout of the app sitting next to the website repo:
    python3 scripts/update-versions.py ../privacytracker/package.json

    # Direct from GitHub (what the workflow does):
    python3 scripts/update-versions.py \
        https://raw.githubusercontent.com/privacykey/privacytracker/main/package.json

How it works
------------
legal.html tags every version pill with `data-pkg="<package-name>"`:

    <span class="version" data-pkg="next">v16.2.4</span>

This script:
  1. Loads package.json (local file or HTTPS URL).
  2. Merges `dependencies` + `devDependencies` into one map.
  3. Strips semver-range prefixes (^, ~, >=, etc.) from each version.
  4. Walks every <span class="version" data-pkg="..."> in legal.html and
     replaces the inner text with `v<stripped-version>`.
  5. Writes legal.html back if anything changed.
  6. Prints a per-package summary of changes (or "no changes").

The script is intentionally regex-based and stdlib-only — no
third-party deps, no HTML parser. The data-pkg pattern is unique
enough that a precise regex is more reliable than tree manipulation,
and keeps the script trivially auditable.

Exit codes
----------
  0  — success (regardless of whether anything changed)
  1  — input error (file/URL missing, malformed JSON, etc.)
  2  — fatal error during HTML rewrite

The GitHub Action checks `git diff --quiet legal.html` after running,
so it doesn't need a special "changes were made" exit code from us.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# ──────────────────────────────────────────────────────────────────────
#  Paths + constants
# ──────────────────────────────────────────────────────────────────────

# Run the script from the repo root or anywhere — we resolve relative
# to the script's own location so `python3 scripts/update-versions.py`
# works regardless of cwd.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parent
LEGAL_HTML = REPO_ROOT / "legal.html"

# Pattern: <span class="version" data-pkg="<name>">v<old>...</span>
# Captures the package name and the surrounding tags so we can
# substitute just the inner text. .*? is non-greedy so we don't
# swallow neighbouring spans on the same line.
VERSION_SPAN = re.compile(
    r'(?P<open><span\s+class="version"\s+data-pkg="(?P<pkg>[^"]+)"\s*>)'
    r'(?P<old>.*?)'
    r'(?P<close></span>)',
    re.DOTALL,
)

# Matches semver-range prefixes the script should strip:
#   ^1.2.3  ~1.2.3  >=1.2.3  >1.2  *  workspace:* etc.
RANGE_PREFIX = re.compile(r'^[\s\^~>=<v*]+|^workspace:')


# ──────────────────────────────────────────────────────────────────────
#  Loading package.json — local path or HTTPS
# ──────────────────────────────────────────────────────────────────────

def load_package_json(source: str) -> dict:
    """Return the parsed package.json object from a file path or URL."""
    if source.startswith(("http://", "https://")):
        # Set a UA so GitHub raw doesn't refuse us
        req = Request(source, headers={"User-Agent": "privacytracker-update-versions/1"})
        try:
            with urlopen(req, timeout=20) as resp:
                payload = resp.read()
        except URLError as e:
            sys.exit(f"error: failed to fetch {source}: {e}")
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            sys.exit(f"error: package.json not found at {path}")
        payload = path.read_bytes()

    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        sys.exit(f"error: package.json is not valid JSON: {e}")


def collect_versions(pkg: dict) -> dict[str, str]:
    """Merge dependencies + devDependencies into a single name → version map."""
    merged: dict[str, str] = {}
    merged.update(pkg.get("dependencies", {}) or {})
    merged.update(pkg.get("devDependencies", {}) or {})
    # We deliberately ignore peerDependencies + optionalDependencies —
    # they're upstream constraints, not what's actually installed.
    return merged


def strip_range(raw: str) -> str:
    """`^16.2.4` → `16.2.4`, `>= 1.0` → `1.0`, `1.2.3` → `1.2.3`."""
    return RANGE_PREFIX.sub("", (raw or "").strip())


# ──────────────────────────────────────────────────────────────────────
#  Rewriting legal.html
# ──────────────────────────────────────────────────────────────────────

def rewrite(html: str, versions: dict[str, str]) -> tuple[str, list[tuple[str, str, str]], list[str]]:
    """
    Return (new_html, changes, missing).

    changes = [(pkg, old_version, new_version), …] for every span whose
        text actually moved. Spans whose text already matched are
        skipped silently.

    missing = [pkg, …] — packages referenced in legal.html that aren't in
        package.json. Reported as warnings; their version text is left
        as-is. Use cases:
          - Packages renamed upstream (we should rename in HTML)
          - Hand-managed entries (Inter, OpenDyslexic — they aren't
            npm deps and use synthetic data-pkg slugs that won't be
            in package.json by design).

    The synthetic slugs we know about:
        inter-typeface          (font, hand-versioned)
        opendyslexic-typeface   (font, hand-versioned)
    These are silently skipped — never reported as "missing".
    """
    SYNTHETIC = {"inter-typeface", "opendyslexic-typeface"}

    changes: list[tuple[str, str, str]] = []
    missing: list[str] = []
    seen: set[str] = set()

    def replace(m: re.Match) -> str:
        pkg = m.group("pkg")
        old = m.group("old")
        seen.add(pkg)

        if pkg in SYNTHETIC:
            return m.group(0)

        raw = versions.get(pkg)
        if raw is None:
            missing.append(pkg)
            return m.group(0)

        new = "v" + strip_range(raw)
        if new != old:
            changes.append((pkg, old, new))
        return f"{m.group('open')}{new}{m.group('close')}"

    new_html = VERSION_SPAN.sub(replace, html)
    return new_html, changes, missing


# ──────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1

    if not LEGAL_HTML.is_file():
        sys.exit(f"error: legal.html not found at {LEGAL_HTML}")

    print(f"sourcing versions from: {argv[1]}")
    pkg = load_package_json(argv[1])
    versions = collect_versions(pkg)
    print(f"  {len(versions)} packages in dependencies + devDependencies")

    html = LEGAL_HTML.read_text(encoding="utf-8")
    new_html, changes, missing = rewrite(html, versions)

    if changes:
        print(f"\napplying {len(changes)} change(s):")
        for pkg_name, old, new in changes:
            print(f"  {pkg_name:30}  {old:>12}  →  {new}")
    else:
        print("\nno changes — every tagged version already matches package.json")

    if missing:
        print(f"\nwarning: {len(missing)} package(s) referenced in legal.html are not in package.json:")
        for pkg_name in missing:
            print(f"  {pkg_name}")
        print("  (left unchanged — rename or remove the data-pkg in legal.html if no longer used)")

    if changes:
        LEGAL_HTML.write_text(new_html, encoding="utf-8")
        print(f"\nwrote {LEGAL_HTML.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
