#!/usr/bin/env python3
"""
Generate markdown mirrors for every page on ryzecleaning.com.

Each .html page gets a sibling .md file with frontmatter and clean content,
stripped of nav, footer, scripts, and layout chrome — readable by AI tools.
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path


def install_deps():
    missing = []
    try:
        import bs4  # noqa: F401
    except ImportError:
        missing.append("beautifulsoup4")
    try:
        import markdownify  # noqa: F401
    except ImportError:
        missing.append("markdownify")
    if missing:
        print(f"Installing: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"]
        )


install_deps()

from bs4 import BeautifulSoup, Tag  # noqa: E402
import markdownify as mdlib  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://ryzecleaning.com"
TODAY = date.today().isoformat()

# Pages whose path contains any of these strings are skipped
SKIP_PATTERNS = ["404", "thanks", "noindex"]

# Tags stripped wholesale
STRIP_TAGS = ["nav", "header", "footer", "script", "style", "noscript", "iframe"]

# Class substrings that cause an element to be stripped
STRIP_CLASS_KEYWORDS = ["nav", "footer", "header", "menu", "chat", "widget", "cookie", "popup"]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def find_html_files() -> list[Path]:
    files: set[Path] = set()
    for p in REPO_ROOT.rglob("index.html"):
        files.add(p)
    for p in REPO_ROOT.glob("*.html"):
        if p.name != "index.html":
            files.add(p)
    return sorted(files)


def should_skip(path: Path) -> str | None:
    parts = str(path.relative_to(REPO_ROOT)).lower()
    for pat in SKIP_PATTERNS:
        if pat in parts:
            return f"matches skip pattern '{pat}'"
    return None


def canonical_url(html_path: Path) -> str:
    rel = html_path.relative_to(REPO_ROOT)
    parts = rel.parts
    if parts == ("index.html",):
        return BASE_URL + "/"
    if parts[-1] == "index.html":
        return BASE_URL + "/" + "/".join(parts[:-1]) + "/"
    # top-level foo.html → /foo
    return BASE_URL + "/" + html_path.stem


def output_path(html_path: Path) -> Path:
    if html_path.name == "index.html":
        return html_path.parent / "index.md"
    return html_path.with_suffix(".md")


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

def strip_elements(soup: Tag) -> None:
    for tag in STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    to_remove = []
    for el in soup.find_all(True):
        if not isinstance(el, Tag) or el.attrs is None:
            continue
        classes = " ".join(el.get("class", [])).lower()
        attrs = " ".join(
            str(v).lower() for k, v in el.attrs.items() if k in ("id", "role")
        )
        combined = classes + " " + attrs
        if any(kw in combined for kw in STRIP_CLASS_KEYWORDS):
            to_remove.append(el)
    for el in to_remove:
        el.decompose()


def drop_empty_wrappers(soup: Tag) -> None:
    changed = True
    while changed:
        changed = False
        for el in soup.find_all(["div", "span", "section", "aside"]):
            if not el.get_text(strip=True):
                el.decompose()
                changed = True


# ---------------------------------------------------------------------------
# Markdown cleaning
# ---------------------------------------------------------------------------

def clean_markdown(text: str) -> str:
    # Strip empty image tags  ![](...) or ![  ](...)
    text = re.sub(r'!\[\s*\]\([^)]*\)', '', text)
    # Remove lines that are only a standalone step number: 01 02 03 …
    text = re.sub(r'(?m)^\s*0\d\s*$', '', text)
    # Remove lines that are pure bullet-separator characters
    text = re.sub(r'(?m)^[•·\-–—|]{1,3}\s*$', '', text)
    # Remove leftover lines that are nothing but whitespace-only markdown bold/italic markers
    text = re.sub(r'(?m)^\s*[*_]{1,3}\s*[*_]{1,3}\s*$', '', text)
    # Collapse 3+ blank lines → 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process(html_path: Path) -> tuple[bool, str]:
    """Returns (generated, message)."""
    reason = should_skip(html_path)
    if reason:
        return False, reason

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # Frontmatter values
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content", "").strip() if desc_tag else ""

    url = canonical_url(html_path)

    # Work on body only
    body = soup.find("body") or soup
    strip_elements(body)
    drop_empty_wrappers(body)

    raw_md = mdlib.markdownify(str(body), heading_style="ATX", bullets="-")
    clean_md = clean_markdown(raw_md)

    frontmatter = (
        "---\n"
        f"title: {title}\n"
        f"description: {description}\n"
        f"url: {url}\n"
        f"last_updated: {TODAY}\n"
        "---\n\n"
    )

    out = output_path(html_path)
    out.write_text(frontmatter + clean_md + "\n", encoding="utf-8")
    return True, str(out.relative_to(REPO_ROOT))


def main() -> None:
    html_files = find_html_files()
    generated: list[str] = []
    skipped: list[tuple[str, str]] = []

    print(f"Scanning {REPO_ROOT}\n")

    for html_path in html_files:
        rel = str(html_path.relative_to(REPO_ROOT))
        ok, message = process(html_path)
        if ok:
            generated.append(message)
            print(f"  [OK]   {message}")
        else:
            skipped.append((rel, message))
            print(f"  [SKIP] {rel} — {message}")

    print(f"\n{'=' * 52}")
    print(f"Pages found:      {len(html_files)}")
    print(f"Mirrors generated:{len(generated):>3}")
    print(f"Pages skipped:    {len(skipped):>3}")
    if skipped:
        print("\nSkipped:")
        for path, reason in skipped:
            print(f"  - {path}: {reason}")


if __name__ == "__main__":
    main()
