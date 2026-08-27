#!/usr/bin/env python3
"""Refresh live profile data and GitHub summary cards.

The script intentionally uses only Python's standard library. It downloads the
three cards displayed by README.md for both color themes, reads the shared
GitHub statistics from the stats card, computes repository line totals through
GitHub's contributor statistics API, and updates both generated profile SVGs.
"""
from __future__ import annotations

import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
CARD_API = "https://github-profile-summary-cards.vercel.app/api/cards"
CARD_ENDPOINTS = {
    "1-repos-per-language.svg": "repos-per-language",
    "2-most-commit-language.svg": "most-commit-language",
    "3-stats.svg": "stats",
}
THEMES = ("github", "github_dark")
LINE_COLUMNS = 79
LANGUAGE_LIMIT = 4
LANGUAGE_SEPARATOR = " · "


@dataclass(frozen=True)
class ProfileStats:
    uptime: str
    repos: int
    contributed: int
    stars: int
    commits: int
    followers: int
    additions: int | None
    deletions: int | None
    languages: str | None = None

    @property
    def lines_of_code(self) -> int | None:
        if self.additions is None or self.deletions is None:
            return None
        return self.additions - self.deletions


class HttpClient:
    def __init__(self, token: str = "", retries: int = 4) -> None:
        self.token = token
        self.retries = retries

    def get(self, url: str, accept: str = "application/vnd.github+json") -> str:
        headers = {
            "Accept": accept,
            "User-Agent": "Patruxs-profile-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=45) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code not in {429, 500, 502, 503, 504}:
                    break
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Could not fetch {url}: {last_error}") from last_error

    def get_json(self, url: str) -> Any:
        return json.loads(self.get(url))


def _anniversary(start: dt.date, year: int) -> dt.date:
    day = min(start.day, calendar.monthrange(year, start.month)[1])
    return dt.date(year, start.month, day)


def _add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def account_age(start: dt.date, today: dt.date) -> str:
    """Return an exact calendar duration suitable for the Uptime row."""
    if today < start:
        raise ValueError("Account creation date cannot be in the future")

    years = today.year - start.year
    year_anchor = _anniversary(start, start.year + years)
    if year_anchor > today:
        years -= 1
        year_anchor = _anniversary(start, start.year + years)

    months = 0
    while _add_months(year_anchor, months + 1) <= today:
        months += 1
    month_anchor = _add_months(year_anchor, months)
    days = (today - month_anchor).days

    parts = []
    for value, singular in (
        (years, "year"),
        (months, "month"),
        (days, "day"),
    ):
        if value:
            suffix = singular if value == 1 else f"{singular}s"
            parts.append(f"{value} {suffix}")
    return ", ".join(parts) if parts else "0 days"


def parse_card_stats(svg: str) -> dict[str, int]:
    """Read the statistics by label so upstream layout changes fail safely."""
    root = ET.fromstring(svg)
    texts = [
        ("".join(element.itertext()).strip(), element.attrib.get("y"))
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "text"
    ]
    labels = {
        "Total Stars:": "stars",
        "Total Commits:": "commits",
        "Contributed to:": "contributed",
    }
    values: dict[str, int] = {}

    for index, (text, y_position) in enumerate(texts):
        key = labels.get(text)
        if not key:
            continue

        candidates = []
        if y_position is not None:
            candidates.extend(
                candidate
                for candidate, candidate_y in texts
                if candidate_y == y_position and candidate != text
            )
        candidates.extend(candidate for candidate, _ in texts[index + 1 :])
        match = next(
            (candidate for candidate in candidates if re.fullmatch(r"[\d,]+", candidate)),
            None,
        )
        if match is None:
            raise ValueError(f"Summary card has no numeric value for {text}")
        values[key] = int(match.replace(",", ""))

    missing = set(labels.values()) - values.keys()
    if missing:
        raise ValueError(f"Summary card is missing stats: {', '.join(sorted(missing))}")
    return values


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def download_cards(
    client: HttpClient,
    username: str,
    output_directory: Path,
) -> tuple[dict[str, int], dict[Path, str]]:
    light_stats = ""
    downloads: dict[Path, str] = {}
    for theme in THEMES:
        theme_directory = output_directory / theme
        for filename, endpoint in CARD_ENDPOINTS.items():
            query = urllib.parse.urlencode({"username": username, "theme": theme})
            url = f"{CARD_API}/{endpoint}?{query}"
            try:
                svg = client.get(url, accept="image/svg+xml")
                ET.fromstring(svg)
                if "<svg" not in svg or "Something went wrong" in svg:
                    raise ValueError(f"Card service returned an invalid {theme}/{filename}")
                downloads[theme_directory / filename] = svg
                if theme == "github" and filename == "3-stats.svg":
                    light_stats = svg
            except Exception as e:
                print(f"Warning: Failed to download {filename} for {theme}: {e}", file=sys.stderr)
                if theme == "github" and filename == "3-stats.svg":
                    fallback_path = theme_directory / filename
                    if fallback_path.exists():
                        print(f"Using fallback for {filename}", file=sys.stderr)
                        light_stats = fallback_path.read_text(encoding="utf-8")
                    else:
                        raise ValueError("No fallback available for 3-stats.svg") from e
    return parse_card_stats(light_stats), downloads


def fetch_repositories(client: HttpClient, username: str) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"type": "owner", "sort": "full_name", "per_page": 100, "page": page}
        )
        batch = client.get_json(f"{GITHUB_API}/users/{username}/repos?{query}")
        if not isinstance(batch, list):
            raise ValueError("GitHub repositories response was not a list")
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
        page += 1


