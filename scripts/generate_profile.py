#!/usr/bin/env python3
"""Build synchronized dark and light GitHub profile SVGs from a portrait.

The outputs are 1180x610 terminal windows generated from the same profile data
and animation geometry. Portrait processing and animation are deterministic so
rebuilding the same input produces byte-stable geometry and metrics.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from scipy.optimize import linear_sum_assignment

# ---------------------------------------------------------------------------
# Public profile data. Edit this block, then rerun the script.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InfoToken:
    text: str
    class_name: str = "cc"
    element_id: str = ""


INFO_LINES: tuple[tuple[InfoToken, ...], ...] = (
    (
        InfoToken(". "),
        InfoToken("Uptime", "key"),
        InfoToken(":"),
        InfoToken(" ...................... ", element_id="age_data_dots"),
        InfoToken("4 years, 10 months, 21 days", "value", "age_data"),
    ),
    (
        InfoToken(". "),
        InfoToken("Subject", "key"),
        InfoToken(": ......................................... "),
        InfoToken("Patrick", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Role", "key"),
        InfoToken(": .............. "),
        InfoToken("Backend Engineer · Fullstack Engineer", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Origin", "key"),
        InfoToken(": ................................. "),
        InfoToken("Vietnam · Remote", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Education", "key"),
        InfoToken(": .......................... "),
        InfoToken("Software Engineering", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Status", "key"),
        InfoToken(": ................... "),
        InfoToken("Building · Learning · Shipping", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Lang", "key"),
        InfoToken(": "),
        InfoToken("................. ", element_id="lang_data_dots"),
        InfoToken("TypeScript · Java · HTML · CSS +14", "value", "lang_data"),
    ),
    (InfoToken(". "),),
    (
        InfoToken("- Contact", "accent"),
        InfoToken(" -----------------------------------------------------"),
    ),
    (
        InfoToken(". "),
        InfoToken("Mail", "key"),
        InfoToken(": ................... "),
        InfoToken("laithuanphat.work@gmail.com", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Portfolio", "key"),
        InfoToken(": ....................... "),
        InfoToken("github.com/Patruxs", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("LinkedIn", "key"),
        InfoToken(": ................... "),
        InfoToken("linkedin.com/in/patruxs", "value"),
    ),
    (
        InfoToken(". "),
        InfoToken("Github", "key"),
        InfoToken(": ..................................... "),
        InfoToken("Patruxs", "value"),
    ),
    (InfoToken(". "),),
    (
        InfoToken("- GitHub Stats", "accent"),
        InfoToken(" ------------------------------------------------"),
    ),
    (
        InfoToken(". "),
        InfoToken("Repos", "key"),
        InfoToken(":"),
        InfoToken(" .... ", element_id="repo_data_dots"),
        InfoToken("15", "value", "repo_data"),
        InfoToken(" {"),
        InfoToken("Contributed", "key"),
        InfoToken(": "),
        InfoToken("17", "value", "contrib_data"),
        InfoToken("} | "),
        InfoToken("Stars", "key"),
        InfoToken(":"),
        InfoToken(" .............. ", element_id="star_data_dots"),
        InfoToken("0", "value", "star_data"),
    ),
    (
        InfoToken(". "),
        InfoToken("Commits", "key"),
        InfoToken(":"),
        InfoToken(" ................... ", element_id="commit_data_dots"),
        InfoToken("431", "value", "commit_data"),
        InfoToken(" | "),
        InfoToken("Followers", "key"),
        InfoToken(":"),
        InfoToken(" .......... ", element_id="follower_data_dots"),
        InfoToken("2", "value", "follower_data"),
    ),
    (
        InfoToken(". "),
        InfoToken("Lines of Code on GitHub", "key"),
        InfoToken(":"),
        InfoToken(". ", element_id="loc_data_dots"),
        InfoToken("360,893", "value", "loc_data"),
        InfoToken(" ( "),
        InfoToken("510,165", "addColor", "loc_add"),
        InfoToken("++", "addColor"),
        InfoToken(", "),
        InfoToken("", element_id="loc_del_dots"),
        InfoToken("149,272", "delColor", "loc_del"),
        InfoToken("--", "delColor"),
        InfoToken(" )"),
    ),
)
INFO_LINE_COLUMNS = 79
LOGO_MARKS = ("React", "Java", "Database")

# ---------------------------------------------------------------------------
# Fixed design/animation contract.
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1180, 610
GRID_W, GRID_H = 300, 340
TARGET_DOTS = 17_000
INTRO_GROUPS = 60
DRIFT_BANDS = 94
TRAVELLERS = 900
INTRO_SECONDS = 3.2
LOOP_SECONDS = 14.2

# 3.0 portrait, then 1.3 transition + 2.0 hold for each of three marks,
# with a final 1.3 transition back to the portrait.
TIMES_SECONDS = np.array([0.0, 3.0, 4.3, 6.3, 7.6, 9.6, 10.9, 12.9, 14.2])
KEY_TIMES = TIMES_SECONDS / LOOP_SECONDS
KEY_TIMES_SVG = ";".join(f"{v:.6f}" for v in KEY_TIMES)

FONT_MONO_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
)
FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf",
)


@dataclass
class ThemeMetrics:
    portrait_dots: int
    intro_evenness: float
    straight_boundary: float
    intro_path_bytes: int
    loop_path_bytes: int


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def stable_rng(*parts: object) -> np.random.Generator:
    payload = "|".join(map(str, parts)).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return np.random.default_rng(seed)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_MONO_CANDIDATES
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_width(text: str, size: int, bold: bool = False) -> float:
    bbox = load_font(size, bold=bold).getbbox(text)
    return float(bbox[2] - bbox[0])


def largest_component(mask: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count == 0:
        return mask.astype(bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def otsu_threshold(values: np.ndarray) -> float:
    values = np.clip(values.ravel(), 0, 255).astype(np.uint8)
    histogram = np.bincount(values, minlength=256).astype(np.float64)
    total = values.size
    weighted_total = float(np.dot(np.arange(256), histogram))
    background_weight = 0.0
    background_sum = 0.0
    maximum = -1.0
    threshold = 0
    for index in range(256):
        background_weight += histogram[index]
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += index * histogram[index]
        mean_background = background_sum / background_weight
        mean_foreground = (weighted_total - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (mean_background - mean_foreground) ** 2
        if variance > maximum:
            maximum = variance
            threshold = index
    return float(threshold)


def subject_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    if float(np.mean(alpha < 240)) > 0.02 and np.any(alpha > 24):
        ys, xs = np.where(alpha > 24)
        return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

    rgb = rgba[..., :3].astype(np.float32)
    border = np.concatenate(
        [
            rgb[:12].reshape(-1, 3),
            rgb[-12:].reshape(-1, 3),
            rgb[:, :12].reshape(-1, 3),
            rgb[:, -12:].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(border, axis=0)
    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    normalized = 255.0 * distance / max(float(distance.max()), 1.0)
    preliminary = normalized > max(18.0, otsu_threshold(normalized))
    preliminary = ndimage.binary_closing(preliminary, structure=np.ones((5, 5)), iterations=2)
    preliminary = ndimage.binary_fill_holes(preliminary)
    preliminary = largest_component(preliminary)
    if not preliminary.any():
        return 0, 0, image.width, image.height
    ys, xs = np.where(preliminary)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def crop_head_shoulders(image: Image.Image) -> Image.Image:
    """Top-anchored, roomy 300:340 crop retaining head and shoulders."""
    image = image.convert("RGBA")
    x0, y0, x1, _ = subject_bounds(image)
    subject_width = max(1, x1 - x0)
    crop_width = min(image.width, int(round(subject_width * 1.06)))
    crop_height = int(round(crop_width * GRID_H / GRID_W))

    center_x = (x0 + x1) / 2.0
    left = int(round(center_x - crop_width / 2.0))
    left = max(0, min(left, image.width - crop_width))

    # Small headroom only; the rest of the frame is reserved for shoulders.
    top = max(0, y0 - int(round(subject_width * 0.025)))
    if top + crop_height > image.height:
        top = max(0, image.height - crop_height)
    bottom = min(image.height, top + crop_height)
    return image.crop((left, top, left + crop_width, bottom))


def segment_subject(crop: Image.Image) -> np.ndarray:
    """Colour-distance segmentation + closing + fill holes + largest component."""
    rgba = np.asarray(crop.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32) / 255.0

    # Transparent pixels define a robust background sample when available.
    transparent = alpha < 0.08
    if transparent.any():
        background = np.median(rgb[transparent], axis=0)
    else:
        border = np.concatenate(
            [
                rgb[:10].reshape(-1, 3),
                rgb[-10:].reshape(-1, 3),
                rgb[:, :10].reshape(-1, 3),
                rgb[:, -10:].reshape(-1, 3),
            ],
            axis=0,
        )
        background = np.median(border, axis=0)

    distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    distance /= max(float(distance.max()), 1.0)
    # Alpha keeps dark clothing from being mistaken for a transparent dark background;
    # colour distance remains the segmentation signal for ordinary opaque photos.
    score = np.maximum(alpha, distance * 0.72)
    normalized = score * 255.0
    threshold = max(18.0, otsu_threshold(normalized))
    mask = normalized > threshold

    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5)), iterations=2)
    mask = ndimage.binary_fill_holes(mask)
    mask = largest_component(mask)
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3)), iterations=1)
    mask = ndimage.binary_fill_holes(mask)
    return mask.astype(bool)


def preprocess_portrait(image: Image.Image) -> tuple[Image.Image, np.ndarray]:
    crop = crop_head_shoulders(image)
    mask = segment_subject(crop)

    resized = crop.resize((GRID_W, GRID_H), Image.Resampling.LANCZOS)
    mask_image = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    mask = np.asarray(mask_image.resize((GRID_W, GRID_H), Image.Resampling.NEAREST)) > 127

    # The light-mode source retains its background. Transparent input naturally
    # becomes a clean white background rather than an invented replacement scene.
    white = Image.new("RGBA", resized.size, (255, 255, 255, 255))
    grayscale = Image.alpha_composite(white, resized.convert("RGBA")).convert("L")
    grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
    grayscale = ImageEnhance.Contrast(grayscale).enhance(1.3)
    grayscale = grayscale.filter(ImageFilter.UnsharpMask(radius=3, percent=140, threshold=0))
    return grayscale, mask


def floyd_steinberg_serpentine(tone: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    """1-bit serpentine Floyd-Steinberg with hard mask-edge diffusion clearing."""
    work = np.clip(tone.astype(np.float64), 0.0, 255.0).copy()
    height, width = work.shape
    active = np.ones((height, width), dtype=bool) if mask is None else mask.astype(bool)
    output = np.zeros((height, width), dtype=bool)

    for y in range(height):
        left_to_right = y % 2 == 0
        x_range = range(width) if left_to_right else range(width - 1, -1, -1)
        for x in x_range:
            if not active[y, x]:
                work[y, x] = 0.0  # hard-clear accumulated bleed outside the mask
                continue
            old = work[y, x]
            new = 255.0 if old >= 127.5 else 0.0
            output[y, x] = new > 0.0
            error = old - new
            if left_to_right:
                neighbours = (
                    (x + 1, y, 7 / 16),
                    (x - 1, y + 1, 3 / 16),
                    (x, y + 1, 5 / 16),
                    (x + 1, y + 1, 1 / 16),
                )
            else:
                neighbours = (
                    (x - 1, y, 7 / 16),
                    (x + 1, y + 1, 3 / 16),
                    (x, y + 1, 5 / 16),
                    (x - 1, y + 1, 1 / 16),
                )
            for nx, ny, weight in neighbours:
                if 0 <= nx < width and 0 <= ny < height and active[ny, nx]:
                    work[ny, nx] += error * weight
    output &= active
    return output


def scale_for_dot_budget(tone: np.ndarray, active: np.ndarray, target: int) -> np.ndarray:
    """Scale exposure globally; relative portrait contrast is left unchanged."""
    target = int(np.clip(target, 1, int(active.sum())))
    base = tone.astype(np.float64)
    low, high = 0.0, 12.0
    for _ in range(30):
        middle = (low + high) / 2.0
        estimate = float(np.clip(base * middle, 0, 255)[active].sum() / 255.0)
        if estimate < target:
            low = middle
        else:
            high = middle
    return np.clip(base * ((low + high) / 2.0), 0.0, 255.0)


def portrait_points(grayscale: Image.Image, mask: np.ndarray, mode: str) -> np.ndarray:
    values = np.asarray(grayscale, dtype=np.float64)
    if mode == "dark":
        active = mask
        tone = scale_for_dot_budget(values, active, TARGET_DOTS)
        bitmap = floyd_steinberg_serpentine(tone, mask=active)
    elif mode == "light":
        active = np.ones_like(mask, dtype=bool)
        tone = scale_for_dot_budget(255.0 - values, active, TARGET_DOTS)
        bitmap = floyd_steinberg_serpentine(tone, mask=None)
    else:
        raise ValueError(f"Unknown mode: {mode}")
    ys, xs = np.where(bitmap)
    return np.column_stack([xs, ys]).astype(np.float64)


def intro_groups(points: np.ndarray, groups: int = INTRO_GROUPS) -> tuple[np.ndarray, float]:
    """Globally interleave every group across a 6x6 spatial diagnostic grid."""
    rng = stable_rng("intro", len(points), groups)
    cells_x = cells_y = 6
    cell_x = np.minimum((points[:, 0] * cells_x / GRID_W).astype(int), cells_x - 1)
    cell_y = np.minimum((points[:, 1] * cells_y / GRID_H).astype(int), cells_y - 1)
    cell_ids = cell_x + cells_x * cell_y
    labels = np.empty(len(points), dtype=np.int32)

    for cell in range(cells_x * cells_y):
        ids = np.flatnonzero(cell_ids == cell)
        rng.shuffle(ids)
        offset = int(rng.integers(0, groups))
        labels[ids] = (np.arange(len(ids)) + offset) % groups

    global_hist = np.bincount(cell_ids, minlength=cells_x * cells_y).astype(np.float64)
    global_hist /= max(float(global_hist.sum()), 1.0)
    distances: list[float] = []
    for group in range(groups):
        local = np.bincount(cell_ids[labels == group], minlength=cells_x * cells_y).astype(np.float64)
        local /= max(float(local.sum()), 1.0)
        distances.append(float(0.5 * np.abs(local - global_hist).sum()))
    return labels, float(np.mean(distances))


def points_to_path(points: np.ndarray, dot: float = 1.0) -> str:
    """Encode square dots as horizontal SVG path runs with crisp edges."""
    if len(points) == 0:
        return ""
    xy = np.unique(np.rint(points).astype(np.int32), axis=0)
    xy = xy[np.lexsort((xy[:, 0], xy[:, 1]))]
    commands: list[str] = []
    index = 0
    while index < len(xy):
        start_x, y = int(xy[index, 0]), int(xy[index, 1])
        end_x = start_x
        index += 1
        while index < len(xy) and int(xy[index, 1]) == y and int(xy[index, 0]) == end_x + 1:
            end_x = int(xy[index, 0])
            index += 1
        width = (end_x - start_x + 1) * dot
        commands.append(f"M{start_x} {y}h{width:g}v{dot:g}h-{width:g}z")
    return "".join(commands)


def raster_logo(mark: str) -> np.ndarray:
    canvas = Image.new("L", (GRID_W, GRID_H), 0)
    draw = ImageDraw.Draw(canvas)

    if mark == "React":
        ring_box = (72, 124, 228, 200)
        for angle in (0, 60, 120):
            ring = Image.new("L", (GRID_W, GRID_H), 0)
            ImageDraw.Draw(ring).ellipse(ring_box, outline=255, width=8)
            canvas = Image.fromarray(
                np.maximum(
                    np.asarray(canvas),
                    np.asarray(
                        ring.rotate(
                            angle,
                            resample=Image.Resampling.BICUBIC,
                            center=(150, 162),
                        )
                    ),
                )
            )
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((139, 151, 161, 173), fill=255)
    elif mark == "Java":
        # Steam, cup, handle, and saucer form a compact Java coffee mark.
        draw.arc((105, 72, 165, 151), 275, 82, fill=255, width=8)
        draw.arc((135, 82, 190, 157), 96, 260, fill=255, width=8)
        draw.arc((113, 96, 174, 166), 280, 78, fill=255, width=7)
        draw.line((94, 159, 198, 159), fill=255, width=9)
        draw.arc((95, 137, 205, 225), 0, 180, fill=255, width=10)
        draw.arc((181, 164, 225, 207), 255, 105, fill=255, width=9)
        draw.arc((78, 203, 222, 238), 2, 178, fill=255, width=9)
        draw.arc((92, 217, 208, 246), 2, 178, fill=255, width=7)
    elif mark == "Database":
        draw.ellipse((79, 91, 221, 145), outline=255, width=10)
        draw.line((79, 118, 79, 224), fill=255, width=10)
        draw.line((221, 118, 221, 224), fill=255, width=10)
        draw.arc((79, 125, 221, 179), 0, 180, fill=255, width=10)
        draw.arc((79, 169, 221, 223), 0, 180, fill=255, width=10)
        draw.arc((79, 197, 221, 251), 0, 180, fill=255, width=10)
    else:
        raise ValueError(f"Unknown logo {mark!r}")

    return np.asarray(canvas) > 127


def sample_logo(mask: np.ndarray, count: int, key: str) -> np.ndarray:
    ys, xs = np.where(mask)
    points = np.column_stack([xs, ys]).astype(np.float64)
    if len(points) == 0:
        raise ValueError(f"Logo {key!r} produced no points")
    if len(points) < count:
        points = np.tile(points, (int(math.ceil(count / len(points))), 1))
    rng = stable_rng("logo", key, count)
    chosen = rng.choice(len(points), count, replace=False)
    return points[chosen] + rng.normal(0.0, 0.18, size=(count, 2))


def optimal_transport(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Exact Hungarian assignment minimizing total squared dot travel."""
    cost = ((source[:, None, :] - target[None, :, :]) ** 2).sum(axis=2)
    rows, columns = linear_sum_assignment(cost)
    reordered = np.empty_like(target)
    reordered[rows] = target[columns]
    return reordered


