#!/usr/bin/env python3
"""Draw the figure at the top of README.md from the tables in results/.

    python3 make_figure.py

Writes docs/images/checks-light.svg and docs/images/checks-dark.svg, and prints the sentence the figure's alt text uses.
Exits 1 if a table's counts differ from the total printed above or below it.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "images")
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"text": "#0b0b0b", "muted": "#52514e", "PASS": "#2a78d6", "FAIL": "#eb6834", "SKIP": "#b4b2a7"},
    "dark": {"text": "#f0efec", "muted": "#c3c2b7", "PASS": "#3987e5", "FAIL": "#d95926", "SKIP": "#6f6e66"},
}
# The newest pass: file in results/ and the heading it starts at
NAME, HEADING = "v0.17.0-generation.md", "# 0.17.0 generation — tag-day pass"
KEYS = ["PASS", "FAIL", "SKIP"]
TITLE = "LiteRT-LM 0.17.0 on the day of its GitHub tag, by install route"
WIDTH, BAR, GAP = 860, 24, 2


def section(text, heading):
    """Return the part of text from the top-level heading to the next top-level heading."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(heading)), None)
    if start is None:
        sys.exit(f"make_figure: no heading {heading!r}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("# ")), len(lines))
    return "\n".join(lines[start:end])


def count():
    """Return [(channel, {PASS, FAIL, SKIP})] in table order, checked against the pass's printed total."""
    path = os.path.join(HERE, "results", NAME)
    if not os.path.exists(path):
        sys.exit(f"make_figure: results/{NAME} not found")
    with open(path, encoding="utf-8") as f:
        part = section(f.read(), HEADING)
    channels = {}
    for channel, verdict in re.findall(r"^\|([^|]*)\|[^|]*\|\s*\S+\s+(PASS|FAIL|SKIP)\s*\|", part, re.M):
        channels.setdefault(channel.strip(), dict.fromkeys(KEYS, 0))[verdict] += 1
    total = re.search(r"\*\*(\d+) checks / (\d+) FAIL", part)
    if total is None:
        sys.exit(f"make_figure: no total in the pass {HEADING!r}")
    checks = sum(sum(c.values()) for c in channels.values())
    fails = sum(c["FAIL"] for c in channels.values())
    if checks != int(total.group(1)) or fails != int(total.group(2)):
        sys.exit(f"make_figure: {checks} checks and {fails} FAIL differ from the total {total.group(0)}")
    return list(channels.items())


def text(x, y, body, size, fill, weight="400"):
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" font-weight="{weight}" fill="{fill}">{body}</text>'


def summary(v):
    return ", ".join(f"{v[k]} {k}" for k in KEYS if v[k])


def draw(rows, theme, desc):
    c = THEMES[theme]
    unit = WIDTH / max(sum(v.values()) for _, v in rows)
    parts = [text(0, 28, TITLE, 20, c["text"], "600")]
    x = 0
    for key in KEYS:
        parts.append(f'<rect x="{x:g}" y="42" width="14" height="14" rx="4" fill="{c[key]}"/>')
        parts.append(text(x + 20, 54, key, 14, c["muted"]))
        x += 90
    y = 92
    for label, v in rows:
        parts.append(text(0, y, f"{label}: {summary(v)}", 15, c["text"]))
        x = 0
        for key in KEYS:
            if v[key]:
                parts.append(f'<rect x="{x:g}" y="{y + 8:g}" width="{v[key] * unit - GAP:g}" height="{BAR}" rx="4" fill="{c[key]}"/>')
                x += v[key] * unit
        y += 62
    height = y - 62 + 8 + BAR + 8
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height:g}" width="{WIDTH}" height="{height:g}" '
        f'role="img" aria-labelledby="t d" font-family="{FONT}">\n'
        f'<title id="t">{TITLE}</title>\n<desc id="d">{desc}</desc>\n' + "\n".join(parts) + "\n</svg>\n"
    )


def main():
    rows = count()
    desc = " ".join(f"{label}: {summary(v)}." for label, v in rows)
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        with open(os.path.join(OUT, f"checks-{theme}.svg"), "w", encoding="utf-8") as f:
            f.write(draw(rows, theme, desc))
    print(desc)


if __name__ == "__main__":
    main()
