"""Small regression tests for source cleanup and repeatable editorial output."""
import copy
import unittest
from unittest.mock import patch
from lxml import html
import refine_branch_guides as r


class RefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.centers=r.READ(r.base.DATA/'centers.json')['centers']
        cls.by_name={c['routeName']:c for c in cls.centers}

    def test_source_is_not_mutated(self):
        original=copy.deepcopy(self.centers)
        for center in self.centers:r.school_view(center)
        self.assertEqual(original,self.centers)

    def test_physical_address_is_not_navigation_region(self):
        wirye=self.by_name['위례점']
        self.assertEqual(wirye['region'],'서울')
        self.assertEqual(r.physical_region(wirye),'경기')
        self.assertEqual(r.physical_region(self.by_name['개신점']),'충북')

    def test_school_annotations_and_duplicate_aliases(self):
        for center in self.centers:
            schools,_=r.school_view(center)
            for names in schools.values():
                self.assertEqual(len(names),len(set(names)))
                self.assertFalse(any('[' in n or ']' in n or '후보' in n for n in names))
        schools,_=r.school_view(self.by_name['상암점'])
        self.assertIn('덕은한강중학교',schools['중등'])
        self.assertNotIn('덕은한강중',schools['중등'])
        schools,_=r.school_view(self.by_name['풍동점'])
        self.assertIn('일산양일중학교',schools['중등'])
        self.assertNotIn('양일중',schools['중등'])

    def test_course_conditions_unchanged(self):
        records=r.READ(r.grade.DATA/'manifest.json')['records']
        lookup={r.base.route(c):c for c in self.centers}
        counts=r.Counter(r.state(lookup[row['branchPath']],row) for row in records)
        self.assertEqual(dict(counts),{'confirmed':6277,'pending':35,'unlisted':366})

    def test_school_fragment_repair_is_idempotent(self):
        old=self.by_name['위례점'];center=copy.deepcopy(old)
        center['schools'],_=r.school_view(center)
        doc=html.fromstring('<html><body><main><section id="learning"><article><h3>영어 상담에 준비할 내용</h3><p>고운초등학교 [후보 지역: 세종 세종시]</p></article></section><details class="hc-faq"><summary>영어 상담을 준비할 때 어떤 학교 자료가 필요한가요?</summary><p>고운초등학교 [후보 지역: 세종 세종시]</p></details></main></body></html>')
        r.apply_schools(doc,[],center,old)
        once=html.tostring(doc)
        r.apply_schools(doc,[],center,old)
        self.assertEqual(once,html.tostring(doc))
        self.assertNotIn('후보',doc.text_content())

    def test_finish_does_not_duplicate_links_or_change_dates(self):
        path='/지점안내/서울/명일점/'
        center=self.by_name['명일점'];doc=r.read_doc(path)
        _,graph=r.subject.graph_of(doc)
        r.NEW_PATHS=[]
        with patch.object(r.subject,'save_document'):
            r.finish(path,doc,graph,center,r.DAY)
            once=(html.tostring(doc),copy.deepcopy(graph))
            r.finish(path,doc,graph,center,r.DAY)
        self.assertEqual(once,(html.tostring(doc),graph))
        policies=[a for a in doc.xpath('//footer//nav/a/@href') if r.unquote(a)==r.POLICY]
        self.assertEqual(len(policies),1)

    def test_search_uses_cleaned_schools(self):
        center=copy.deepcopy(self.by_name['위례점'])
        center['schools'],_=r.school_view(center)
        doc=html.fromstring(r.base.branch_card(self.by_name['위례점']))
        r.search_keywords(doc,{r.base.route(center):center})
        self.assertNotIn('후보',doc.get('data-center-keywords'))
        self.assertNotIn('세종',doc.get('data-center-keywords'))


if __name__=='__main__':unittest.main(verbosity=2)
