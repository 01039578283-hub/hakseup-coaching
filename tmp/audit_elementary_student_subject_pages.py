from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "tmp" / "audit_middle_student_subject_pages.py"
spec = importlib.util.spec_from_file_location("subject_audit_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load {BASE_SCRIPT}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.CATEGORY = "초등학생학원"
base.TARGET = ROOT / "과목별학원" / base.CATEGORY


if __name__ == "__main__":
    base.main()
