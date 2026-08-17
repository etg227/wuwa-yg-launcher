import tempfile
import unittest
from pathlib import Path

from packaging_meta import project_version, runtime_requirements


class TestPackagingMetadata(unittest.TestCase):
    def test_development_version_is_valid_pep440(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "config.py")
            config.write_text('version = "dev"\n', encoding="utf-8")
            self.assertEqual(project_version(config), "0.0.0.dev0")

    def test_release_version_comes_from_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "config.py")
            config.write_text('version = "v1.2.3"\n', encoding="utf-8")
            self.assertEqual(project_version(config), "1.2.3")

    def test_requirements_ignore_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory, "requirements.in")
            requirements.write_text("# runtime\nok-script\n\nrequests>=2\n", encoding="utf-8")
            self.assertEqual(runtime_requirements(requirements), ["ok-script", "requests>=2"])


if __name__ == "__main__":
    unittest.main()
