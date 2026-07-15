#!/usr/bin/env python3
"""Convert assets/portrait.txt into SVG <tspan> lines for VISUAL.MAP."""

from __future__ import annotations

from html import escape
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

INPUT = ROOT / "assets" / "portrait.txt"
OUTPUT = ROOT / "assets" / "portrait_tspan.txt"

# Keep portrait vertically aligned with SYSTEM.INFO
# (matched to SYSTEM.INFO y=42→438)
START_X = 17
START_Y = 42.0
END_Y = 438.0
TEXT_LENGTH = 561

lines = [l.rstrip() for l in INPUT.read_text(encoding="utf-8", errors="ignore").splitlines()]
if not lines:
    raise SystemExit(f"{INPUT} is empty")

n = len(lines)
step = (END_Y - START_Y) / (n - 1) if n > 1 else 0

y = START_Y
svg = []
for line in lines:
    svg.append(
        f'<tspan x="{START_X}" y="{y:.2f}" textLength="{TEXT_LENGTH}" '
        f'lengthAdjust="spacingAndGlyphs" xml:space="preserve">{escape(line)}</tspan>'
    )
    y += step

OUTPUT.write_text("\n".join(svg), encoding="utf-8")
print(f"Generated {len(svg)} tspans → {OUTPUT.relative_to(ROOT)}")
print(f"  y={START_Y:.2f}→{y - step:.2f} step={step:.3f}")
