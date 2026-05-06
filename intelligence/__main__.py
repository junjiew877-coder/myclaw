"""`python -m intelligence` → 终端 REPL（委托 `entrypoints.main`）。"""

from __future__ import annotations

from .entrypoints.main import main

if __name__ == "__main__":
    main()
