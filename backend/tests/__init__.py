"""Backend unit tests package. Ensures backend directory is on sys.path."""

import sys
from pathlib import Path

backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
