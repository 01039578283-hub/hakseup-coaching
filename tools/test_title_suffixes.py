import unittest

from personalize_title_suffixes import replace_titles, masked, content_candidates, title_of


class TitleMetadataTests(unittest.TestCase):
    def test_only_three_title_fields_change(self):
        source = '''<!doctype html>\r\n<title>기존 | 이름</title>
<meta name="description" content="기존 원고">
<meta property="og:title" content="기존 | 이름">
<meta name='twitter:title' content='기존 | 이름'>
<script type="application/ld+json">{"@type":"Article","headline":"화면 제목"}</script>
<body><h1>화면 제목</h1><p>원고</p><img alt="본문" style="display:none;"></body>'''
        title = '명일동 영어학원 | 독해 & 문장 적용'
        changed = replace_titles(source, title)
        self.assertEqual(title_of(changed), title)
        self.assertEqual(masked(source), masked(changed))
        self.assertIn('headline":"화면 제목', changed)
        self.assertIn('독해 &amp; 문장 적용', changed)
        self.assertIn('\r\n', changed)
        self.assertEqual(replace_titles(changed, title), changed)

    def test_subject_guard_and_exact_visible_evidence(self):
        page = dict(parts=['과목별학원','고등영어학원','명일동'],
                    blocks=[('문장 구조와 독해 근거를 확인합니다. 첫 식과 검산도 링크에 있습니다.',4)])
        candidates = content_candidates(page)
        self.assertFalse(any(c['subject']=='math' for c in candidates))
        self.assertTrue(any(c['label']=='독해 근거 찾기' for c in candidates))
        for c in candidates:
            self.assertIn(c['match'],c['excerpt'])

    def test_no_generic_fallback_without_evidence(self):
        page = dict(parts=['과목별학원','고등수학학원','명일동'],blocks=[('내용이 없는 페이지입니다.',4)])
        self.assertEqual(content_candidates(page),[])

    def test_high_school_exam_not_used_for_younger_grades(self):
        for category in ('초등학생학원','중학생학원','중등영어학원'):
            page=dict(parts=['과목별학원',category,'명일동'],
                      blocks=[('내신과 모의고사를 구분하고 오답 유형을 확인합니다.',5)])
            self.assertNotIn('내신·모의고사 구분',[c['label'] for c in content_candidates(page)])

    def test_missing_or_duplicate_title_rejected(self):
        for source in ('<h1>제목 없음</h1>','<title>1</title><title>2</title>'):
            with self.assertRaises(ValueError):
                replace_titles(source,'새 제목')


if __name__=='__main__':
    unittest.main()