def format_languages(names: list[str]) -> str:
    if not names:
        return "N/A"

    shown = names[:LANGUAGE_LIMIT]
    value_budget = LINE_COLUMNS - len(". Lang:") - 2
    while shown:
        extra = len(names) - len(shown)
        suffix = f" +{extra}" if extra else ""
        value = LANGUAGE_SEPARATOR.join(shown) + suffix
        if len(value) <= value_budget:
            return value
        shown.pop()
    return f"+{len(names)}"


def fetch_languages(
    client: HttpClient,
    repositories: list[dict[str, Any]],
) -> str:
    owned_repositories = [
        repository for repository in repositories if not repository.get("fork", False)
    ]

    def repository_languages(repository: dict[str, Any]) -> dict[str, int]:
        languages = client.get_json(
            f"{GITHUB_API}/repos/{repository['full_name']}/languages"
        )
        if not isinstance(languages, dict):
            raise ValueError(
                f"GitHub languages response was not an object for "
                f"{repository['full_name']}"
            )
        return {str(name): int(size) for name, size in languages.items()}

    totals: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        language_sets = executor.map(repository_languages, owned_repositories)
        for languages in language_sets:
            for name, size in languages.items():
                totals[name] = totals.get(name, 0) + size

    ranked = sorted(totals, key=lambda name: (-totals[name], name.casefold(), name))
    return format_languages(ranked)


def fetch_line_totals(
    client: HttpClient,
    username: str,
    repositories: list[dict[str, Any]],
) -> tuple[int, int] | None:
    def repository_totals(
        repository: dict[str, Any],
    ) -> tuple[int, int] | None:
        full_name = repository["full_name"]
        contributors: Any = None
        for attempt in range(8):
            try:
                contributors = client.get_json(
                    f"{GITHUB_API}/repos/{full_name}/stats/contributors"
                )
            except (json.JSONDecodeError, RuntimeError):
                contributors = None
            if isinstance(contributors, list):
                break
            if attempt < 7:
                time.sleep(5)
        if not isinstance(contributors, list):
            print(
                f"Warning: preserving existing line totals because contributor "
                f"statistics are unavailable for {full_name}",
                file=sys.stderr,
            )
            return None
        additions = 0
        deletions = 0
        for contributor in contributors:
            author = contributor.get("author") or {}
            if author.get("login", "").casefold() != username.casefold():
                continue
            for week in contributor.get("weeks", []):
                additions += int(week.get("a", 0))
                deletions += int(week.get("d", 0))
        return additions, deletions

    with ThreadPoolExecutor(max_workers=4) as executor:
        totals = list(executor.map(repository_totals, repositories))
    if any(item is None for item in totals):
        return None
    return sum(item[0] for item in totals), sum(item[1] for item in totals)


