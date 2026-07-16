import unittest

from scripts.update_system_info import (
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


if __name__ == "__main__":
    unittest.main()
