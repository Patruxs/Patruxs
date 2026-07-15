from pathlib import Path
from html import escape

INPUT = "portrait.txt"
OUTPUT = "portrait_tspan.txt"

# Keep portrait vertically aligned with SYSTEM.INFO
# (update_system_info.py: INFO_START_Y=42, 25 rows * step 22 → last y=570)
START_X = 17
START_Y = 42.0
END_Y = 570.0
TEXT_LENGTH = 561

lines = [l.rstrip() for l in Path(INPUT).read_text(encoding="utf-8", errors="ignore").splitlines()]
if not lines:
    raise SystemExit("portrait.txt is empty")

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

Path(OUTPUT).write_text("\n".join(svg), encoding="utf-8")
print(f"Generated {len(svg)} tspans  y={START_Y:.2f}→{y - step:.2f} step={step:.3f}")
