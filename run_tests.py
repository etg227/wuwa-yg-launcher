"""Run the complete unittest suite in one process."""

import sys
import unittest

import ok.test as ok_test


def main() -> int:
    destroy_ok = ok_test.destroy_ok

    # TaskTestCase normally closes the shared QApplication after every class.
    # Keep it alive for discovery and close it once after the complete suite.
    ok_test.destroy_ok = lambda: None
    try:
        suite = unittest.defaultTestLoader.discover("tests", pattern="*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        destroy_ok()

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
