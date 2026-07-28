import unittest

from scripts.fetch_data import (
    CONFIG,
    LINE_WIDTH,
    RULE_WIDTH,
    build_rows,
    load_config,
    render_segments,
)


def rendered_text(kind: str, **kwargs: str) -> str:
    return "".join(segment[1] for segment in render_segments(kind, **kwargs))


class AlignmentTest(unittest.TestCase):
    def test_section_rules_end_at_the_same_column(self) -> None:
        rows = [
            rendered_text("head", host="patruxs@devos"),
            rendered_text("section", title="Contact"),
            rendered_text("section", title="GitHub Stats"),
        ]

        self.assertEqual([RULE_WIDTH] * len(rows), [len(row) for row in rows])

    def test_content_rows_end_at_the_same_column(self) -> None:
        config = load_config(CONFIG)
        rows = build_rows(
            config,
            lang_chunks=["TypeScript · Java · HTML · CSS +13"],
        )
        content_rows = [
            "".join(segment[1] for segment in row)
            for row in rows
            if row[0][0] not in {"head", "accent"} and row != [("cc", ". ")]
        ]

        self.assertEqual(
            [LINE_WIDTH] * len(content_rows),
            [len(row) for row in content_rows],
        )

    def test_build_rows_keeps_existing_stats_without_a_token(self) -> None:
        stats = {
            "repos": "15",
            "contrib": "17",
            "stars": "0",
            "commits": "424",
            "followers": "2",
            "loc": "362,091",
            "loc_add": "501,721",
            "loc_del": "139,630",
        }

        rows = build_rows(load_config(CONFIG), github_stats=stats)
        rendered = "".join(segment[1] for row in rows for segment in row)

        for value in stats.values():
            self.assertIn(value, rendered)


if __name__ == "__main__":
    unittest.main()