def logo_trajectories(marks: Sequence[str]) -> list[np.ndarray]:
    clouds = [sample_logo(raster_logo(mark), TRAVELLERS, mark) for mark in marks]
    first = clouds[0]
    second = optimal_transport(first, clouds[1])
    third = optimal_transport(second, clouds[2])
    return_to_first = optimal_transport(third, first)
    return [first, second, third, return_to_first]


def drift_bands(points: np.ndarray, target_centroid: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Cluster noisy linear drift; sigma=4 noise breaks quantized square boundaries."""
    rng = stable_rng("drift", len(points), DRIFT_BANDS)
    ideal = 0.42 * (target_centroid[None, :] - points)
    noisy = ideal + rng.normal(0.0, 4.0, size=ideal.shape)
    initial_ids = rng.choice(len(noisy), DRIFT_BANDS, replace=False)
    _, labels = kmeans2(noisy, noisy[initial_ids], iter=28, minit="matrix")
    labels = labels.astype(np.int32)

    translations = np.zeros((DRIFT_BANDS, 2), dtype=np.float64)
    for band in range(DRIFT_BANDS):
        members = ideal[labels == band]
        if len(members):
            translations[band] = members.mean(axis=0)

    # Detect long, axis-aligned repeated boundaries between the same band pair.
    grid = np.full((GRID_H, GRID_W), -1, dtype=np.int32)
    xy = np.rint(points).astype(np.int32)
    valid = (
        (xy[:, 0] >= 0)
        & (xy[:, 0] < GRID_W)
        & (xy[:, 1] >= 0)
        & (xy[:, 1] < GRID_H)
    )
    grid[xy[valid, 1], xy[valid, 0]] = labels[valid]

    horizontal_boundary = (
        (grid[:, :-1] >= 0)
        & (grid[:, 1:] >= 0)
        & (grid[:, :-1] != grid[:, 1:])
    )
    vertical_boundary = (
        (grid[:-1, :] >= 0)
        & (grid[1:, :] >= 0)
        & (grid[:-1, :] != grid[1:, :])
    )

    left, right = grid[:, :-1], grid[:, 1:]
    horizontal_codes = np.where(
        horizontal_boundary,
        np.minimum(left, right) * DRIFT_BANDS + np.maximum(left, right),
        -1,
    )
    upper, lower = grid[:-1, :], grid[1:, :]
    vertical_codes = np.where(
        vertical_boundary,
        np.minimum(upper, lower) * DRIFT_BANDS + np.maximum(upper, lower),
        -1,
    )

    def long_run_pixels(lines: np.ndarray, minimum: int = 5) -> int:
        count = 0
        for line in lines:
            start = 0
            while start < len(line):
                code = int(line[start])
                end = start + 1
                while end < len(line) and int(line[end]) == code:
                    end += 1
                if code >= 0 and end - start >= minimum:
                    count += end - start
                start = end
        return count

    long_pixels = long_run_pixels(horizontal_codes) + long_run_pixels(vertical_codes.T)
    boundary_pixels = max(int(horizontal_boundary.sum() + vertical_boundary.sum()), 1)
    return labels, translations, float(long_pixels / boundary_pixels)


def info_rows_svg() -> str:
    left = 506.0
    y = 128.0
    row_gap = 25.0
    clip_definitions: list[str] = []
    parts: list[str] = []

    for line_index, tokens in enumerate(INFO_LINES):
        line_y = y + line_index * row_gap
        padding = max(
            INFO_LINE_COLUMNS - sum(len(token.text) for token in tokens),
            0,
        )
        padding_index = next(
            (
                index
                for index in range(len(tokens) - 1, -1, -1)
                if tokens[index].class_name == "cc"
                and ("." in tokens[index].text or "-" in tokens[index].text)
            ),
            -1,
        ) if len(tokens) > 1 else -1
        clip_definitions.append(
            f'<clipPath id="lc{line_index}">'
            f'<rect x="496" y="{line_y - 17:.1f}" width="638" height="23"/>'
            '</clipPath>'
        )
        spans: list[str] = []
        for token_index, token in enumerate(tokens):
            position = (
                f' x="{left:.1f}" y="{line_y:.1f}"'
                if token_index == 0
                else ""
            )
            element_id = (
                f' id="{escape(token.element_id)}"' if token.element_id else ""
            )
            token_text = token.text
            if token_index == padding_index and padding:
                fill_character = "-" if "-" in token_text else "."
                if token_text.endswith(" "):
                    token_text = (
                        token_text[:-1] + fill_character * padding + " "
                    )
                else:
                    token_text += fill_character * padding
            spans.append(
                f'<tspan{position} class="{escape(token.class_name)}"{element_id}>'
                f'{escape(token_text)}</tspan>'
            )
        parts.append(
            f'<g clip-path="url(#lc{line_index})">'
            f'<text x="{left:.1f}" y="0" fill="var(--text)" class="terminal-line">'
            f'{"".join(spans)}</text></g>'
        )

    return f'<defs>{"".join(clip_definitions)}</defs>{"".join(parts)}'


def build_portrait_layers(points: np.ndarray, prefix: str, logo_centroid: np.ndarray) -> tuple[str, ThemeMetrics]:
    group_labels, evenness = intro_groups(points)
    band_labels, translations, boundary = drift_bands(points, logo_centroid)

    intro_paths: list[str] = []
    rng = stable_rng("intro-fade-order", prefix, len(points))
    random_order = rng.permutation(INTRO_GROUPS)
    rank = np.empty(INTRO_GROUPS, dtype=np.int32)
    rank[random_order] = np.arange(INTRO_GROUPS)
    intro_geometry_bytes = 0

    for group in range(INTRO_GROUPS):
        path_data = points_to_path(points[group_labels == group])
        intro_geometry_bytes += len(path_data.encode("utf-8"))
        begin = 0.08 + 0.72 * rank[group] / max(INTRO_GROUPS - 1, 1)
        duration = 1.18 + 0.22 * ((group * 17) % INTRO_GROUPS) / max(INTRO_GROUPS - 1, 1)
        intro_paths.append(
            f'<path d="{path_data}" opacity="0">'
            f'<animate attributeName="opacity" values="0;1" begin="{begin:.3f}s" '
            f'dur="{duration:.3f}s" fill="freeze" calcMode="linear"/>'
            f'</path>'
        )

    portrait_opacity = "1;1;0;0;0;0;0;0;1"
    band_paths: list[str] = []
    loop_geometry_bytes = 0
    for band in range(DRIFT_BANDS):
        path_data = points_to_path(points[band_labels == band])
        loop_geometry_bytes += len(path_data.encode("utf-8"))
        dx, dy = translations[band]
        transforms = (
            f"0 0;0 0;{dx:.3f} {dy:.3f};{dx:.3f} {dy:.3f};"
            f"{dx:.3f} {dy:.3f};{dx:.3f} {dy:.3f};{dx:.3f} {dy:.3f};"
            f"{dx:.3f} {dy:.3f};0 0"
        )
        band_paths.append(
            f'<path d="{path_data}">'
            f'<animate attributeName="opacity" values="{portrait_opacity}" '
            f'keyTimes="{KEY_TIMES_SVG}" begin="{INTRO_SECONDS}s" dur="{LOOP_SECONDS}s" '
            f'repeatCount="indefinite" calcMode="linear"/>'
            f'<animateTransform attributeName="transform" type="translate" values="{transforms}" '
            f'keyTimes="{KEY_TIMES_SVG}" begin="{INTRO_SECONDS}s" dur="{LOOP_SECONDS}s" '
            f'repeatCount="indefinite" calcMode="linear"/>'
            f'</path>'
        )

    svg = (
        f'<g class="portrait-theme {prefix}">'
        f'<g id="{prefix}-intro">'
        f'<animate attributeName="opacity" values="1;1;0" keyTimes="0;0.925;1" '
        f'begin="0s" dur="{INTRO_SECONDS}s" fill="freeze" calcMode="linear"/>'
        f'{"".join(intro_paths)}</g>'
        f'<g id="{prefix}-loop" opacity="0">'
        f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;0.900;1" '
        f'begin="0s" dur="{INTRO_SECONDS}s" fill="freeze" calcMode="linear"/>'
        f'{"".join(band_paths)}</g>'
        f'</g>'
    )
    metrics = ThemeMetrics(
        portrait_dots=int(len(points)),
        intro_evenness=float(evenness),
        straight_boundary=float(boundary),
        intro_path_bytes=int(intro_geometry_bytes),
        loop_path_bytes=int(loop_geometry_bytes),
    )
    return svg, metrics


def traveller_svg(trajectories: Sequence[np.ndarray]) -> str:
    first, second, third, return_first = trajectories
    opacity = "0;0;1;1;1;1;1;1;0"
    dot_path = "M-.82 -.82h1.64v1.64h-1.64z"
    parts: list[str] = []
    for index in range(TRAVELLERS):
        positions = [
            first[index],
            first[index],
            first[index],
            first[index],
            second[index],
            second[index],
            third[index],
            third[index],
            return_first[index],
        ]
        transform_values = ";".join(f"{point[0]:.3f} {point[1]:.3f}" for point in positions)
        parts.append(
            f'<path d="{dot_path}" opacity="0" shape-rendering="crispEdges">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="{transform_values}" keyTimes="{KEY_TIMES_SVG}" '
            f'begin="{INTRO_SECONDS}s" dur="{LOOP_SECONDS}s" repeatCount="indefinite" '
            f'calcMode="linear"/>'
            f'<animate attributeName="opacity" values="{opacity}" '
            f'keyTimes="{KEY_TIMES_SVG}" begin="{INTRO_SECONDS}s" dur="{LOOP_SECONDS}s" '
            f'repeatCount="indefinite" calcMode="linear"/>'
            f'</path>'
        )
    return "".join(parts)


def build_svgs(image_path: Path) -> tuple[dict[str, str], dict[str, object]]:
    image = Image.open(image_path)
    grayscale, mask = preprocess_portrait(image)
    dark_points = portrait_points(grayscale, mask, "dark")
    light_points = portrait_points(grayscale, mask, "light")

    trajectories = logo_trajectories(LOGO_MARKS)
    first_logo_centroid = trajectories[0].mean(axis=0)
    dark_layers, dark_metrics = build_portrait_layers(dark_points, "portrait-dark", first_logo_centroid)
    light_layers, light_metrics = build_portrait_layers(light_points, "portrait-light", first_logo_centroid)
    travellers = traveller_svg(trajectories)
    rows = info_rows_svg()

    portrait_x, portrait_y = 48.0, 123.0
    portrait_height = 430.0
    portrait_scale = portrait_height / GRID_H

    live_x = 1080.0

    theme_data = {
        "dark": {
            "description": "Animated dark-mode terminal profile for Patruxs.",
            "palette": (
                "--bg:#080A0D; --panel:#0D1117; --stroke:#2B313B; --text:#E6EDF3;\n"
                "      --muted:#7D8998; --label:#39D0D8; --portrait:#A8F07A;\n"
                "      --positive:#41D17D; --negative:#FF667A; --live:#FF4D5A;"
            ),
            "portrait": dark_layers,
        },
        "light": {
            "description": "Animated light-mode terminal profile for Patruxs.",
            "palette": (
                "--bg:#E8EBEF; --panel:#F7F8FA; --stroke:#C4CAD3; --text:#15191F;\n"
                "      --muted:#66707D; --label:#087F8C; --portrait:#1F6E5C;\n"
                "      --positive:#18794E; --negative:#C21F39; --live:#D7263D;"
            ),
            "portrait": light_layers,
        },
    }

    def render_svg(theme: str) -> str:
        data = theme_data[theme]
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">
  <title id="title">profile.sh --live</title>
  <desc id="description">{data["description"]} The portrait uses 300 by 340 one-bit serpentine Floyd-Steinberg dithering.</desc>
  <style>
    :root {{
      {data["palette"]}
    }}
    text {{ font-family:"DejaVu Sans Mono","Liberation Mono",monospace; }}
    .window-title {{ font-size:13px; fill:var(--muted); letter-spacing:.3px; }}
    .section {{ font-size:13px; fill:var(--muted); font-weight:700; letter-spacing:1.7px; }}
    .terminal-line {{ font-size:16.5px; letter-spacing:-2.05px; dominant-baseline:alphabetic; }}
    .key, .accent {{ fill:var(--label); font-weight:700; }}
    .cc {{ fill:var(--muted); }}
    .value {{ fill:var(--text); }}
    .addColor {{ fill:var(--positive); font-weight:700; }}
    .delColor {{ fill:var(--negative); font-weight:700; }}
    .live {{ font-size:12px; fill:var(--live); font-weight:700; letter-spacing:1.4px; }}
  </style>

  <rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="var(--bg)"/>
  <rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="17" fill="none" stroke="var(--stroke)"/>
  <path d="M1 48H1179" stroke="var(--stroke)"/>
  <circle cx="24" cy="24" r="5" fill="#FF5F57"/>
  <circle cx="42" cy="24" r="5" fill="#FEBC2E"/>
  <circle cx="60" cy="24" r="5" fill="#28C840"/>
  <text x="590" y="29" text-anchor="middle" class="window-title" textLength="128" lengthAdjust="spacingAndGlyphs">profile.sh --live</text>

  <rect x="26" y="72" width="420" height="512" rx="12" fill="var(--panel)" stroke="var(--stroke)"/>
  <rect x="470" y="72" width="684" height="512" rx="12" fill="var(--panel)" stroke="var(--stroke)"/>
  <text x="48" y="101" class="section" textLength="91" lengthAdjust="spacingAndGlyphs">VISUAL.MAP</text>
  <text x="496" y="101" class="section" textLength="102" lengthAdjust="spacingAndGlyphs">SYSTEM.INFO</text>

  <circle cx="{live_x:.1f}" cy="96" r="4" fill="var(--live)">
    <animate attributeName="opacity" values=".35;1;.35" keyTimes="0;.5;1" dur="1.25s" repeatCount="indefinite"/>
  </circle>
  <text x="{live_x + 11:.1f}" y="100" class="live" textLength="34" lengthAdjust="spacingAndGlyphs">LIVE</text>

  <g transform="translate({portrait_x} {portrait_y}) scale({portrait_scale:.6f})" fill="var(--portrait)" shape-rendering="crispEdges">
    {data["portrait"]}
    <g id="travellers">{travellers}</g>
  </g>

  {rows}
</svg>
'''
    svgs = {theme: render_svg(theme) for theme in theme_data}

    metrics: dict[str, object] = {
        "canvas": {"width": WIDTH, "height": HEIGHT},
        "grid": {"width": GRID_W, "height": GRID_H},
        "intro": {"seconds": INTRO_SECONDS, "groups": INTRO_GROUPS},
        "loop": {
            "seconds": LOOP_SECONDS,
            "key_times_seconds": TIMES_SECONDS.tolist(),
            "key_times_normalized": [round(float(value), 6) for value in KEY_TIMES],
            "portrait_hold_seconds": 3.0,
            "logo_hold_seconds": 2.0,
            "transition_seconds": 1.3,
        },
        "drift_bands": DRIFT_BANDS,
        "travellers": TRAVELLERS,
        "logos": list(LOGO_MARKS),
        "dark": asdict(dark_metrics),
        "light": asdict(light_metrics),
    }
    return svgs, metrics


def write_preview_html(dark_svg_name: str, light_svg_name: str) -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>profile.sh --live</title>
<style>
  html,body{{margin:0;min-height:100%;background:#050608}}
  body{{display:grid;place-items:center;padding:24px;box-sizing:border-box}}
  img{{width:min(1180px,100%);height:auto;filter:drop-shadow(0 24px 64px rgba(0,0,0,.36))}}
  @media(prefers-color-scheme:light){{html,body{{background:#D8DCE2}}}}
</style>
</head>
<body>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="{escape(dark_svg_name)}">
    <img src="{escape(light_svg_name)}" alt="Animated GitHub profile">
  </picture>
</body>
</html>
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, nargs="?", default=Path("assets/portrait.png"))
    parser.add_argument("--dark-output", type=Path, default=Path("assets/dark.svg"))
    parser.add_argument("--light-output", type=Path, default=Path("assets/light.svg"))
    parser.add_argument("--metrics", type=Path, default=Path("metrics.json"))
    parser.add_argument("--html", type=Path, default=Path("profile.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    svgs, metrics = build_svgs(args.image)
    outputs = {"dark": args.dark_output, "light": args.light_output}
    for theme, output in outputs.items():
        output.write_text(svgs[theme], encoding="utf-8")
    metrics["svg_bytes"] = {
        theme: output.stat().st_size for theme, output in outputs.items()
    }
    args.metrics.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    args.html.write_text(
        write_preview_html(args.dark_output.name, args.light_output.name),
        encoding="utf-8",
    )

    for theme, output in outputs.items():
        print(f"Wrote {output} ({output.stat().st_size / 1024:.1f} KiB, {theme})")
    for mode in ("dark", "light"):
        data = metrics[mode]
        print(
            f"{mode}: {data['portrait_dots']:,} dots, "
            f"intro evenness={data['intro_evenness']:.4f}, "
            f"straight boundary={data['straight_boundary']:.4f}"
        )


if __name__ == "__main__":
    main()
