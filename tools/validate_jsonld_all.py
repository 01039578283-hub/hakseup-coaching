from __future__ import annotations

import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]


def main() -> None:
    bad = 0
    count = 0
    for f in SITE.glob("**/index.html"):
        if ".git" in f.parts or ".vercel" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
            count += 1
            try:
                json.loads(m.group(1))
            except Exception as exc:  # noqa: BLE001
                bad += 1
                print("BAD", f, exc)
    print(f"checked={count} bad={bad}")


if __name__ == "__main__":
    main()
