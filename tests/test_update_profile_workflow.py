import unittest
from pathlib import Path


class UpdateProfileWorkflowTests(unittest.TestCase):
    def test_workflow_updates_existing_svgs_without_a_portrait(self) -> None:
        workflow = Path(".github/workflows/update-profile.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("assets/portrait.png", workflow)
        self.assertNotIn("generate_profile.py", workflow)


if __name__ == "__main__":
    unittest.main()
