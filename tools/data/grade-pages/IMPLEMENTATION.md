# 학년별 학습 안내 확장 — 2026-09-21

- 도메인: 학습코칭.kr (`https://xn--ru4bi8s1tac0p.kr`). 기존 지점/과목 주소 보존.
- 새 학년 글 6,678개: 371개 동네 × 영어·수학 × 초3/초4/초5/초6/중1/중2/중3/고1/고2.
- 상위 동네별 과목 안내 742개에 FAQ 바로 아래 학년 선택 링크 9개씩 추가.
- 지점안내 루트 1, 지역 16, 실제 지점 193. 기존 188개 지점의 371개 동네 연결을 유지.
- 18개 원고 파일은 읽기 전용. 각 파일 Sheet1 A1:A371의 물리 행을 유지하며 오류 셀 때문에 순서를 당기지 않음.
- 중3 영어 A97, 고2 수학 A140/A210/A240/A274/A304/A310은 `#ERROR!`. 해당 동네의 검증된 과목 안내와 새 학년별 학습 예시로 대체 작성. 원본 엑셀에는 쓰지 않음.
- 지역명 오류·별칭 214건과 오류 셀 7건을 합해 221개 매핑 검토 기록. 봉담3지구 원고 표현은 기존 검증된 봉담2지구 연결로 바로잡음. 잘못된 도·시·지점/성과/강사 주장은 가져오지 않음.
- 원고 키워드로 두 가지 학습 점검을 선택하고, 18개 학년·과목별 별도 원고/예시/복습 기준에 결합. 일부 공통 안내는 공유하며 문서 전체가 모두 고유하거나 검색 노출이 보장된다고 주장하지 않음.
- 개설 학년: 6,277개 확인, 35개 조건 확인, 366개 목록 미표시. 뒤의 401개는 학습 안내와 개설 사실을 명확히 구분하고 해당 학년 Service를 생성하지 않음.
- 실제 EducationalOrganization/LocalBusiness @id는 지점 URL을 사용. 학년 페이지 WebPage/Article/FAQPage/BreadcrumbList/ItemList는 각 페이지 주소에 귀속. 확인된 수업만 Service를 생성.
- canonical/og:url/제목/설명과 첫 답변을 대조. Article abstract는 보이는 첫 요약과 동일. datePublished/dateModified는 실제 생성일, 단순 빌드 시 날짜를 갱신하지 않음.
- 이미지: 상단 첫 요약 다음, GRADE LEARNING 바로 위에 대표(숨김) → 본문(전체 표시) → 검증된 지점 지도 순으로 배치. 기존 자산 재사용. ALT는 학년별 페이지명 + 대표이미지/본문/지도. 이미지 접기·자르기 없음.
- 내부 링크는 과목 부모, 실제 지점, 같은 동네·같은 학년의 다른 과목, 앞뒤 학년으로 4~5개. 모든 학년을 모든 글에 반복 나열하지 않음.
- 사이트맵 전체 12,373 URL, RSS 최근 50개(새 학년 글 30개 전체 본문 포함), llms 탐색 안내 갱신. robots 기존 정책 유지.

## 재생성 / 검증

1. `python -X utf8 tools/build_grade_pages.py` (엑셀 다시 읽기) 또는 `--reuse-manifest`.
2. 기존 `build_subject_pages.py` 및 전체 디렉터리 빌드에도 학년 재생성 훅을 연결.
3. `python -X utf8 tools/audit_subject_pages.py`
4. `python -X utf8 tools/audit_grade_pages.py --base http://127.0.0.1:8850`
5. `python -X utf8 tools/verify_grade_repeatability.py`
6. 배포 후 `python -X utf8 tools/audit_grade_pages.py --base https://xn--ru4bi8s1tac0p.kr --public`
7. `python -X utf8 tools/export_branch_grade_urls.py`는 공개 사이트맵과 완전히 일치할 때만 바탕화면 TXT를 생성.

TXT 순서: 메인 → 지점안내 → 모든 지역 → 모든 지점 → 모든 동네별 과목 허브 → 각 과목 허브의 초3~고2. 지역은 메뉴 순서, 지점/동네는 가나다순. 한글 도메인과 경로, 7,631줄. 다른 전국학원/과목별학원 경로는 포함하지 않음.

이 폴더와 tools/reports/tmp는 `.vercelignore`로 공개 배포 제외. 관리자 키나 원본 엑셀을 공개 HTML에 포함하지 않음.
