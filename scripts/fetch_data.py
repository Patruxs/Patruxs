#!/usr/bin/env python3
"""Fetch GitHub data and update the profile assets."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from dateutil import relativedelta
from lxml import etree

# Repo root is one level above scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CONFIG = ROOT / "system_info.yaml"
TARGETS = [ROOT / "assets" / "dark.svg", ROOT / "assets" / "light.svg"]
CACHE_DIR = ROOT / "cache"
USER_NAME = os.environ.get("USER_NAME", "Patruxs")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
HEADERS = {"authorization": f"token {ACCESS_TOKEN}"} if ACCESS_TOKEN else {}

# Layout constants (must match banner geometry)
INFO_X = 617  # text x inside SYSTEM.INFO panel
CLIP_X = 595
CLIP_W = 583
INFO_START_Y = 42
INFO_STEP = 22
CLIP_START_Y = 26.0
ANIM_BEGIN0 = 0.75
ANIM_STEP = 0.115
ANIM_DUR = 0.38
# Total monospaced width of a simple ". Key: ... value" row (right-align values)
LINE_WIDTH = 60
RULE_WIDTH = 63

# Placeholder stats, overwritten when ACCESS_TOKEN is set.
GH_PLACEHOLDERS = {
    "repos": "0",
    "contrib": "0",
    "stars": "0",
    "commits": "0",
    "followers": "0",
    "loc": "0",
    "loc_add": "0",
    "loc_del": "0",
}

LANG_FIRST_PREFIX = 8
LANG_VALUE_BUDGET = LINE_WIDTH - LANG_FIRST_PREFIX
LANG_TOP_N = 4
LANG_MAX_N = 50
LANG_SEP = " · "
def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("system_info.yaml root must be a mapping")
        return data
    except ImportError:
        return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict:
    """Minimal parser for the shape of system_info.yaml if PyYAML is missing."""
    # Strip comments
    lines = []
    for line in text.splitlines():
        if "#" in line:
            # keep # inside quoted strings roughly
            in_q = False
            out = []
            for ch in line:
                if ch == '"':
                    in_q = not in_q
                if ch == "#" and not in_q:
                    break
                out.append(ch)
            line = "".join(out)
        lines.append(line.rstrip())

    data: dict = {"fields": [], "sections": []}
    host = None
    mode = None  # fields | section_fields | section_note
    cur_section: dict | None = None
    pending_key = None

    def unquote(s: str) -> str:
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            return s[1:-1]
        return s

    for line in lines:
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("host:"):
            host = unquote(stripped.split(":", 1)[1])
            mode = None
            continue
        if stripped == "fields:":
            mode = "fields"
            continue
        if stripped == "sections:":
            mode = "sections"
            continue
        if stripped.startswith("- title:"):
            cur_section = {"title": unquote(stripped.split(":", 1)[1]), "fields": []}
            data["sections"].append(cur_section)
            mode = "section_fields"
            continue
        if stripped.startswith("note:") and cur_section is not None and indent >= 2:
            cur_section["note"] = unquote(stripped.split(":", 1)[1])
            continue
        if stripped.startswith("kind:") and cur_section is not None and indent >= 2:
            cur_section["kind"] = unquote(stripped.split(":", 1)[1])
            continue
        if stripped == "fields:" and cur_section is not None:
            mode = "section_fields"
            continue
        if stripped.startswith("- key:"):
            pending_key = unquote(stripped.split(":", 1)[1])
            continue
        if stripped.startswith("value:") and pending_key is not None:
            val = unquote(stripped.split(":", 1)[1])
            item = {"key": pending_key, "value": val}
            if mode == "section_fields" and cur_section is not None:
                cur_section.setdefault("fields", []).append(item)
            else:
                data["fields"].append(item)
            pending_key = None
            continue

    if host is None:
        raise ValueError("host: is required in system_info.yaml")
    data["host"] = host
    return data


def pad_dots(key: str, value: str, width: int = LINE_WIDTH) -> str:
    """
    Return dots so a full row aligns to a fixed monospaced width:

        . {key}: {dots} {value}
    """
    # ". " + key + ": " + dots + " " + value
    fixed = 2 + len(key) + 2 + 1 + len(value)
    room = width - fixed
    return "." * max(3, room)


def pad_rule(label: str) -> str:
    """Fill a rule so its label and dashes occupy RULE_WIDTH columns."""
    return " " + "-" * max(1, RULE_WIDTH - len(label) - 1)


def render_segments(kind: str, **kwargs) -> list:
    """Return list of (css_class, text[, attrs]) for one row."""
    if kind == "head":
        host = kwargs["host"]
        return [("head", host), ("cc", pad_rule(host))]
    if kind == "empty":
        return [("cc", ". ")]
    if kind == "section":
        title = kwargs["title"]
        title_text = f"- {title}"
        return [("accent", title_text), ("cc", pad_rule(title_text))]
    if kind == "note":
        return [("cc", ". "), ("value", kwargs["text"])]
    if kind == "kv":
        key, value = kwargs["key"], kwargs["value"]
        dots_id = kwargs.get("dots_id")
        value_id = kwargs.get("value_id")
        if "." in key and (key.startswith("Core") or key.startswith("Grid")):
            left, right = key.split(".", 1)
            value_text = value if value else " "
            dots = pad_dots(f"{left}.{right}", value_text)
            dots_id = kwargs.get("dots_id")
            value_id = kwargs.get("value_id")
            value_seg: tuple = ("value", value_text)
            if value_id:
                value_seg = ("value", value_text, {"id": value_id})
            if dots_id:
                # Split ":" from live dots so fetch_data.py can rewrite dots without losing colon
                return [
                    ("cc", ". "),
                    ("key", left),
                    ("cc", "."),
                    ("key", right),
                    ("cc", ":"),
                    ("cc", f" {dots} ", {"id": dots_id}),
                    value_seg,
                ]
            return [
                ("cc", ". "),
                ("key", left),
                ("cc", "."),
                ("key", right),
                ("cc", f": {dots} "),
                value_seg,
            ]
        dots = pad_dots(key, value)
        # Uptime (and similar live fields): same alignment as other kv rows
        if dots_id or value_id:
            value_text = value if value else " "
            # recompute dots for possibly empty live value; fetch_data.py rewrites both
            dots = pad_dots(key, value_text)
            dots_seg: tuple = ("cc", f" {dots} ")
            if dots_id:
                dots_seg = ("cc", f" {dots} ", {"id": dots_id})
            value_seg: tuple = ("value", value_text)
            if value_id:
                value_seg = ("value", value_text, {"id": value_id})
            return [
                ("cc", ". "),
                ("key", key),
                ("cc", ":"),
                dots_seg,
                value_seg,
            ]
        return [
            ("cc", ". "),
            ("key", key),
            ("cc", f": {dots} "),
            ("value", value),
        ]
    raise ValueError(f"unknown kind {kind}")


def justify_dots(value: str, length: int) -> str:
    """Build dot padding for a value column."""
    just_len = max(0, length - len(str(value)))
    if just_len <= 2:
        return {0: "", 1: " ", 2: ". "}[just_len]
    return " " + ("." * just_len) + " "


def fit_row_to_width(row: list, dots_id: str, width: int = LINE_WIDTH) -> list:
    """Resize one dotted segment so the complete row reaches width."""
    target_index = next(
        index
        for index, segment in enumerate(row)
        if len(segment) == 3 and segment[2].get("id") == dots_id
    )
    fixed_width = sum(
        len(segment[1]) for index, segment in enumerate(row) if index != target_index
    )
    room = max(0, width - fixed_width)
    if room == 0:
        filler = ""
    elif room == 1:
        filler = " "
    elif room == 2:
        filler = ". "
    else:
        filler = " " + "." * (room - 2) + " "
    css_class, _, attrs = row[target_index]
    row[target_index] = (css_class, filler, attrs)
    return row


def github_stats_rows(p: dict | None = None) -> list:
    """
    GitHub Stats block under Contact.
    IDs match fetch_data.py: repo_data, contrib_data, star_data, commit_data,
    follower_data, loc_data, loc_add, loc_del (+ *_dots where used).

    Column budgets:
      repos:6  stars:14  commits:22  followers:10  loc:9  loc_del:7
    """
    p = {**GH_PLACEHOLDERS, **(p or {})}
    rows = []
    rows.append(render_segments("section", title="GitHub Stats"))

    # . Repos: .... N {Contributed: M} | Stars: ........... S
    rows.append(
        [
            ("cc", ". "),
            ("key", "Repos"),
            ("cc", ":"),
            ("cc", justify_dots(p["repos"], 6), {"id": "repo_data_dots"}),
            ("value", p["repos"], {"id": "repo_data"}),
            ("cc", " {"),
            ("key", "Contributed"),
            ("cc", ": "),
            ("value", p["contrib"], {"id": "contrib_data"}),
            ("cc", "} | "),
            ("key", "Stars"),
            ("cc", ":"),
            ("cc", justify_dots(p["stars"], 14), {"id": "star_data_dots"}),
            ("value", p["stars"], {"id": "star_data"}),
        ]
    )
    fit_row_to_width(rows[-1], "star_data_dots")

    # . Commits: ................. N | Followers: ....... M
    rows.append(
        [
            ("cc", ". "),
            ("key", "Commits"),
            ("cc", ":"),
            ("cc", justify_dots(p["commits"], 22), {"id": "commit_data_dots"}),
            ("value", p["commits"], {"id": "commit_data"}),
            ("cc", " | "),
            ("key", "Followers"),
            ("cc", ":"),
            ("cc", justify_dots(p["followers"], 10), {"id": "follower_data_dots"}),
            ("value", p["followers"], {"id": "follower_data"}),
        ]
    )
    fit_row_to_width(rows[-1], "follower_data_dots")

    # . Lines of Code on GitHub: . N ( A++, D-- )
    rows.append(
        [
            ("cc", ". "),
            ("key", "Lines of Code on GitHub"),
            ("cc", ":"),
            ("cc", justify_dots(p["loc"], 9), {"id": "loc_data_dots"}),
            ("value", p["loc"], {"id": "loc_data"}),
            ("cc", " ( "),
            ("addColor", p["loc_add"], {"id": "loc_add"}),
            ("addColor", "++"),
            ("cc", ", "),
            ("", justify_dots(p["loc_del"], 7) or " ", {"id": "loc_del_dots"}),
            ("delColor", p["loc_del"], {"id": "loc_del"}),
            ("delColor", "--"),
            ("cc", " )"),
        ]
    )
    fit_row_to_width(rows[-1], "loc_del_dots")
    return rows


def lang_rows(chunks: list[str] | None) -> list:
    """
    Single-line Lang, right-justified with filler dots:

        . Lang: .......... TypeScript · Java · HTML · CSS · Python +12
    """
    if not chunks:
        chunks = [" "]

    text = chunks[0]
    return [
        [
            ("cc", ". "),
            ("key", "Lang"),
            ("cc", ": "),
            ("cc", lang_dots_for(text, LANG_FIRST_PREFIX), {"id": "lang_data_dots"}),
            ("value", text, {"id": "lang_data"}),
        ]
    ]


def build_rows(
    cfg: dict,
    lang_chunks: list[str] | None = None,
    github_stats: dict | None = None,
    uptime: str | None = None,
) -> list:
    rows: list = []
    rows.append(render_segments("head", host=cfg["host"]))

    for item in cfg.get("fields") or []:
        key = (item.get("key") or "").strip()
        value = item.get("value")
        if value is None:
            value = ""
        value = str(value)
        if not key and not value:
            rows.append(render_segments("empty"))
        elif key == "Uptime":
            rows.append(
                render_segments(
                    "kv",
                    key=key,
                    value=uptime if uptime is not None else value,
                    dots_id="age_data_dots",
                    value_id="age_data",
                )
            )
        elif key in ("Lang", "Core.Lang"):
            # Multi-line live languages (ids: lang_data, lang_data_1, …)
            # Accept both "Lang" (current) and legacy "Core.Lang"
            if lang_chunks:
                rows.extend(lang_rows(lang_chunks))
            else:
                rows.extend(lang_rows([value or " "]))
        else:
            rows.append(render_segments("kv", key=key, value=value))

    for sec in cfg.get("sections") or []:
        # spacer before section (skip if previous row already empty)
        if not rows or rows[-1] != render_segments("empty"):
            rows.append(render_segments("empty"))

        kind = (sec.get("kind") or "").strip()
        if kind == "github_stats" or sec.get("title") == "GitHub Stats":
            rows.extend(github_stats_rows(github_stats))
            continue

        rows.append(render_segments("section", title=sec["title"]))
        for item in sec.get("fields") or []:
            rows.append(
                render_segments(
                    "kv",
                    key=(item.get("key") or "").strip(),
                    value=str(item.get("value") or ""),
                )
            )
        note = sec.get("note")
        if note:
            rows.append(render_segments("note", text=str(note)))

    return rows


def build_clippaths(n: int) -> str:
    parts = []
    for i in range(n):
        y = CLIP_START_Y + i * INFO_STEP
        begin = ANIM_BEGIN0 + i * ANIM_STEP
        parts.append(
            f'<clipPath id="lc{i}">'
            f'<rect x="{CLIP_X}" y="{y:.2f}" width="0" height="24">'
            f'<animate attributeName="width" from="0" to="{CLIP_W}" '
            f'dur="{ANIM_DUR}s" begin="{begin:.2f}s" fill="freeze"/>'
            f"</rect></clipPath>"
        )
    return "".join(parts)


def _attrs_str(attrs: dict | None) -> str:
    if not attrs:
        return ""
    return "".join(f' {k}="{escape(str(v), quote=True)}"' for k, v in attrs.items())


def build_info_groups(rows: list, text_fill: str) -> str:
    out = []
    for i, segs in enumerate(rows):
        y = INFO_START_Y + i * INFO_STEP
        tspans = []
        first = True
        for seg in segs:
            cls, text = seg[0], seg[1]
            attrs = seg[2] if len(seg) > 2 else None
            t = escape(text)
            extra = _attrs_str(attrs)
            class_attr = f' class="{cls}"' if cls else ""
            if first:
                tspans.append(
                    f'<tspan x="{INFO_X}" y="{y}"{class_attr}{extra}>{t}</tspan>'
                )
                first = False
            else:
                tspans.append(f"<tspan{class_attr}{extra}>{t}</tspan>")
        out.append(
            f'<g clip-path="url(#lc{i})">'
            f'<text x="{INFO_X}" y="0" fill="{text_fill}">{"".join(tspans)}</text>'
            f"</g>"
        )
    return "".join(out)


def ensure_stats_styles(svg: str, path: Path) -> str:
    """Ensure addColor / delColor CSS exists for LOC ++/--."""
    if "addColor" in svg and "delColor" in svg:
        return svg
    is_dark = "dark" in path.name
    add_fill = "#4ADE80" if is_dark else "#16A34A"
    del_fill = "#F87171" if is_dark else "#DC2626"
    block = (
        f"    .addColor {{ font-family: 'Courier New', Consolas, monospace; "
        f"font-size: 15px; fill: {add_fill}; font-weight: bold; }}\n"
        f"    .delColor {{ font-family: 'Courier New', Consolas, monospace; "
        f"font-size: 15px; fill: {del_fill}; font-weight: bold; }}\n"
    )
    svg2, n = re.subn(
        r"(  </style>)",
        block + r"\1",
        svg,
        count=1,
    )
    return svg2 if n else svg


def strip_panel_borders(svg: str) -> str:
    """
    Remove VISUAL.MAP / SYSTEM.INFO glass cards and outer frame stroke.
    Called on every regenerate so borders do not come back.
    """
    # Glass panel backgrounds (with or without stroke)
    svg, _ = re.subn(
        r'\n  <rect x="14" y="10" width="567" height="\d+" rx="14"[^/]*/>'
        r'\n  <rect x="599" y="10" width="567" height="\d+" rx="14"[^/]*/>',
        '',
        svg,
        count=1,
    )
    svg, _ = re.subn(
        r'\n  <rect x="14" y="10" width="567" height="\d+" rx="14"[^/]*/>',
        '',
        svg,
        count=1,
    )
    svg, _ = re.subn(
        r'\n  <rect x="599" y="10" width="567" height="\d+" rx="14"[^/]*/>',
        '',
        svg,
        count=1,
    )
    # Outer animated frame (not the titlebar bar height=34)
    svg, _ = re.subn(
        r'\n?<rect x="3" y="3" width="1174" height="604"[^>]*>\s*'
        r'(?:<animate[^/]*/>\s*)?</rect>\s*',
        '\n',
        svg,
        count=1,
        flags=re.DOTALL,
    )
    svg = re.sub(r' stroke="url\(#borderGrad\)" stroke-width="[^"]*"', '', svg)
    svg, _ = re.subn(
        r'\n  <linearGradient id="borderGrad"[^>]*>.*?</linearGradient>',
        '',
        svg,
        count=1,
        flags=re.DOTALL,
    )
    return svg


# SYSTEM.INFO + ASCII sit under <g transform="translate(0, 38)"> (titlebar clearance).
CONTENT_Y_OFFSET = 38
# Room below last baseline for font descent + rounded SVG corner.
BOTTOM_PAD = 28


def expand_canvas_for_rows(svg: str, n: int) -> str:
    """Size banner/panel height to fit SYSTEM.INFO content (no extra white space)."""
    last_y = INFO_START_Y + (n - 1) * INFO_STEP
    # local y is inside the translated group → screen y = local + CONTENT_Y_OFFSET
    needed_height = last_y + CONTENT_Y_OFFSET + BOTTOM_PAD
    panel_h = needed_height - 30  # panels start at y=10, leave ~20 bottom
    ascii_h = panel_h - 12
    reveal_h = needed_height - 10
    scan_to = needed_height + 70

    def repl_svg_open(m: re.Match) -> str:
        tag = m.group(0)
        tag = re.sub(r'\bheight="\d+"', f'height="{needed_height}"', tag)
        tag = re.sub(
            r'viewBox="0 0 (\d+) \d+"',
            lambda mm: f'viewBox="0 0 {mm.group(1)} {needed_height}"',
            tag,
        )
        # fix accidental escaped quotes from older buggy runs
        tag = tag.replace('\\"', '"')
        return tag

    # Repair any prior bad height="N\" attributes first
    svg = svg.replace('\\"', '"')

    svg = re.sub(r"<svg\b[^>]*>", repl_svg_open, svg, count=1)
    # full-bleed background rects
    svg = re.sub(
        r'(<rect width="1180" height=")\d+(" rx="18")',
        rf"\g<1>{needed_height}\2",
        svg,
    )
    # left/right glass panels (never inject backslashes)
    svg = re.sub(
        r'(<rect x="14" y="10" width="567" height=")\d+(")',
        rf"\g<1>{panel_h}\2",
        svg,
    )
    svg = re.sub(
        r'(<rect x="599" y="10" width="567" height=")\d+(")',
        rf"\g<1>{panel_h}\2",
        svg,
    )
    # ASCII clip rect inside left panel (clipPath + any loose rect)
    svg = re.sub(
        r'(<rect x="15" y="26" width="565" height=")\d+(")',
        rf"\g<1>{ascii_h}\2",
        svg,
    )
    # reveal mask bounds + curtain target height
    svg = re.sub(
        r'(<mask id="revealMask"[^>]*height=")\d+(")',
        rf"\g<1>{needed_height}\2",
        svg,
        count=1,
    )
    svg = re.sub(
        r'(attributeName="height" from="0" to=")\d+(")',
        rf"\g<1>{reveal_h}\2",
        svg,
        count=1,
    )
    # horizontal scan beam travel end (off bottom of canvas)
    svg = re.sub(
        r'(animateTransform[^>]*to="0 )\d+(")',
        rf"\g<1>{scan_to}\2",
        svg,
        count=1,
    )
    return svg


def strip_cursor(svg: str) -> str:
    """Remove the blinking terminal cursor (and its CSS) if present."""
    svg = re.sub(
        r'\n  <rect x="619" y="\d+" width="9" height="16" class="cursor-blink"[^>]*>\s*'
        r'(?:<animate[^/]*/>\s*)?</rect>',
        '',
        svg,
        count=1,
        flags=re.DOTALL,
    )
    svg = re.sub(r'\n    \.cursor-blink \{[^}]+\}\n', '\n', svg, count=1)
    return svg


def detect_text_fill(svg: str) -> str:
    """Pick fill color used on SYSTEM.INFO text (dark vs light)."""
    m = re.search(
        r'<g clip-path="url\(#lc0\)"><text x="[^"]+" y="0" fill="([^"]+)"',
        svg,
    )
    if m:
        return m.group(1)
    # fallbacks
    if 'stop-color="#050816"' in svg or "#0B1120" in svg[:2000]:
        return "#dbeafe"
    return "#1E293B"


def patch_svg(path: Path, rows: list) -> None:
    svg = path.read_text(encoding="utf-8")
    n = len(rows)
    text_fill = detect_text_fill(svg)
    svg = ensure_stats_styles(svg, path)
    svg = strip_panel_borders(svg)
    svg = expand_canvas_for_rows(svg, n)

    # 1) Replace all lc* clipPaths
    clips = build_clippaths(n)
    svg2, n_clips = re.subn(
        r'(?:<clipPath id="lc\d+">.*?</clipPath>\s*)+',
        clips + "\n  ",
        svg,
        count=1,
        flags=re.DOTALL,
    )
    if n_clips == 0:
        raise RuntimeError(f"{path.name}: could not find lc* clipPaths to replace")

    # 2) Replace all SYSTEM.INFO content groups (lc0..lcN)
    groups = build_info_groups(rows, text_fill)
    svg3, n_groups = re.subn(
        r'(?:<g clip-path="url\(#lc\d+\)">.*?</g>\s*)+',
        groups + "\n\n  ",
        svg2,
        count=1,
        flags=re.DOTALL,
    )
    if n_groups == 0:
        raise RuntimeError(f"{path.name}: could not find SYSTEM.INFO <g clip-path=lc*> blocks")

    # 3) Drop blinking cursor (not wanted on profile banner)
    svg4 = strip_cursor(svg3)

    path.write_text(svg4, encoding="utf-8")
    ET.parse(path)  # validate XML
    last_y = INFO_START_Y + (n - 1) * INFO_STEP
    h = last_y + CONTENT_Y_OFFSET + BOTTOM_PAD
    print(f"  updated {path.name}  ({n} rows, height={h}, no cursor)")


def daily_readme(birthday):
    """
    Returns the length of time since I was born
    e.g. 'XX years, XX months, XX days'
    """
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years, 'year' + format_plural(diff.years),
        diff.months, 'month' + format_plural(diff.months),
        diff.days, 'day' + format_plural(diff.days),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '')


def format_plural(unit):
    """
    Returns a properly formatted number
    e.g.
    'day' + format_plural(diff.days) == 5
    >>> '5 days'
    'day' + format_plural(diff.days) == 1
    >>> '1 day'
    """
    return 's' if unit != 1 else ''


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS)
    if request.status_code == 200:
        return request
    raise Exception(func_name, ' has failed with a', request.status_code, request.text)


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    """
    Uses GitHub's GraphQL v4 API to return my total repository, star, or lines of code count.
    """
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers {
                                totalCount
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(graph_repos_stars.__name__, query, variables)
    repositories = request.json()["data"]["user"]["repositories"]
    if count_type == "repos":
        return repositories["totalCount"]
    if count_type == "stars":
        total = stars_counter(repositories["edges"])
        if repositories["pageInfo"]["hasNextPage"]:
            total += graph_repos_stars(
                count_type,
                owner_affiliation,
                repositories["pageInfo"]["endCursor"],
            )
        return total
    raise ValueError(f"Unknown count type: {count_type}")


def recursive_loc(owner, repo_name, data, cache_comment, addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    """
    Uses GitHub's GraphQL v4 API and cursor pagination to fetch 100 commits from a repository at a time
    """
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit {
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo {
                                endCursor
                                hasNextPage
                            }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables':variables}, headers=HEADERS) # I cannot use simple_request(), because I want to save the file before raising Exception
    if request.status_code == 200:
        if request.json()['data']['repository']['defaultBranchRef'] != None: # Only count commits if repo isn't empty
            return loc_counter_one_repo(owner, repo_name, data, cache_comment, request.json()['data']['repository']['defaultBranchRef']['target']['history'], addition_total, deletion_total, my_commits)
        else: return 0
    force_close_file(data, cache_comment) # saves what is currently in the file before this program crashes
    if request.status_code == 403:
        raise Exception('Too many requests in a short amount of time!\nYou\'ve hit the non-documented anti-abuse limit!')
    raise Exception('recursive_loc() has failed with a', request.status_code, request.text)


def loc_counter_one_repo(owner, repo_name, data, cache_comment, history, addition_total, deletion_total, my_commits):
    """
    Recursively call recursive_loc (since GraphQL can only search 100 commits at a time)
    only adds the LOC value of commits authored by me
    """
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']

    if history['edges'] == [] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    else: return recursive_loc(owner, repo_name, data, cache_comment, addition_total, deletion_total, my_commits, history['pageInfo']['endCursor'])


def loc_query(
    owner_affiliation,
    comment_size=0,
    force_cache=False,
    cursor=None,
    edges=None,
):
    """
    Uses GitHub's GraphQL v4 API to query all the repositories I have access to (with respect to owner_affiliation)
    Queries 60 repos at a time, because larger queries give a 502 timeout error and smaller queries send too many
    requests and also give a 502 error.
    Returns the total number of lines of code in all repositories
    """
    if edges is None:
        edges = []
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
            edges {
                node {
                    ... on Repository {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    request = simple_request(loc_query.__name__, query, variables)
    if request.json()['data']['user']['repositories']['pageInfo']['hasNextPage']:   # If repository data has another page
        edges += request.json()['data']['user']['repositories']['edges']            # Add on to the LoC count
        return loc_query(owner_affiliation, comment_size, force_cache, request.json()['data']['user']['repositories']['pageInfo']['endCursor'], edges)
    else:
        return cache_builder(edges + request.json()['data']['user']['repositories']['edges'], comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count
    """
    cached = True # Assume all repositories are cached
    os.makedirs(CACHE_DIR, exist_ok=True)
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt') # Create a unique filename for each user
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError: # If the cache file doesn't exist, create it
        data = []
        if comment_size > 0:
            for _ in range(comment_size): data.append('This line is a comment block. Write whatever you want here.\n')
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data)-comment_size != len(edges) or force_cache: # If the number of repos has changed, or force_cache is True
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if repo_hash == hashlib.sha256(edges[index]['node']['nameWithOwner'].encode('utf-8')).hexdigest():
            try:
                if int(commit_count) != edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']:
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]['node']['nameWithOwner'].split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = repo_hash + ' ' + str(edges[index]['node']['defaultBranchRef']['target']['history']['totalCount']) + ' ' + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
            except TypeError: # If the repo is empty
                data[index] = repo_hash + ' 0 0 0 0\n'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    """
    Wipes the cache file
    This is called when the number of repositories changes or when the file is first created
    """
    with open(filename, 'r') as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size] # only save the comment
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(node['node']['nameWithOwner'].encode('utf-8')).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data, cache_comment):
    """
    Forces the file to close, preserving whatever data was written to it
    This is needed because if this function is called, the program would've crashed before the file is properly saved and closed
    """
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt')
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print('There was an error while writing to the cache file. The file,', filename, 'has had the partial data saved and closed.')


