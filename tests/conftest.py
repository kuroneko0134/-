"""Make ``src`` and the test helpers importable without installing the package."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT / "src", Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
