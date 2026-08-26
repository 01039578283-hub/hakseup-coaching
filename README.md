# 새 홈페이지2

새로운 학원 홈페이지 뼈대입니다.

현재 구성:

- 홈
- 학습관리
- 진단상담
- 학습가이드
- 전국학원
- 상담문의

메모:

- 371개 동네 페이지는 추후 `전국학원/` 하위로 확장하는 구조를 권장합니다.
- 도메인이 정해지면 canonical, OG URL, sitemap, 검색엔진 인증 메타태그를 추가하면 됩니다.
- 검색 노출용 사이트명은 `학습코칭 학원 안내`이며, 화면 헤더에는 짧게 `학습코칭`을 표시합니다.
- 대량 페이지 생성 시 FAQ, 후기, JSON-LD, 이미지 alt 규칙은 `tmp/PAGE_GENERATION_RULES.md`를 기준으로 적용합니다.
- FAQ/후기 문구 풀은 `tmp/page_content_pool.json`에 저장되어 있으며, 기존 홈페이지 문구를 그대로 복사하지 않고 새 홈페이지2 톤에 맞춰 각색해서 사용합니다.

내부 링크 릴리스 순서:

1. 페이지 생성·수정이 끝난 뒤 `python -B tools/strengthen_internal_links.py --apply`를 실행합니다.
2. `python -B tools/strengthen_internal_links.py`가 `changed: 0`, `errors: 0`인지 확인합니다.
3. `python -B tools/audit_internal_link_network.py`가 `ok: true`인지 확인합니다.

이 후처리는 371개 지역마다 과목별 8개 페이지와 전국학원 4개 페이지를 하나의 12페이지 네트워크로 연결합니다. 생성기를 다시 실행했다면 배포 전에 반드시 다시 실행해야 합니다.

센터 상세 페이지 릴리스 순서:

1. `python -B tools/generate_wawa_center_pages.py --apply`로 187개 지점 본문을 생성합니다.
2. `python -B tools/generate_wawa_center_pages.py`가 `changed: 0`인지 확인합니다.
3. `python -B tools/audit_wawa_center_pages.py`가 `errors: 0`인지 확인합니다.

센터 본문은 주소·위치안내·과목별 가능 학년·학교 참고 자료를 지점별 근거로 사용합니다. 원자료에 없는 학년, 학교, 운영 내용은 추정해 추가하지 않습니다.

중등 핵심 과목 742개 릴리스 순서:

1. 중등영어·중등수학 생성기와 학교 원고 후처리를 먼저 끝냅니다.
2. 내부 링크 후처리 뒤 `python -B tools/differentiate_priority_subject_pages.py --apply`를 마지막으로 실행합니다.
3. 같은 명령을 `--apply` 없이 다시 실행해 `changed: 0`, `errors: 0`인지 확인합니다.
4. `python -B tools/audit_national_naver_strict.py`와 전체 JSON-LD·화면 일치 감사를 통과한 뒤 배포합니다.

이 후처리는 371개 중등영어학원 페이지와 371개 중등수학학원 페이지에 진단·학교 내신·첫 2주·상담 판단 기준을 추가합니다. 학교 원자료 블록과 canonical은 보존하며, 화면의 네 질문과 `#priority-search-intent` ItemList를 동일하게 유지합니다. 임시 이전 릴리스 manifest는 엄격 감사의 기본 필수 조건이 아니며, 이전 URL 세트 동결을 의도적으로 검사할 때만 `--require-baseline`을 사용합니다.
