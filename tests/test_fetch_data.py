from __future__ import annotations

import datetime as dt
import html
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.fetch_data import (
    HttpClient,
    ProfileStats,
    account_age,
    fetch_languages,
    fetch_line_totals,
    fetch_profile_stats,
    format_languages,
    parse_card_stats,
    preserve_line_totals,
    render_profile_svg,
)


class HttpClientTests(unittest.TestCase):
    def test_only_adds_authorization_header_when_given_a_token(self) -> None:
        class Response:
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"{}"

        with patch("scripts.fetch_data.urllib.request.urlopen", return_value=Response()) as urlopen:
            HttpClient().get("https://cards.example/stats")
            tokenless_request = urlopen.call_args.args[0]
            HttpClient(token="secret").get("https://api.github.com/user")
            authenticated_request = urlopen.call_args.args[0]

        self.assertIsNone(tokenless_request.get_header("Authorization"))
        self.assertEqual(
            authenticated_request.get_header("Authorization"),
            "Bearer secret",
        )


class AccountAgeTests(unittest.TestCase):
    def test_formats_calendar_age(self) -> None:
        self.assertEqual(
            account_age(dt.date(2021, 9, 7), dt.date(2026, 7, 29)),
            "4 years, 10 months, 22 days",
        )

    def test_handles_leap_day_anniversary(self) -> None:
        self.assertEqual(
            account_age(dt.date(2020, 2, 29), dt.date(2021, 3, 1)),
            "1 year, 1 day",
        )

    def test_profile_stats_prefers_birthday_override(self) -> None:
        class Client:
            def get_json(self, url: str) -> object:
                if url.endswith("/users/Patruxs"):
                    return {
                        "created_at": "2021-09-07T05:41:30Z",
                        "public_repos": 0,
                        "followers": 2,
                    }
                if "/users/Patruxs/repos?" in url:
                    return []
                raise AssertionError(url)

        with patch("scripts.fetch_data.fetch_line_totals", return_value=(1, 0)):
            stats = fetch_profile_stats(
                Client(),
                "Patruxs",
                {"contributed": 3, "stars": 4, "commits": 5},
                dt.date(2026, 7, 29),
                "2002-07-05",
            )

        self.assertEqual(stats.uptime, "24 years, 24 days")

    def test_rejects_invalid_birthday_override(self) -> None:
        class Client:
            def get_json(self, _url: str) -> object:
                raise AssertionError("Invalid input should fail before API requests")

        with self.assertRaisesRegex(ValueError, "BIRTHDAY must use YYYY-MM-DD"):
            fetch_profile_stats(
                Client(),
                "Patruxs",
                {"contributed": 3, "stars": 4, "commits": 5},
                dt.date(2026, 7, 29),
                "July 5",
            )


