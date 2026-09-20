# 학습코칭.kr 지점안내와 코칭 가이드 (2026-09-21)

## 범위

- 홈·학습가이드·진단상담 3개 페이지를 새 원고와 공식 프로그램 이미지·영상 링크로 구성.
- 기존 전국학원/과목별학원 허브 24개에 맥락별 학습가이드·지점안내 연결 추가.
- 지점안내 1개, 지역 16개, 센터 193개 생성. 센터 아래 동네·과목 자식 페이지는 생성하지 않음.
- 기존 학원 페이지의 본문·이미지·canonical URL은 유지하고 상단 메뉴만 공통화.
- 원본 Excel·사진은 수정하지 않음. 기존 수강료 수치와 방문통계 설치 방식 유지.

## 사실·원고 관리

`centers.json`은 확인된 센터 데이터와 과목별 안내/보류 학년을 보관한다.
`course-conditions.json`은 학년 표와 비고가 상충하는 셀의 검토 근거다.
`photo-provenance.json`은 원본 사진 경로·해시·목적지·공용 여부를 기록한다.
이 파일들은 `tools/` 아래에 있으며 공개 배포에서 제외한다.

- 기존 wawa-center 데이터의 지점명·주소·등록번호·학년·학교를 최신 제공 Excel과 대조했다.
- 기존 삭제 대상 11개는 재생성하지 않았다. 별도 확인된 화성태안점을 포함해 193개이다.
- 사진: 지점 사진 96곳, 공용 사진 97곳. 공용 사진을 특정 지점 실내라고 ALT나 schema에 표기하지 않는다.
- 대표(숨김) → 본문(전체 노출) → 확인된 지도 순서. 이미지 아래 캡션은 오버레이가 아니다.
- 공통 코칭/AI 프로그램 설명은 실제 지점 개설을 증명하지 않는다. 성과·강사진·시간표·좌석·운영 실적을 추정하지 않는다.
- 설명과 상담 질문은 이 사이트용으로 새로 썼다. 주소·등록명·학교·학년 등 동일 사실은 동의어로 바꾸지 않는다.
- 검색 순위, 유사문서 판정, 리치 결과 노출은 보장하지 않는다.

## 재생성과 검사

```powershell
python -X utf8 tools/build_coaching_directory.py
python -X utf8 tools/audit_coaching_directory.py
python -X utf8 tools/audit_coaching_directory.py --base https://xn--ru4bi8s1tac0p.kr
node --check assets/coaching-directory.js
node wawa-analytics-build.mjs wawa-03 . --check
```

처음 자료를 새로 가져올 때만 `--import-source`를 사용한다. 파일 경로와 검토된 원본 해시가 다르면 먼저 근거를 확인한다. 실행할 때마다 수정일을 현재 날짜로 바꾸지 않는다. 실제 내용이 수정된 경우에만 `DAY`와 해당 페이지 변경일을 갱신한다.

## 검증

- 생성·보완 페이지 237개: 개별 title/description, canonical, H1, 이미지 ALT·크기, 내부 경로/앵커, FAQ와 구조화 데이터 일치 검사.
- 기존 4,717개 HTML을 Git 원본과 대조하여 메뉴 외 내용 보존 검사.
- 모바일 DOM 검증: 동네 검색(천호동→명일점), 결과 없음, 초기화(193개), 서울 이동(23개), FAQ·사진 펼침, 가이드 링크, 공식 영상 도착 페이지.
- 실제 CSS viewport 폭 320/360/390 및 데스크톱 1440에서 대표 화면의 가로 넘침 확인.
- 로컬 Windows 기본 HTTP 서버는 WebP를 application/octet-stream으로 응답할 수 있다. 파일 바이트는 별도로 대조하며, 공개 HTTPS 검사는 image MIME를 엄격하게 확인한다.
