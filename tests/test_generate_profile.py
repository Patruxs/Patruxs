from __future__ import annotations

import unittest

import numpy as np

from scripts.generate_profile import LOGO_MARKS, raster_logo


class LogoRasterTests(unittest.TestCase):
    def test_uses_named_react_java_and_database_icons(self) -> None:
        self.assertEqual(LOGO_MARKS, ("React", "Java", "Database"))

        masks = [raster_logo(mark) for mark in LOGO_MARKS]

        for mask in masks:
            self.assertEqual(mask.shape, (340, 300))
            self.assertGreater(np.count_nonzero(mask), 900)

        for index, mask in enumerate(masks):
            for other in masks[index + 1 :]:
                self.assertFalse(np.array_equal(mask, other))

    def test_rejects_unknown_logo_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown logo"):
            raster_logo("Unknown")


if __name__ == "__main__":
    unittest.main()