class CardStatsTests(unittest.TestCase):
    def test_reads_values_by_label_instead_of_position(self) -> None:
        card = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <text>Total Commits:</text><text>612</text>
          <text>Total Stars:</text><text>9</text>
          <text>Contributed to:</text><text>14</text>
        </svg>
        """

        self.assertEqual(
            parse_card_stats(card),
            {"commits": 612, "stars": 9, "contributed": 14},
        )


class ProfileSvgTests(unittest.TestCase):
    def test_updates_all_live_values_and_keeps_rows_at_79_columns(self) -> None:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg">
          <g><text><tspan>. </tspan><tspan>Uptime</tspan><tspan>:</tspan><tspan id="age_data_dots"> .... </tspan><tspan id="age_data">old</tspan></text></g>
          <g><text><tspan>. </tspan><tspan>Repos</tspan><tspan>:</tspan><tspan id="repo_data_dots"> .... </tspan><tspan id="repo_data">1</tspan><tspan> {Contributed: </tspan><tspan id="contrib_data">2</tspan><tspan>} | Stars:</tspan><tspan id="star_data_dots"> .... </tspan><tspan id="star_data">3</tspan></text></g>
          <g><text><tspan>. Commits:</tspan><tspan id="commit_data_dots"> .... </tspan><tspan id="commit_data">4</tspan><tspan> | Followers:</tspan><tspan id="follower_data_dots"> .... </tspan><tspan id="follower_data">5</tspan></text></g>
          <g><text><tspan>. Lines of Code on GitHub:</tspan><tspan id="loc_data_dots">.... </tspan><tspan id="loc_data">6</tspan><tspan> ( </tspan><tspan id="loc_add">7</tspan><tspan>++, </tspan><tspan id="loc_del_dots"></tspan><tspan id="loc_del">8</tspan><tspan>-- )</tspan></text></g>
          <g><text><tspan>. Lang:</tspan><tspan id="lang_data_dots"> .... </tspan><tspan id="lang_data">old</tspan></text></g>
        </svg>
        """
        stats = ProfileStats(
            uptime="4 years, 10 months, 22 days",
            repos=11,
            contributed=12,
            stars=0,
            commits=576,
            followers=2,
            additions=510_165,
            deletions=149_272,
            languages="TypeScript · Java · HTML · CSS +14",
        )

        updated = render_profile_svg(svg, stats)

        for expected in (
            'id="age_data">4 years, 10 months, 22 days<',
            'id="repo_data">11<',
            'id="contrib_data">12<',
            'id="star_data">0<',
            'id="commit_data">576<',
            'id="follower_data">2<',
            'id="loc_data">360,893<',
            'id="loc_add">510,165<',
            'id="loc_del">149,272<',
            'id="lang_data">TypeScript · Java · HTML · CSS +14<',
        ):
            self.assertIn(expected, updated)

        for anchor in (
            "age_data",
            "star_data",
            "follower_data",
            "loc_data",
            "lang_data",
        ):
            match = re.search(
                rf'<text\b[^>]*>((?:(?!</text>).)*id="{anchor}"'
                rf"(?:(?!</text>).)*)</text>",
                updated,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            visible = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
            self.assertEqual(len(visible), 79)

    def test_preserves_line_values_when_statistics_are_unavailable(self) -> None:
        svg = Path("assets/dark.svg").read_text(encoding="utf-8")
        stats = ProfileStats("1 day", 11, 12, 0, 576, 2, None, None)
        updated = render_profile_svg(svg, stats)

        for element_id in ("loc_data", "loc_add", "loc_del"):
            pattern = rf'id="{element_id}">([^<]+)'
            before = re.search(pattern, svg)
            after = re.search(pattern, updated)
            self.assertIsNotNone(before)
            self.assertIsNotNone(after)
            self.assertEqual(before.group(1), after.group(1))

    def test_restores_last_published_line_values_after_generation(self) -> None:
        previous = Path("assets/dark.svg").read_text(encoding="utf-8")
        unavailable = ProfileStats("1 day", 11, 12, 0, 576, 2, None, None)

        restored = preserve_line_totals(unavailable, previous)

        additions = re.search(r'id="loc_add">([\d,]+)', previous)
        deletions = re.search(r'id="loc_del">([\d,]+)', previous)
        self.assertEqual(restored.additions, int(additions.group(1).replace(",", "")))
        self.assertEqual(restored.deletions, int(deletions.group(1).replace(",", "")))


class LineTotalsTests(unittest.TestCase):
    def test_returns_none_when_one_repository_never_becomes_available(self) -> None:
        class UnavailableClient:
            def get_json(self, _url: str) -> dict[str, object]:
                return {}

        with patch("scripts.fetch_data.time.sleep"):
            totals = fetch_line_totals(
                UnavailableClient(),
                "Patruxs",
                [{"full_name": "Patruxs/empty"}],
            )

        self.assertIsNone(totals)


class LanguageTests(unittest.TestCase):
    def test_aggregates_owned_non_fork_repositories_by_code_size(self) -> None:
        class Client:
            def get_json(self, url: str) -> dict[str, int]:
                return {
                    "https://api.github.com/repos/Patruxs/one/languages": {
                        "Java": 10,
                        "TypeScript": 50,
                    },
                    "https://api.github.com/repos/Patruxs/two/languages": {
                        "Java": 100,
                        "HTML": 20,
                        "CSS": 5,
                        "Shell": 1,
                    },
                }[url]

        languages = fetch_languages(
            Client(),
            [
                {"full_name": "Patruxs/one", "fork": False},
                {"full_name": "Patruxs/two", "fork": False},
                {"full_name": "Patruxs/fork", "fork": True},
            ],
        )

        self.assertEqual(languages, "Java · TypeScript · HTML · CSS +1")

    def test_language_summary_shrinks_to_fit_the_generated_row(self) -> None:
        names = ["A" * 40, "B" * 40, "C", "D", "E"]

        value = format_languages(names)

        self.assertEqual(value, f"{'A' * 40} +4")


if __name__ == "__main__":
    unittest.main()
