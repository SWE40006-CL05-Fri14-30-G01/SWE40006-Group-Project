"""Mandatory suites must contain tests with no failures, errors or skips."""
import sys
from xml.etree import ElementTree


def check(path):
    root = ElementTree.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases or any(case.find(tag) is not None for case in cases
                        for tag in ("failure", "error", "skipped")):
        raise ValueError("Mandatory suite missing, failed or skipped: " + str(path))


if __name__ == "__main__":
    for path in sys.argv[1:]:
        check(path)
