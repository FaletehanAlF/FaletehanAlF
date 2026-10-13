#!/usr/bin/env python3
"""Regenerate the language rows in analytics.svg from live GitHub data.

Aggregates linguist byte counts across all non-fork public repos of GH_USER,
takes the top 12, and rewrites the block between ROWS-START / ROWS-END in
analytics.svg as two columns of 6 rows (left = rank 1-6, right = rank 7-12).
Bar widths are normalized to the #1 language (like github-readme-stats
top-langs), labels show the real share of total bytes. The "UPDATED <date>"
stamp in the footer is rewritten too, so the card always shows its freshness.

Usage (local):
    python3 scripts/update-analytics.py
Usage (CI): GH_TOKEN / GITHUB_TOKEN is picked up automatically for higher rate limits.
"""

import base64
import collections
import datetime
import json
import os
import re
import sys
import urllib.request

USERNAME = os.environ.get("GH_USER", "FaletehanAlF")
TOKEN = os.environ.get("GH_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
SVG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analytics.svg")

# Card geometry (must match analytics.svg viewBox 900x470).
CARD_W = 900
MARGIN_X = 60
COL_GAP = 40
COL_W = (CARD_W - 2 * MARGIN_X - COL_GAP) // 2
COL_X = (MARGIN_X, MARGIN_X + COL_W + COL_GAP)
ROW_Y0 = 158
ROW_STEP = 48
BAR_H = 10

TOTAL_LANGS = 12
ROWS_PER_COL = TOTAL_LANGS // 2
LOGO_SIZE = 24
MIN_BAR = 20

# GitHub linguist colors + contrasting text + short logo monogram for the badge at row end.
LANG_META = {
    "JavaScript": ("#F7DF1E", "#000000", "JS"),
    "TypeScript": ("#3178C6", "#ffffff", "TS"),
    "HTML": ("#E34F26", "#ffffff", "H5"),
    "CSS": ("#1572B6", "#ffffff", "CSS"),
    "PHP": ("#777BB3", "#ffffff", "PHP"),
    "Dart": ("#0175C2", "#ffffff", "D"),
    "Python": ("#3572A5", "#ffffff", "PY"),
    "Go": ("#00ADD8", "#ffffff", "GO"),
    "Vue": ("#41B883", "#ffffff", "V"),
    "Java": ("#B07219", "#ffffff", "JV"),
    "C++": ("#F34B7D", "#ffffff", "C+"),
    "C": ("#A8B9CC", "#000000", "C"),
    "C#": ("#178600", "#ffffff", "C#"),
    "Kotlin": ("#A97BFF", "#ffffff", "KT"),
    "Swift": ("#F05138", "#ffffff", "SW"),
    "Ruby": ("#701516", "#ffffff", "RB"),
    "Rust": ("#DEA584", "#000000", "RS"),
    "Shell": ("#89E051", "#000000", "SH"),
    "PowerShell": ("#5391FE", "#ffffff", "PS"),
    "Jupyter Notebook": ("#DA5B0B", "#ffffff", "NB"),
    "SCSS": ("#C6538C", "#ffffff", "SC"),
    "Less": ("#1D365D", "#ffffff", "LS"),
    "Dockerfile": ("#384D54", "#ffffff", "DK"),
    "CMake": ("#DA3434", "#ffffff", "CM"),
    "Blade": ("#FF2D20", "#ffffff", "BL"),
    "Svelte": ("#FF3E00", "#ffffff", "SV"),
    "Solidity": ("#363636", "#ffffff", "SO"),
    "Lua": ("#000080", "#ffffff", "LU"),
    "Groovy": ("#4298B8", "#ffffff", "GR"),
    "Perl": ("#0298C3", "#ffffff", "PL"),
    "PLpgSQL": ("#336790", "#ffffff", "PL"),
}


def meta_for(lang):
    if lang in LANG_META:
        return LANG_META[lang]
    short = re.sub(r"[^A-Za-z0-9+#]", "", lang)[:3].upper() or "??"
    return ("#38bdf8", "#04121f", short)


# Devicon paths for real language logos (inlined as base64 data URIs, same
# pattern skills.svg already uses, so they render inside README <img> context).
DEVICON_BASE = "https://cdn.jsdelivr.net/gh/devicons/devicon/icons"
ICON_PATH = {
    "JavaScript": "javascript/javascript-original.svg",
    "TypeScript": "typescript/typescript-original.svg",
    "HTML": "html5/html5-original.svg",
    "CSS": "css3/css3-original.svg",
    "PHP": "php/php-original.svg",
    "Dart": "dart/dart-original.svg",
    "Python": "python/python-original.svg",
    "Go": "go/go-original.svg",
    "Vue": "vuejs/vuejs-original.svg",
    "Java": "java/java-original.svg",
    "C++": "cplusplus/cplusplus-original.svg",
    "C": "c/c-original.svg",
    "C#": "csharp/csharp-original.svg",
    "Kotlin": "kotlin/kotlin-original.svg",
    "Swift": "swift/swift-original.svg",
    "Ruby": "ruby/ruby-original.svg",
    "Rust": "rust/rust-original.svg",
    "SCSS": "sass/sass-original.svg",
    "Less": "less/less-plain-wordmark.svg",
    "Shell": "bash/bash-original.svg",
    "PowerShell": "powershell/powershell-original.svg",
    "Jupyter Notebook": "python/python-original.svg",
    "Dockerfile": "docker/docker-original.svg",
    "CMake": "cmake/cmake-original.svg",
    "Blade": "laravel/laravel-original.svg",
    "Svelte": "svelte/svelte-original.svg",
    "Solidity": "solidity/solidity-original.svg",
    "Lua": "lua/lua-original.svg",
    "Groovy": "groovy/groovy-original.svg",
    "Perl": "perl/perl-original.svg",
    "PLpgSQL": "postgresql/postgresql-original.svg",
}

_icon_cache = {}


def icon_uri(lang):
    """Return a data: URI with the real language logo, or None on failure."""
    if lang in _icon_cache:
        return _icon_cache[lang]
    path = ICON_PATH.get(lang)
    if not path:
        _icon_cache[lang] = None
        return None
    try:
        req = urllib.request.Request(f"{DEVICON_BASE}/{path}", headers={"User-Agent": "analytics-updater"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        uri = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
        _icon_cache[lang] = uri
        return uri
    except Exception as e:
        print(f"WARN: icon fetch failed for {lang}: {e}", file=sys.stderr)
        _icon_cache[lang] = None
        return None


def fetch_json(url):
    headers = {"User-Agent": "analytics-updater", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def collect_languages(user):
    totals = collections.Counter()
    page = 1
    while True:
        repos = fetch_json(f"https://api.github.com/users/{user}/repos?per_page=100&page={page}&type=owner")
        if not repos:
            break
        for repo in repos:
            if repo.get("fork"):
                continue
            lang_url = repo.get("languages_url")
            if not lang_url:
                continue
            try:
                langs = fetch_json(lang_url)
            except Exception as e:
                print(f"WARN: skip languages for {repo.get('name')}: {e}", file=sys.stderr)
                continue
            for lang, byte_count in langs.items():
                totals[lang] += int(byte_count)
        if len(repos) < 100:
            break
        page += 1
        if page > 10:
            break
    return totals


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def at(base, step, i):
    return f"{base + step * i:.2f}s"


def build_rows(ranked, total, top_bytes):
    out = []
    for g, (lang, byte_count) in enumerate(ranked):
        col = 0 if g < ROWS_PER_COL else 1
        row = g if col == 0 else g - ROWS_PER_COL
        x = COL_X[col]
        entry = "slideL" if col == 0 else "slideR"
        color, txt, abbr = meta_for(lang)
        uri = icon_uri(lang)
        pct = (byte_count / total * 100) if total else 0
        width = round(byte_count / top_bytes * COL_W) if top_bytes else 0
        width = max(width, MIN_BAR)
        label_y = ROW_Y0 + row * ROW_STEP
        bar_y = label_y + 8
        clip = f"barClip{g + 1}"
        logo_x = x + COL_W - LOGO_SIZE
        logo_y = label_y - 21
        if uri:
            logo = (
                f'  <image href="{uri}" x="{logo_x}" y="{logo_y}" width="{LOGO_SIZE}" height="{LOGO_SIZE}">'
                f"<title>{esc(lang)}</title></image>"
            )
        else:
            fs = 11 if len(abbr) <= 1 else (9.5 if len(abbr) == 2 else (8 if len(abbr) == 3 else 7))
            logo = (
                f'  <rect x="{logo_x}" y="{logo_y}" width="{LOGO_SIZE}" height="{LOGO_SIZE}" rx="7" fill="{color}" stroke="{color}" stroke-opacity="0.5"/>\n'
                f'  <text x="{logo_x + LOGO_SIZE / 2:g}" y="{logo_y + 16}" text-anchor="middle" class="logo-txt" fill="{txt}" font-size="{fs:g}">{esc(abbr)}</text>'
            )
        out.append(f"<!-- ROW {g + 1} : {esc(lang)} {pct:.1f}% -->")
        out.append(f'<clipPath id="{clip}"><rect x="{x}" y="{bar_y}" width="{COL_W}" height="{BAR_H}" rx="5"/></clipPath>')
        out.append(f'<g class="{entry}" style="animation-delay:{at(0.30, 0.10, g)}">')
        out.append(f'  <text x="{x}" y="{label_y}" class="rank">{g + 1:02d}</text>')
        out.append(f'  <circle cx="{x + 24}" cy="{label_y - 4}" r="4.5" fill="{color}" filter="url(#anaGlow)"/>')
        out.append(f'  <text x="{x + 38}" y="{label_y}" class="stat-label">{esc(lang).upper()}</text>')
        out.append(f'  <text x="{x + COL_W - LOGO_SIZE - 8}" y="{label_y}" text-anchor="end" class="pct">{pct:.1f}%</text>')
        out.append(logo)
        out.append("</g>")
        out.append(f'<g class="{entry}" style="animation-delay:{at(0.42, 0.10, g)}">')
        out.append(
            f'  <rect x="{x}" y="{bar_y}" width="{COL_W}" height="{BAR_H}" rx="5" fill="#0a1e3a" stroke="#38bdf8" stroke-opacity="0.25"/>'
        )
        out.append(
            f'  <rect class="bar-fill" x="{x}" y="{bar_y}" width="{width}" height="{BAR_H}" rx="5" fill="{color}" '
            f'filter="url(#anaGlow)" style="animation-delay:{at(0.55, 0.10, g)}"/>'
        )
        out.append(
            f'  <g clip-path="url(#{clip})"><rect class="shine" x="{x}" y="{bar_y}" width="80" height="{BAR_H}" '
            f'fill="url(#anaShine)" style="animation-delay:{at(0.80, 0.20, g)}"/></g>'
        )
        out.append(
            f'  <circle class="tip" cx="{x + width}" cy="{bar_y + BAR_H // 2}" r="3" fill="#ffffff" '
            f'filter="url(#anaGlow)" style="animation-delay:{at(0.20, 0.30, g)}"/>'
        )
        out.append("</g>")
    return "\n".join(out)


def main():
    totals = collect_languages(USERNAME)
    if not totals:
        print("ERROR: no language data collected (rate limit or user has no repos?)", file=sys.stderr)
        sys.exit(1)
    total = sum(totals.values())
    ranked = totals.most_common(TOTAL_LANGS)
    top_bytes = ranked[0][1]
    print(f"Top {len(ranked)} for {USERNAME} (total {total} bytes):")
    for lang, b in ranked:
        print(f"  {lang}: {b} ({b / total * 100:.1f}%)")

    with open(SVG_PATH, encoding="utf-8") as f:
        svg = f.read()
    rows = build_rows(ranked, total, top_bytes)
    new_svg, n = re.subn(
        r"(<!-- ROWS-START.*?-->\n).*?(\n<!-- ROWS-END -->)",
        lambda m: m.group(1) + rows + m.group(2),
        svg,
        flags=re.DOTALL,
    )
    if n == 0:
        print("ERROR: ROWS-START/ROWS-END markers not found in analytics.svg", file=sys.stderr)
        sys.exit(1)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    new_svg = re.sub(
        r"<!-- last-updated:.*?-->",
        f"<!-- last-updated: {stamp} | source: GitHub linguist bytes (public repos) | auto-updated by .github/workflows/update-analytics.yml -->",
        new_svg,
    )
    new_svg, n = re.subn(
        r'(<tspan id="lastUpdated"[^>]*>)[^<]*(</tspan>)',
        lambda m: m.group(1) + stamp + m.group(2),
        new_svg,
    )
    if n == 0:
        print("WARN: lastUpdated tspan not found in analytics.svg", file=sys.stderr)
    if new_svg != svg:
        with open(SVG_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_svg)
        print(f"Updated {SVG_PATH}")
    else:
        print("No changes.")


if __name__ == "__main__":
    main()