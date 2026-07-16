#!/usr/bin/env python3
"""
Update SYSTEM.INFO in assets/dark.svg and assets/light.svg from system_info.yaml.

Usage (from repo root):
  1. Edit system_info.yaml
  2. Run:  python3 scripts/update_system_info.py
  3. Open assets/dark.svg / assets/light.svg to preview

Requires: PyYAML  (pip install pyyaml)  — falls back to a tiny YAML subset parser.
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

# Repo root is one level above scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

CONFIG = ROOT / "system_info.yaml"
TARGETS = [ROOT / "assets" / "dark.svg", ROOT / "assets" / "light.svg"]

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
LINE_WIDTH = 54
# Kept for callers that still pass DOT_WIDTH-style budgets
DOT_WIDTH = 50

# Placeholder stats (overwritten by today.py when ACCESS_TOKEN is set)
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


# Segment: (css_class, text, optional html attrs dict)
Seg = tuple  # (str, str) or (str, str, dict)


def render_segments(kind: str, **kwargs) -> list:
    """Return list of (css_class, text[, attrs]) for one row."""
    if kind == "head":
        host = kwargs["host"]
        dash = " -" + "—" * 42 + "-—-"
        return [("head", host), ("cc", dash)]
    if kind == "empty":
        return [("cc", ". ")]
    if kind == "section":
        title = kwargs["title"]
        dash = " -" + "—" * 44 + "-—-"
        return [("accent", f"- {title}"), ("cc", dash)]
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
                # Split ":" from live dots so today.py can rewrite dots without losing colon
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
            # recompute dots for possibly empty live value; today.py rewrites both
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
    """Match today.py justify_format dot padding for a value column."""
    just_len = max(0, length - len(str(value)))
    if just_len <= 2:
        return {0: "", 1: " ", 2: ". "}[just_len]
    return " " + ("." * just_len) + " "


def github_stats_rows(p: dict | None = None) -> list:
    """
    GitHub Stats block under Contact.
    IDs match today.py: repo_data, contrib_data, star_data, commit_data,
    follower_data, loc_data, loc_add, loc_del (+ *_dots where used).

    Column budgets match today.py justify_format lengths:
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
    return rows


def lang_rows(chunks: list[str] | None) -> list:
    """
    Single-line Lang, right-justified with filler dots:

        . Lang: .......... TypeScript · Java · HTML · CSS · Python +12
    """
    if not chunks:
        chunks = [" "]

    try:
        from today import LANG_FIRST_PREFIX, lang_dots_for
    except Exception:
        LANG_FIRST_PREFIX = 8  # len(". Lang: ")

        def lang_dots_for(value: str, prefix_len: int = 8) -> str:
            return "." * max(0, 54 - prefix_len - len(value))

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


def build_rows(cfg: dict, lang_chunks: list[str] | None = None) -> list:
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
            # Preserve age_data ids from the profile template
            rows.append(
                render_segments(
                    "kv",
                    key=key,
                    value=value,
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
            rows.extend(github_stats_rows())
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


def main() -> int:
    if not CONFIG.exists():
        print(f"ERROR: missing {CONFIG.name}", file=sys.stderr)
        return 1

    print(f"Reading {CONFIG.name} ...")
    cfg = load_config(CONFIG)

    # Fetch languages before build so multi-line Lang rows are created
    age = None
    lang_chunks = None
    svg_overwrite_fn = None
    try:
        from today import (
            USER_NAME,
            daily_readme,
            languages_getter,
            pack_lang_chunks,
            resolve_start_date,
            svg_overwrite as svg_overwrite_fn,
        )

        age = daily_readme(resolve_start_date())
        try:
            lang_names = languages_getter(USER_NAME)
            lang_chunks = pack_lang_chunks(lang_names)
            print(f"  Lang: {len(lang_names)} languages → {lang_chunks}")
        except Exception as lang_exc:
            print(f"  Note: languages not refreshed ({lang_exc})")
            lang_chunks = None
    except Exception as exc:
        print(f"Note: live helpers unavailable ({exc}). Run: python3 today.py")

    rows = build_rows(cfg, lang_chunks=lang_chunks)
    print(f"Built {len(rows)} SYSTEM.INFO rows for host={cfg.get('host')!r}")

    for target in TARGETS:
        if not target.exists():
            print(f"WARNING: skip missing {target.name}")
            continue
        print(f"Patching {target.name} ...")
        patch_svg(target, rows)

    # Fill live Uptime + Lang values (structure already has the right row count)
    if age is not None and svg_overwrite_fn is not None:
        try:
            for target in TARGETS:
                if target.exists():
                    svg_overwrite_fn(str(target), age, lang_data=lang_chunks)
            msg = f"  refreshed Uptime via today.py → {age}"
            if lang_chunks is not None:
                msg += f" | Lang → {lang_chunks}"
            print(msg)
        except Exception as exc:
            print(f"Note: live field fill failed ({exc})")

    print("Done. Open assets/dark.svg / assets/light.svg to preview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
