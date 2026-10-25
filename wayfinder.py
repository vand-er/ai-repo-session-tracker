"""Launch the Wayfinder board from any folder: python ~/code/wayfinder-board/wayfinder.py [flags].

`python -m src` only works with the repo root as the current folder; this puts the repo root on the path first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.__main__ import main  # noqa: E402  (needs the path above)

if __name__ == "__main__":
    main()
