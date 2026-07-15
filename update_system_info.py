#!/usr/bin/env python3
"""
Update SYSTEM.INFO in dark.svg and light.svg from system_info.yaml.

Usage:
  1. Edit system_info.yaml
  2. Run:  python3 update_system_info.py
  3. Open dark.svg / light.svg to preview

Requires: PyYAML  (pip install pyyaml)  — falls back to a tiny YAML subset parser.
"""
from __future__ import annotations

import re
import sys
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "system_info.yaml"
TARGETS = [ROOT / "dark.svg", ROOT / "light.svg"]

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
# Dot padding target: length of "Key: " + dots + " " + value ≈ this
DOT_WIDTH = 50


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


def pad_dots(key: str, value: str, width: int = DOT_WIDTH) -> str:
    """Return dots so 'Key: ... Value' aligns roughly."""
    label = f"{key}: "
    room = width - len(label) - len(value)
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
            dots = pad_dots(f"{left}.{right}", value)
            return [
                ("cc", ". "),
                ("key", left),
                ("cc", "."),
                ("key", right),
                ("cc", f": {dots} "),
                ("value", value),
            ]
        dots = pad_dots(key, value)
        # Match requested Uptime shape: key, bare ":", dots id, value id
        if dots_id or value_id:
            dots_seg: tuple = ("cc", f" {dots} ")
            if dots_id:
                dots_seg = ("cc", f" {dots} ", {"id": dots_id})
            value_seg: tuple = ("value", value if value else " ")
            if value_id:
                value_seg = ("value", value if value else " ", {"id": value_id})
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


def build_rows(cfg: dict) -> list:
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
        else:
            rows.append(render_segments("kv", key=key, value=value))

    for sec in cfg.get("sections") or []:
        # spacer before section (skip if previous row already empty)
        if not rows or rows[-1] != render_segments("empty"):
            rows.append(render_segments("empty"))
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
            if first:
                tspans.append(
                    f'<tspan x="{INFO_X}" y="{y}" class="{cls}"{extra}>{t}</tspan>'
                )
                first = False
            else:
                tspans.append(f'<tspan class="{cls}"{extra}>{t}</tspan>')
        out.append(
            f'<g clip-path="url(#lc{i})">'
            f'<text x="{INFO_X}" y="0" fill="{text_fill}">{"".join(tspans)}</text>'
            f"</g>"
        )
    return "".join(out)


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


def patch_svg(path: Path, rows: list[list[tuple[str, str]]]) -> None:
    svg = path.read_text(encoding="utf-8")
    n = len(rows)
    text_fill = detect_text_fill(svg)

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

    # 3) Cursor timing: after last line finishes typing
    cursor_begin = ANIM_BEGIN0 + (n - 1) * ANIM_STEP + ANIM_DUR
    svg4, n_cur = re.subn(
        r'(class="cursor-blink"[^>]*>\s*<animate[^>]*begin=")[^"]+(")',
        rf"\g<1>{cursor_begin:.2f}s\g<2>",
        svg3,
        count=1,
    )
    if n_cur == 0:
        # alternate attribute order
        svg4, n_cur = re.subn(
            r'(<animate attributeName="opacity"[^>]*begin=")[^"]+(")',
            rf"\g<1>{cursor_begin:.2f}s\g<2>",
            svg3,
            count=1,
        )

    path.write_text(svg4, encoding="utf-8")
    ET.parse(path)  # validate XML
    print(f"  updated {path.name}  ({n} rows, cursor @{cursor_begin:.2f}s)")


def main() -> int:
    if not CONFIG.exists():
        print(f"ERROR: missing {CONFIG.name}", file=sys.stderr)
        return 1

    print(f"Reading {CONFIG.name} ...")
    cfg = load_config(CONFIG)
    rows = build_rows(cfg)
    print(f"Built {len(rows)} SYSTEM.INFO rows for host={cfg.get('host')!r}")

    for target in TARGETS:
        if not target.exists():
            print(f"WARNING: skip missing {target.name}")
            continue
        print(f"Patching {target.name} ...")
        patch_svg(target, rows)

    # Fill live Uptime (age_data) via today.py after structural rewrite
    try:
        from today import daily_readme, resolve_start_date, svg_overwrite

        age = daily_readme(resolve_start_date())
        for target in TARGETS:
            if target.exists():
                svg_overwrite(str(target), age)
        print(f"  refreshed Uptime via today.py → {age}")
    except Exception as exc:
        print(f"Note: Uptime not refreshed ({exc}). Run: python3 today.py")

    print("Done. Open dark.svg / light.svg to preview.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
