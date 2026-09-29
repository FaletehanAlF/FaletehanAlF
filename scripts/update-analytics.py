#!/usr/bin/env python3
"""Regenerate the language rows in analytics.svg from live GitHub data.

Aggregates linguist byte counts across all non-fork public repos of GH_USER,
takes the top 5, and rewrites the block between ROWS-START / ROWS-END in
analytics.svg. Bar widths are normalized to the #1 language (like
github-readme-stats top-langs), labels show the real share of total bytes.

Usage (local):
    python3 scripts/update-analytics.py
Usage (CI): GH_TOKEN / GITHUB_TOKEN is picked up automatically for higher rate limits.
"""

import collections
import datetime
import json
import os
import re
import sys
import urllib.request

USERNAME = os.environ.get("GH_USER", "FaletehanAlF")
TOKEN = os.environ.get("GH_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
TRACK_W = 700
SVG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analytics.svg")

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
}


def meta_for(lang):
    if lang in LANG_META:
        return LANG_META[lang]
    short = re.sub(r"[^A-Za-z0-9+#]", "", lang)[:3].upper() or "??"
    return ("#38bdf8", "#04121f", short)


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


LABEL_DELAYS = [".35s", ".55s", ".75s", ".95s", "1.15s"]
BAR_DELAYS = [".45s", ".65s", ".85s", "1.05s", "1.25s"]
FILL_DELAYS = [".6s", ".8s", "1s", "1.2s", "1.4s"]
SHINE_DELAYS = [".6s", "1.1s", "1.6s", "2.1s", "2.4s"]
TIP_DELAYS = ["0s", ".4s", ".8s", "1.2s", "1.6s"]


def build_rows(top5, total, top_bytes):
    out = []
    for i, (lang, byte_count) in enumerate(top5, start=1):
        color, txt, abbr = meta_for(lang)
        pct = (byte_count / total * 100) if total else 0
        width = round(byte_count / top_bytes * TRACK_W) if top_bytes else 0
        width = max(width, 24)
        label_y = 156 + (i - 1) * 48
        bar_y = label_y + 8
        clip = f"barClip{i}"
        logo_fs = "10" if len(abbr) <= 2 else ("8.5" if len(abbr) == 3 else "8")
        out.append(f"<!-- ROW {i} : {esc(lang)} {pct:.1f}% -->")
        out.append(f'<g class="rise" style="animation-delay:{LABEL_DELAYS[i-1]}">')
        out.append(f'  <circle cx="86" cy="{label_y - 4}" r="5" fill="{color}" filter="url(#anaGlow)"/>')
        out.append(f'  <text x="100" y="{label_y}" class="stat-label">{esc(lang).upper()}</text>')
        out.append(f'  <text x="776" y="{label_y}" text-anchor="end" class="pct">{pct:.1f}%</text>')
        out.append(f'  <rect x="786" y="{label_y - 15}" width="34" height="20" rx="6" fill="{color}" stroke="{color}" stroke-opacity="0.4"/>')
        out.append(f'  <text x="803" y="{label_y - 1}" text-anchor="middle" class="logo-txt" fill="{txt}" font-size="{logo_fs}">{esc(abbr)}</text>')
        out.append("</g>")
        out.append(f'<g class="rise" style="animation-delay:{BAR_DELAYS[i-1]}">')
        out.append(f'  <rect x="80" y="{bar_y}" width="{TRACK_W}" height="10" rx="5" fill="#0a1e3a" stroke="#38bdf8" stroke-opacity="0.25"/>')
        out.append(f'  <rect class="bar-fill" x="80" y="{bar_y}" width="{width}" height="10" rx="5" fill="{color}" filter="url(#anaGlow)" style="animation-delay:{FILL_DELAYS[i-1]}"/>')
        out.append(f'  <g clip-path="url(#{clip})"><rect class="shine" x="80" y="{bar_y}" width="80" height="10" fill="url(#anaShine)" style="animation-delay:{SHINE_DELAYS[i-1]}"/></g>')
        out.append(f'  <circle class="tip" cx="{80 + width}" cy="{bar_y + 5}" r="3" fill="#ffffff" filter="url(#anaGlow)" style="animation-delay:{TIP_DELAYS[i-1]}"/>')
        out.append("</g>")
    return "\n".join(out)


def main():
    totals = collect_languages(USERNAME)
    if not totals:
        print("ERROR: no language data collected (rate limit or user has no repos?)", file=sys.stderr)
        sys.exit(1)
    total = sum(totals.values())
    top5 = totals.most_common(5)
    top_bytes = top5[0][1]
    print(f"Top 5 for {USERNAME} (total {total} bytes):")
    for lang, b in top5:
        print(f"  {lang}: {b} ({b/total*100:.1f}%)")

    with open(SVG_PATH, encoding="utf-8") as f:
        svg = f.read()
    rows = build_rows(top5, total, top_bytes)
    new_svg, n = re.subn(r"(<!-- ROWS-START.*?-->\n).*?(\n<!-- ROWS-END -->)", lambda m: m.group(1) + rows + m.group(2), svg, flags=re.DOTALL)
    if n == 0:
        print("ERROR: ROWS-START/ROWS-END markers not found in analytics.svg", file=sys.stderr)
        sys.exit(1)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    new_svg = re.sub(
        r"<!-- last-updated:.*?-->",
        f"<!-- last-updated: {stamp} | source: GitHub linguist bytes (public repos) | auto-updated by .github/workflows/update-analytics.yml -->",
        new_svg,
    )
    if new_svg != svg:
        with open(SVG_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_svg)
        print(f"Updated {SVG_PATH}")
    else:
        print("No changes.")


if __name__ == "__main__":
    main()