def fetch_profile_stats(
    client: HttpClient,
    username: str,
    card_stats: dict[str, int],
    today: dt.date,
    birthday: str = "",
) -> ProfileStats:
    start_date: dt.date | None = None
    if birthday.strip():
        try:
            start_date = dt.date.fromisoformat(birthday.strip())
        except ValueError as error:
            raise ValueError("BIRTHDAY must use YYYY-MM-DD") from error

    user = client.get_json(f"{GITHUB_API}/users/{username}")
    repositories = fetch_repositories(client, username)
    line_totals = fetch_line_totals(client, username, repositories)
    languages = fetch_languages(client, repositories)
    additions, deletions = line_totals if line_totals is not None else (None, None)
    if start_date is None:
        created_at = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
        start_date = created_at.date()

    return ProfileStats(
        uptime=account_age(start_date, today),
        repos=int(user["public_repos"]),
        contributed=card_stats["contributed"],
        stars=card_stats["stars"],
        commits=card_stats["commits"],
        followers=int(user["followers"]),
        additions=additions,
        deletions=deletions,
        languages=languages,
    )


def _replace_tspan(svg: str, element_id: str, value: str) -> str:
    pattern = re.compile(
        rf'(<tspan\b[^>]*\bid="{re.escape(element_id)}"[^>]*>)(.*?)(</tspan>)',
        re.DOTALL,
    )
    updated, replacements = pattern.subn(
        lambda match: f"{match.group(1)}{html.escape(value)}{match.group(3)}",
        svg,
        count=1,
    )
    if replacements != 1:
        raise ValueError(f"Could not find exactly one tspan with id={element_id}")
    return updated


def preserve_line_totals(stats: ProfileStats, previous_svg: str) -> ProfileStats:
    if stats.lines_of_code is not None:
        return stats

    values: dict[str, int] = {}
    for field, element_id in (("additions", "loc_add"), ("deletions", "loc_del")):
        pattern = re.compile(
            rf'<tspan\b[^>]*\bid="{element_id}"[^>]*>([\d,]+)</tspan>'
        )
        match = pattern.search(previous_svg)
        if not match:
            raise ValueError(f"Previous profile SVG is missing id={element_id}")
        values[field] = int(match.group(1).replace(",", ""))
    return replace(stats, **values)


def _fit_row(svg: str, anchor_id: str, dots_id: str) -> str:
    text_pattern = re.compile(
        rf'(<text\b[^>]*>)(?P<body>(?:(?!</text>).)*\bid="{re.escape(anchor_id)}"'
        rf'(?:(?!</text>).)*)(</text>)',
        re.DOTALL,
    )
    text_match = text_pattern.search(svg)
    if not text_match:
        raise ValueError(f"Could not find text row containing id={anchor_id}")

    body = text_match.group("body")
    dot_pattern = re.compile(
        rf'(<tspan\b[^>]*\bid="{re.escape(dots_id)}"[^>]*>)(.*?)(</tspan>)',
        re.DOTALL,
    )
    dot_match = dot_pattern.search(body)
    if not dot_match:
        raise ValueError(f"Could not find padding tspan with id={dots_id}")

    visible = html.unescape(re.sub(r"<[^>]+>", "", body))
    current_dots = html.unescape(dot_match.group(2))
    desired_length = len(current_dots) + LINE_COLUMNS - len(visible)
    leading_space = current_dots.startswith(" ")
    trailing_space = current_dots.endswith(" ")
    fixed_spaces = int(leading_space) + int(trailing_space)
    dot_count = desired_length - fixed_spaces
    if dot_count < 1:
        raise ValueError(f"Live values no longer fit the {LINE_COLUMNS}-column row")
    padding = f"{' ' if leading_space else ''}{'.' * dot_count}{' ' if trailing_space else ''}"
    fitted_body = dot_pattern.sub(
        lambda match: f"{match.group(1)}{padding}{match.group(3)}",
        body,
        count=1,
    )
    return f"{svg[:text_match.start('body')]}{fitted_body}{svg[text_match.end('body'):]}"


