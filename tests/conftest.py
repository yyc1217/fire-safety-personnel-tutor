"""讓測試能 import `skills/spaced-repetition/` 下的模組。

該目錄名含連字號、不是合法的 package 名（plugin 的 skill 目錄名由 Claude Code
決定，不能為了 import 而改），故以 sys.path 直接掛入該目錄。
"""

from __future__ import annotations

import sys
from pathlib import Path

SR_DIR = Path(__file__).resolve().parent.parent / "skills" / "spaced-repetition"
if str(SR_DIR) not in sys.path:
    sys.path.insert(0, str(SR_DIR))