def stars_counter(data):
    """
    Count total stars in repositories owned by me
    """
    total_stars = 0
    for node in data: total_stars += node['node']['stargazers']['totalCount']
    return total_stars


def languages_getter(username):
    """
    Aggregate languages across owned non-fork repos (by total bytes of code).
    Returns a size-descending list of language names (all of them, up to LANG_MAX_N).
    Uses GraphQL when ACCESS_TOKEN is set; else public REST.
    """
    totals = {}

    if ACCESS_TOKEN:
        cursor = None
        while True:
            query = '''
            query ($login: String!, $cursor: String) {
              user(login: $login) {
                repositories(
                  first: 50
                  after: $cursor
                  ownerAffiliations: [OWNER]
                  isFork: false
                  orderBy: {field: UPDATED_AT, direction: DESC}
                ) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    languages(first: 100, orderBy: {field: SIZE, direction: DESC}) {
                      edges { size node { name } }
                    }
                  }
                }
              }
            }'''
            variables = {'login': username, 'cursor': cursor}
            request = simple_request(languages_getter.__name__, query, variables)
            data = request.json()['data']['user']['repositories']
            for node in data['nodes']:
                langs = (node.get('languages') or {}).get('edges') or []
                for edge in langs:
                    name = edge['node']['name']
                    totals[name] = totals.get(name, 0) + int(edge['size'])
            if not data['pageInfo']['hasNextPage']:
                break
            cursor = data['pageInfo']['endCursor']
    else:
        # Public REST fallback (no token)
        page = 1
        headers = HEADERS or {'Accept': 'application/vnd.github+json'}
        while True:
            resp = requests.get(
                f'https://api.github.com/users/{username}/repos',
                params={'per_page': 100, 'page': page, 'type': 'owner', 'sort': 'updated'},
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                raise Exception(
                    'languages_getter REST list failed',
                    resp.status_code,
                    resp.text[:200],
                )
            repos = resp.json()
            if not repos:
                break
            for repo in repos:
                if repo.get('fork'):
                    continue
                lr = requests.get(
                    repo['languages_url'],
                    headers=headers,
                    timeout=30,
                )
                if lr.status_code != 200:
                    continue
                for name, size in lr.json().items():
                    totals[name] = totals.get(name, 0) + int(size)
            if len(repos) < 100:
                break
            page += 1

    if not totals:
        return []

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _size in ranked[:LANG_MAX_N]]