def render_profile_svg(svg: str, stats: ProfileStats) -> str:
    values = {
        "age_data": stats.uptime,
        "repo_data": f"{stats.repos:,}",
        "contrib_data": f"{stats.contributed:,}",
        "star_data": f"{stats.stars:,}",
        "commit_data": f"{stats.commits:,}",
        "follower_data": f"{stats.followers:,}",
    }
    if stats.languages is not None:
        values["lang_data"] = stats.languages
    if stats.lines_of_code is not None:
        values.update(
            {
                "loc_data": f"{stats.lines_of_code:,}",
                "loc_add": f"{stats.additions:,}",
                "loc_del": f"{stats.deletions:,}",
            }
        )
    for element_id, value in values.items():
        svg = _replace_tspan(svg, element_id, value)
    fitted_rows = [
        ("age_data", "age_data_dots"),
        ("star_data", "star_data_dots"),
        ("follower_data", "follower_data_dots"),
    ]
    if stats.languages is not None:
        fitted_rows.append(("lang_data", "lang_data_dots"))
    if stats.lines_of_code is not None:
        fitted_rows.append(("loc_data", "loc_data_dots"))
    for anchor_id, dots_id in fitted_rows:
        svg = _fit_row(svg, anchor_id, dots_id)
    return svg


def parse_args() -> argparse.Namespace:
    repository_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "Patruxs")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=repository_owner)
    parser.add_argument("--dark-svg", type=Path, default=Path("assets/dark.svg"))
    parser.add_argument("--light-svg", type=Path, default=Path("assets/light.svg"))
    parser.add_argument(
        "--previous-svg",
        type=Path,
        help="Banner snapshot used to preserve the last successful line totals",
    )
    parser.add_argument(
        "--cards-output",
        type=Path,
        default=Path("assets/profile-summary-card-output"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("ACCESS_TOKEN") or os.environ.get(
        "SUMMARY_GITHUB_TOKEN"
    ) or os.environ.get("GITHUB_TOKEN", "")
    github_client = HttpClient(token=token)
    card_client = HttpClient()

    print(f"Downloading summary cards for {args.username}...")
    card_stats, card_downloads = download_cards(
        card_client, args.username, args.cards_output
    )
    print("Fetching GitHub account and repository statistics...")
    stats = fetch_profile_stats(
        github_client,
        args.username,
        card_stats,
        dt.datetime.now(dt.timezone.utc).date(),
        os.environ.get("BIRTHDAY", ""),
    )
    if stats.lines_of_code is None and args.previous_svg:
        stats = preserve_line_totals(
            stats,
            args.previous_svg.read_text(encoding="utf-8"),
        )
    profile_downloads = {
        path: render_profile_svg(path.read_text(encoding="utf-8"), stats)
        for path in (args.dark_svg, args.light_svg)
    }
    for path, content in profile_downloads.items():
        write_atomic(path, content)
        print(f"Updated {path}")
    for path, content in card_downloads.items():
        write_atomic(path, content)
    line_summary = (
        f"{stats.lines_of_code:,}"
        if stats.lines_of_code is not None
        else "unchanged"
    )
    print(
        f"Uptime: {stats.uptime}; repos: {stats.repos:,}; "
        f"commits: {stats.commits:,}; languages: {stats.languages}; "
        f"LOC: {line_summary}"
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, RuntimeError, ET.ParseError) as error:
        print(f"Profile update failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
