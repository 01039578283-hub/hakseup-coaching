import re

import audit_high_math_subject_pages as audit
from generate_middle_subject_pages import configure


audit.generator = configure("math")
audit.TARGET = audit.ROOT / "과목별학원" / audit.generator.CATEGORY
audit.FORBIDDEN = re.compile(audit.FORBIDDEN.pattern + r"|중등중등|중1·중2·중3·중1", re.I)


if __name__ == "__main__":
    raise SystemExit(audit.main())
