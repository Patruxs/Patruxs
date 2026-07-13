#!/usr/bin/env python3
"""
Portrait photo -> Sushmita-style ASCII art (dark terminal / GitHub banner).

Reference profile style (Sushmitadasari):
  - ~92 columns x ~53 rows
  - Glyph ramp: light bg  . : -   mid  = + *   dark face/hair  % # @
  - Tight face + upper-body crop
  - Dark features -> dense chars (glowing text on dark terminal)
  - White studio bg -> dots / colons / dashes
  - Pure ASCII, no emoji
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageFilter, ImageOps

DEFAULT_COLS = 92
DEFAULT_ROWS = 53

CHAR_ASPECT = 0.50

RAMP_SUSHMITA = " .:-+=*#%@"
RAMP_LONG = " .'`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def _to_luma(img: Image.Image) -> np.ndarray:
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _auto_subject_bbox(
    luma: np.ndarray,
    bg_percentile: float = 90.0,
    pad_frac: float = 0.07,
) -> tuple[int, int, int, int]:

    h, w = luma.shape
    thr = min(float(np.percentile(luma, bg_percentile)), 0.90)
    mask = luma < thr

    m = mask.astype(np.uint8)
    padded = np.pad(m, 1, mode="edge")
    acc = np.zeros_like(m, dtype=np.uint8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            acc |= padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    m = acc
    padded = np.pad(m, 1, mode="constant")
    nsum = np.zeros((h, w), dtype=np.uint8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nsum += padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
    m = nsum >= 3

    ys, xs = np.where(m)
    if len(xs) < 50:
        side_w, side_h = int(w * 0.72), int(h * 0.80)
        left = max(0, (w - side_w) // 2)
        top = max(0, int(h * 0.04))
        return left, top, min(w, left + side_w), min(h, top + side_h)

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    pw = int((x1 - x0) * pad_frac)
    ph = int((y1 - y0) * pad_frac)
    y0 = max(0, y0 - int(ph * 1.5))
    y1 = min(h, y1 + ph)
    x0 = max(0, x0 - pw)
    x1 = min(w, x1 + pw)
    return x0, y0, x1, y1


def _crop_to_char_aspect(
    img: Image.Image,
    cols: int,
    rows: int,
    char_aspect: float,
    bbox: tuple[int, int, int, int] | None,
) -> Image.Image:
 
    if bbox is not None:
        img = img.crop(bbox)

    w, h = img.size
    target_ar = (cols * char_aspect) / float(rows)
    cur_ar = w / float(h)

    if cur_ar > target_ar + 1e-6:
        new_w = max(1, int(round(h * target_ar)))
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif cur_ar < target_ar - 1e-6:
        new_h = max(1, int(round(w / target_ar)))
        excess = h - new_h
        top = int(max(0, excess) * 0.28)
        img = img.crop((0, top, w, top + new_h))
    return img


def _percentile_stretch(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    p_lo, p_hi = np.percentile(arr, (lo, hi))
    if p_hi <= p_lo + 1e-6:
        return np.clip(arr, 0.0, 1.0)
    return np.clip((arr - p_lo) / (p_hi - p_lo), 0.0, 1.0)


def _gamma(arr: np.ndarray, g: float) -> np.ndarray:
    return np.power(np.clip(arr, 0.0, 1.0), max(g, 1e-6))


def _unsharp(arr: np.ndarray, amount: float = 0.55) -> np.ndarray
    if amount <= 0:
        return arr
    p = np.pad(arr, 1, mode="edge")
    blur = (
        p[0:-2, 0:-2] + p[0:-2, 1:-1] + p[0:-2, 2:]
        + p[1:-1, 0:-2] + p[1:-1, 1:-1] + p[1:-1, 2:]
        + p[2:, 0:-2] + p[2:, 1:-1] + p[2:, 2:]
    ) / 9.0
    return np.clip(arr + amount * (arr - blur), 0.0, 1.0)


def _subject_aware_tone(luma: np.ndarray, bg_cut: float = 0.88) -> np.ndarray:
   
    bg = luma >= bg_cut
    sub = ~bg
    out = np.ones_like(luma)  
    if not np.any(sub):
        return _percentile_stretch(luma, 2, 98)

    s = luma[sub]
    lo, hi = np.percentile(s, (4.0, 96.0))
    if hi <= lo + 1e-6:
        mapped = np.clip(s, 0.0, 1.0)
    else:
        mapped = np.clip((s - lo) / (hi - lo), 0.0, 1.0)

    out[sub] = mapped
    band = (luma >= bg_cut - 0.08) & (luma < bg_cut)
    if np.any(band):
        t = (luma[band] - (bg_cut - 0.08)) / 0.08
        out[band] = out[band] * (1.0 - t) + 1.0 * t
    out[bg] = 1.0
    return out


def _floyd_steinberg(darkness: np.ndarray, n_levels: int) -> np.ndarray:
    h, w = darkness.shape
    work = darkness.astype(np.float64).copy()
    levels = n_levels - 1
    out = np.zeros((h, w), dtype=np.int32)
    for y in range(h):
        for x in range(w):
            old = work[y, x]
            idx = int(round(float(np.clip(old, 0.0, 1.0)) * levels))
            out[y, x] = idx
            err = old - (idx / levels)
            if x + 1 < w:
                work[y, x + 1] += err * 7 / 16
            if y + 1 < h and x > 0:
                work[y + 1, x - 1] += err * 3 / 16
            if y + 1 < h:
                work[y + 1, x] += err * 5 / 16
            if y + 1 < h and x + 1 < w:
                work[y + 1, x + 1] += err * 1 / 16
    return out


def image_to_ascii(
    path: str | Path,
    *,
    cols: int = DEFAULT_COLS,
    rows: int = DEFAULT_ROWS,
    char_aspect: float = CHAR_ASPECT,
    ramp: str = RAMP_SUSHMITA,
    invert: bool = True,
    auto_crop: bool = True,
    crop_box: tuple[int, int, int, int] | None = None,
    gamma: float = 0.90,
    contrast_lo: float = 2.0,
    contrast_hi: float = 98.0,
    sharpen: float = 0.65,
    dither: bool = True,
    pre_blur: float = 0.35,
    subject_aware: bool = True,
) -> list[str]:
  
    path = Path(path)
    img = ImageOps.exif_transpose(Image.open(path))

    if crop_box is not None:
        bbox: tuple[int, int, int, int] | None = crop_box
    elif auto_crop:
        bbox = _auto_subject_bbox(_to_luma(img))
    else:
        bbox = None

    img = _crop_to_char_aspect(img, cols, rows, char_aspect, bbox)

    if pre_blur and pre_blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=pre_blur))
    img = img.resize((cols, rows), Image.Resampling.LANCZOS)

    luma = _to_luma(img)

    if subject_aware:
        luma = _subject_aware_tone(luma)
    else:
        luma = _percentile_stretch(luma, contrast_lo, contrast_hi)
    luma = _gamma(luma, gamma)
    luma = _unsharp(luma, amount=sharpen)

    darkness = (1.0 - luma) if invert else luma
    darkness = np.where(darkness < 0.035, 0.0, darkness)
    darkness = np.clip(darkness, 0.0, 1.0)

    n = len(ramp)
    if n < 2:
        raise ValueError("ramp must contain at least 2 characters")
    if dither:
        idx = _floyd_steinberg(darkness, n)
    else:
        idx = np.clip(np.rint(darkness * (n - 1)).astype(np.int32), 0, n - 1)

    lines: list[str] = []
    for y in range(rows):
        lines.append("".join(ramp[int(idx[y, x])] for x in range(cols)))
    return lines


def save_ascii(lines: Sequence[str], out: str | Path) -> None:
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> None:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Portrait -> Sushmita-style ASCII")
    p.add_argument("image", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--cols", type=int, default=DEFAULT_COLS)
    p.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    p.add_argument("--gamma", type=float, default=0.90)
    p.add_argument("--ramp", type=str, default=RAMP_SUSHMITA)
    p.add_argument("--no-dither", action="store_true")
    p.add_argument("--no-crop", action="store_true")
    p.add_argument("--no-subject-aware", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    lines = image_to_ascii(
        args.image,
        cols=args.cols,
        rows=args.rows,
        ramp=args.ramp,
        gamma=args.gamma,
        dither=not args.no_dither,
        auto_crop=not args.no_crop,
        subject_aware=not args.no_subject_aware,
    )
    print("\n".join(lines))
    if args.output:
        save_ascii(lines, args.output)
        print(f"# wrote {args.output} ({len(lines)}x{len(lines[0])})", file=sys.stderr)


if __name__ == "__main__":
    main()
