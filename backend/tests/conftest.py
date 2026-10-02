from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend directory is in sys.path for pytest runs from any directory
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
