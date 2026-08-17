import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_large_files.py"


class TestLargeFileCheck(unittest.TestCase):
    def test_chinese_large_filename_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(("git", "init", "--quiet"), cwd=repository, check=True)
            large_file = repository / "中文模型.onnx"
            with large_file.open("wb") as stream:
                stream.truncate(26 * 1024 * 1024)
            subprocess.run(("git", "add", "中文模型.onnx"), cwd=repository, check=True)

            result = subprocess.run(
                (sys.executable, str(SCRIPT)),
                cwd=repository,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("中文模型.onnx", result.stderr)


if __name__ == "__main__":
    unittest.main()
