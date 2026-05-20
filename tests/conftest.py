import sys
from pathlib import Path


def pytest_configure() -> None:
    src = str(Path(__file__).resolve().parent.parent / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