def pack_lang_chunks(names):
    """
    Top LANG_TOP_N languages on one line, plus " +N" for the rest.

        . Lang: .......... TypeScript · Java · HTML · CSS +12

    Returns a one-element list for ``lang_rows``.
    """
    if not names:
        return ["N/A"]

    shown = names[:LANG_TOP_N]
    extra = max(0, len(names) - len(shown))
    text = LANG_SEP.join(shown)

    if extra > 0:
        suffix = f" +{extra}"
        while shown and len(text) + len(suffix) > LANG_VALUE_BUDGET:
            shown.pop()
            extra = len(names) - len(shown)
            suffix = f" +{extra}"
            text = LANG_SEP.join(shown)
        text = (text + suffix) if shown else f"+{extra}"
    else:
        while len(text) > LANG_VALUE_BUDGET and len(shown) > 1:
            shown.pop()
            text = LANG_SEP.join(shown)
        if len(text) > LANG_VALUE_BUDGET:
            text = text[:LANG_VALUE_BUDGET]

    return [text]


def lang_dots_for(value: str, prefix_len: int = LANG_FIRST_PREFIX) -> str:
    """
    Filler between ': ' and the value.

    Prefer a visible run of dots with a trailing space when there is room:
      . Lang: .......... TypeScript · Java · …
    """
    room = LINE_WIDTH - prefix_len - len(value)
    if room <= 0:
        return ""
    if room == 1:
        return " "
    # dots + trailing space (e.g. room=11 → ".......... ")
    return ("." * (room - 1)) + " "


