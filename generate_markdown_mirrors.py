#!/usr/bin/env python3
"""
Generate markdown mirrors of every page in the RYZE Cleaning site.
Writes {page_dir}/index.md with frontmatter + clean body text.
"""

import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# ── Ensure deps are available ────────────────────────────────────────────────
def ensure_deps():
    for pkg in ("bs4", "markdownify"):
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "beautifulsoup4" if pkg == "bs4" else pkg,
                                   "-q"])

ensure_deps()

from bs4 import BeautifulSoup, Comment          # noqa: E402
from markdownify import markdownify as md       # noqa: E402

# ── Config ───────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).parent
BASE_URL    = "https://ryzecleaning.com"
TODAY       = date.today().isoformat()

SKIP_DIRS   = {"404", "thanks"}                 # directory names to skip

# CSS selectors / tag names to strip before converting
STRIP_TAGS  = ["nav", "footer", "script", "style", "iframe", "noscript"]
STRIP_IDS   = {"navbar", "footer"}
STRIP_CLASSES = {                               # class fragments that match chat/widget noise
    "tawk", "chat", "widget", "cookie", "modal-overlay",
    "nav", "footer",
}


# ── Helpers ──────────────────────────────────────────────────────────────────
def find_pages(root: Path) -> list[Path]:
    pages = []
    for html in sorted(root.rglob("index.html")):
        parts = html.relative_to(root).parts
        # Skip any path segment that matches a skip dir
        if any(p in SKIP_DIRS for p in parts):
            continue
        pages.append(html)
    return pages


def get_meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name}) or \
          soup.find("meta", attrs={"property": name})
    return (tag.get("content") or "").strip() if tag else ""


def get_canonical(soup: BeautifulSoup) -> str:
    tag = soup.find("link", rel="canonical")
    return (tag.get("href") or "").strip() if tag else ""


def strip_noise(soup: BeautifulSoup) -> None:
    # Remove HTML comments
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    # Remove by tag name
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove by id
    for id_ in STRIP_IDS:
        el = soup.find(id=id_)
        if el:
            el.decompose()

    # Remove elements whose class list intersects STRIP_CLASSES
    # Collect first to avoid mutating the tree while iterating
    to_remove = []
    for el in soup.find_all(True):
        if el.attrs is None:
            continue
        classes = " ".join(el.get("class") or []).lower()
        if any(frag in classes for frag in STRIP_CLASSES):
            to_remove.append(el)
    for el in to_remove:
        el.decompose()

    # Remove empty wrappers (tags with no visible text after stripping)
    changed = True
    while changed:
        changed = False
        for el in soup.find_all(["div", "section", "article", "span", "p"]):
            if el.attrs is None:
                continue
            if not el.get_text(strip=True):
                el.decompose()
                changed = True


def clean_markdown(text: str) -> str:
    lines = text.splitlines()
    cleaned = []
    blank_run = 0

    for line in lines:
        stripped = line.strip()

        # Collapse 3+ consecutive blank lines → 2
        if stripped == "":
            blank_run += 1
            if blank_run <= 2:
                cleaned.append("")
            continue
        blank_run = 0

        # Drop standalone step numbers (lone "1.", "2." etc. on their own line)
        if re.fullmatch(r"\d+\.", stripped):
            continue

        # Drop empty image alts  ![](...) or ![ ](...)
        line = re.sub(r'!\[\s*\]\([^)]*\)', '', line)

        # Drop lines that became empty after substitution
        if not line.strip():
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip() + "\n"


def build_frontmatter(title: str, description: str, canonical: str) -> str:
    # Escape any quotes in values
    def q(s): return s.replace('"', '\\"')
    return (
        "---\n"
        f'title: "{q(title)}"\n'
        f'description: "{q(description)}"\n'
        f'canonical: "{q(canonical)}"\n'
        f'last_updated: "{TODAY}"\n'
        "---\n\n"
    )


def page_to_markdown(html_path: Path) -> str:
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    title       = soup.title.get_text(strip=True) if soup.title else ""
    description = get_meta(soup, "description")
    canonical   = get_canonical(soup) or f"{BASE_URL}/{html_path.parent.relative_to(REPO_ROOT)}"

    body = soup.body or soup
    strip_noise(body)

    raw_md  = md(str(body), heading_style="ATX", bullets="-", strip=["a"])
    cleaned = clean_markdown(raw_md)

    return build_frontmatter(title, description, canonical) + cleaned


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    pages   = find_pages(REPO_ROOT)
    written = []
    errors  = []

    for html_path in pages:
        out_path = html_path.parent / "index.txt"
        try:
            content = page_to_markdown(html_path)
            out_path.write_text(content, encoding="utf-8")
            rel = html_path.relative_to(REPO_ROOT)
            written.append(f"  ✓  {rel}  →  {out_path.relative_to(REPO_ROOT)}  ({len(content)} chars)")
        except Exception as exc:
            errors.append(f"  ✗  {html_path.relative_to(REPO_ROOT)}: {exc}")

    print("\n── RYZE Markdown Mirror Generator ──────────────────────")
    print(f"   Repo:  {REPO_ROOT}")
    print(f"   Date:  {TODAY}\n")
    for line in written:
        print(line)
    if errors:
        print("\nErrors:")
        for line in errors:
            print(line)
    print(f"\n   {len(written)} file(s) written, {len(errors)} error(s).")


if __name__ == "__main__":
    main()