def commit_counter(comment_size):
    """
    Counts up my total commits, using the cache file created by cache_builder.
    """
    total_commits = 0
    filename = os.path.join(CACHE_DIR, hashlib.sha256(USER_NAME.encode('utf-8')).hexdigest() + '.txt') # Use the same filename as cache_builder
    with open(filename, 'r') as f:
        data = f.readlines()
    cache_comment = data[:comment_size] # save the comment block
    data = data[comment_size:] # remove those lines
    for line in data:
        total_commits += int(line.split()[2])
    return total_commits


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """
    query = '''
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }'''
    variables = {'login': username}
    request = simple_request(user_getter.__name__, query, variables)
    return {'id': request.json()['data']['user']['id']}, request.json()['data']['user']['createdAt']

def follower_getter(username):
    """
    Returns the number of followers of the user
    """
    query = '''
    query($login: String!){
        user(login: $login) {
            followers {
                totalCount
            }
        }
    }'''
    request = simple_request(follower_getter.__name__, query, {'login': username})
    return int(request.json()['data']['user']['followers']['totalCount'])


def resolve_start_date():
    """
    Uptime start date:
      1) BIRTHDAY env (YYYY-MM-DD)
      2) GitHub account created_at (public REST, no token needed)
      3) Fallback 2002-07-05 (original template default)
    """
    birthday_env = os.environ.get('BIRTHDAY', '').strip()
    if birthday_env:
        return datetime.datetime.strptime(birthday_env, '%Y-%m-%d')

    try:
        resp = requests.get(
            f'https://api.github.com/users/{USER_NAME}',
            headers=HEADERS or None,
            timeout=20,
        )
        if resp.status_code == 200:
            created = resp.json().get('created_at')  # e.g. 2021-09-07T05:41:30Z
            if created:
                return datetime.datetime.fromisoformat(
                    created.replace('Z', '+00:00')
                ).replace(tzinfo=None)
    except Exception as exc:
        print(f'Warning: could not fetch account created_at ({exc})')

    return datetime.datetime(2002, 7, 5)



def fetch_projects() -> None:
    """Merge projects.json with live GitHub repository data when it exists."""
    source = ROOT / "projects.json"
    if not source.exists():
        return

    projects = json.loads(source.read_text(encoding="utf-8"))
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN') or ACCESS_TOKEN}",
        "User-Agent": "projects-panel",
    }
    for project in projects:
        repo = project.get("repo", "").strip()
        repo = re.sub(r"^https?://github\.com/", "", repo).rstrip("/")
        project["repo"] = repo
        try:
            response = requests.get(
                f"https://api.github.com/repos/{repo}", headers=headers, timeout=15
            )
            response.raise_for_status()
            info = response.json()
            project["stars"] = info.get("stargazers_count", 0)
            project["pushed_at"] = info.get("pushed_at")
            project["description"] = (
                project.get("description") or info.get("description") or ""
            )

            response = requests.get(
                f"https://api.github.com/repos/{repo}/languages",
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            project["languages"] = response.json()
        except requests.RequestException as exc:
            print(f"Warning: could not fetch {repo}: {exc}", file=sys.stderr)
            project.setdefault("stars", 0)
            project.setdefault("languages", {})
            project.setdefault("pushed_at", None)

    output = ROOT / "merged.json"
    output.write_text(json.dumps(projects), encoding="utf-8")
    print(f"Merged {len(projects)} projects into {output.name}")


def fetch_github_stats() -> dict:
    """Fetch private stats that require a GitHub access token."""
    if not ACCESS_TOKEN:
        print("ACCESS_TOKEN is not set, skipping private GitHub stats")
        return {}

    user_data, _ = user_getter(USER_NAME)
    globals()["OWNER_ID"] = user_data
    total_loc = loc_query(
        ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"], comment_size=7
    )
    return {
        "commits": f"{commit_counter(7):,}",
        "stars": f"{graph_repos_stars('stars', ['OWNER']):,}",
        "repos": f"{graph_repos_stars('repos', ['OWNER']):,}",
        "contrib": f"{graph_repos_stars(
            "repos", ["OWNER", "COLLABORATOR", "ORGANIZATION_MEMBER"]
        ):,}",
        "followers": f"{follower_getter(USER_NAME):,}",
        "loc_add": f"{total_loc[0]:,}",
        "loc_del": f"{total_loc[1]:,}",
        "loc": f"{total_loc[2]:,}",
    }


def read_svg_stats(path: Path) -> dict:
    """Keep the last fetched stats when no access token is available."""
    ids = {
        "repos": "repo_data",
        "contrib": "contrib_data",
        "stars": "star_data",
        "commits": "commit_data",
        "followers": "follower_data",
        "loc": "loc_data",
        "loc_add": "loc_add",
        "loc_del": "loc_del",
    }
    root = etree.parse(str(path)).getroot()
    elements = {element.get("id"): element.text for element in root.iter()}
    return {
        key: elements.get(element_id) or GH_PLACEHOLDERS[key]
        for key, element_id in ids.items()
    }


def read_svg_value(path: Path, element_id: str) -> str | None:
    root = etree.parse(str(path)).getroot()
    return next(
        (
            element.text
            for element in root.iter()
            if element.get("id") == element_id
        ),
        None,
    )


def update_banners() -> None:
    """Rebuild SYSTEM.INFO and fill its live values."""
    age = daily_readme(resolve_start_date())
    existing_target = next((target for target in TARGETS if target.exists()), None)
    existing_stats = (
        read_svg_stats(existing_target) if existing_target else GH_PLACEHOLDERS
    )
    try:
        languages = pack_lang_chunks(languages_getter(USER_NAME))
    except Exception as exc:
        print(f"Warning: could not refresh languages: {exc}", file=sys.stderr)
        previous_language = (
            read_svg_value(existing_target, "lang_data")
            if existing_target
            else None
        )
        languages = [previous_language] if previous_language else None

    stats = fetch_github_stats() or existing_stats
    rows = build_rows(
        load_config(CONFIG),
        lang_chunks=languages,
        github_stats=stats,
        uptime=age,
    )

    for target in TARGETS:
        if not target.exists():
            print(f"Warning: skip missing {target}")
            continue
        patch_svg(target, rows)
        print(f"Updated {target.name}")


def main() -> int:
    update_banners()
    fetch_projects()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
