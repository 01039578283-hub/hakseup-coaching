/** Give existing editorial areas a concrete reader task, using their own sources. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(fs.readFileSync(path.join(here,'page-roles-config.json')));
const maps=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'))).pages;
const profiles=JSON.parse(fs.readFileSync(path.join(here,'local-content-config.json'))).centers;
const marker=`<!-- page-roles:${config.version} -->`;
const plain=s=>s.replace(/<[^>]+>/g,' ').replaceAll('&amp;','&').replaceAll('&nbsp;',' ').replace(/\s+/g,' ').trim();
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const inside=(n,p)=>p&&n.start>p.start&&n.end<p.end;
const hash=s=>createHash('sha256').update(s.replaceAll('\r\n','\n')).digest('hex');
const gradeList=t=>[...new Set(plain(t).match(/(?:초[1-6]|중[1-3]|고[1-3])/g)||[])];
const join=arr=>arr.length?arr.join(' · '):'기재 학년 없음';
function roleFor(p,m,ns){return p===m.branchPath?'branch':ns.some(n=>has(n,'center-profile-flow'))&&ns.some(n=>has(n,'center-profile-context'))?'center-profile':ns.some(n=>n.a.id==='grade-focus')?'grade-consultation':ns.some(n=>n.a.id==='subject-courses')?'subject-offering':ns.some(n=>has(n,'subject-local-hero'))?'subject-guide':ns.some(n=>has(n,'seo-answer-section'))?'neighborhood-choice':null}
export function branchFacts(s){
 const ns=nodes(s),out={};
 for(const n of ns.filter(n=>n.tag==='p'&&n.a['data-fact-subject']))out[n.a['data-fact-subject']]={grades:gradeList(s.slice(n.open,n.close)),text:plain(s.slice(n.open,n.close)),status:n.a['data-fact-status']};
 if(!out['영어']||!out['수학'])throw Error('Missing published branch course facts');return out;
}
function sourceSchools(s,ns,band){
 const sections=ns.filter(n=>n.tag==='div'&&has(n,'regional-school-list')&&!has(n,'hc-merged-information'));
 const names=[];
 for(const sec of sections){
  const heading=ns.find(n=>/^h[23]$/.test(n.tag)&&inside(n,sec));const title=heading&&plain(s.slice(heading.open,heading.close));
  if(band&&(!title||!title.startsWith({'초':'초등','중':'중학교','고':'고등'}[band])))continue;
  for(const n of ns.filter(n=>inside(n,sec)&&n.a['data-source-school']))names.push(n.a['data-source-school']);
 }
 if(!names.length)for(const n of ns.filter(n=>n.a['data-source-school'])){const v=n.a['data-source-school'];if(!band||v.endsWith({'초':'초등학교','중':'중학교','고':'고등학교'}[band]))names.push(v)}
 return [...new Set(names)];
}
function comparison(facts,band){
 const eg=facts['영어'].grades.filter(g=>!band||g.startsWith(band)),mg=facts['수학'].grades.filter(g=>!band||g.startsWith(band));
 const both=eg.filter(g=>mg.includes(g)),eo=eg.filter(g=>!mg.includes(g)),mo=mg.filter(g=>!eg.includes(g));
 let text=both.length?`영어·수학 두 자료에 함께 기재된 학년은 ${join(both)}입니다.`:'이 범위에서는 영어·수학 두 자료에 함께 기재된 학년을 확인하지 못했습니다.';
 if(eo.length)text+=` 영어에만 기재된 학년은 ${join(eo)}입니다. 수학도 함께 문의한다면 별도 확인이 필요합니다.`;
 if(mo.length)text+=` 수학에만 기재된 학년은 ${join(mo)}입니다. 영어도 함께 문의한다면 별도 확인이 필요합니다.`;
 if(!both.length&&!eo.length&&!mo.length)text+=' 먼저 희망 학년과 필요한 과목의 개설 자료를 지점에 요청하세요.';
 return {text,eg,mg,both,eo,mo};
}
const material={
 '초':{label:'초등',school:'학교에서 받은 학습 안내와 최근 과제',record:'혼자 읽거나 푼 부분과 보호자가 도운 부분을 나누어 표시하세요.',question:'학생이 혼자 시작할 활동과 도움을 줄 시점'},
 '중':{label:'중등',school:'학교의 최신 시험·수행평가 안내와 현재 교재',record:'평가 범위의 단원·문제 요구 조건과 처음 쓴 답을 나란히 적으세요.',question:'지필평가 복습과 수행평가 준비를 나눌 기준'},
 '고':{label:'고등',school:'실제로 이수하는 과목명·학교의 평가 범위와 현재 교재',record:'문제의 조건·근거를 적고 답을 수정했다면 바꾼 이유를 남기세요.',question:'현재 이수 과목 안에서 먼저 보완할 범위'}
};
function localSchoolQuestion(names,band){
 const m=material[band]||{school:'재학 학교의 최신 안내와 현재 교재',record:'혼자 해결한 부분과 설명이 막힌 부분을 표시하세요.'};
 const origin=names.length?`참고 자료에 적힌 학교는 ${names.slice(0,2).join('·')}${names.length>2?' 등':''}입니다.`:'이 범위의 학교 이름은 자료만으로 확정하지 않습니다.';
 return `${origin} ${m.school}를 준비하세요. ${m.record} 참고 학교의 이름만으로 학생의 진도·전용반·현재 모집을 판단하지 마세요.`;
}
function teacherQuestion(center){
 const t=center?.teachers?.[0];
 return t?`공개 교사 소개의 ‘${t.focus}’ 관점으로 학생 기록에서 다시 확인할 대목을 골라 보세요. 상담에서는 다음 활동과 완료 기준을 질문하고 답변을 남깁니다. 소개에 이름이 있어도 실제 담당 학년·과목과 배정은 별도 확인합니다.`:'공개 소개만으로 담당 교사를 확정할 수 없습니다. 희망 학년·과목의 상담 가능 여부와 실제 담당 정보를 먼저 확인하고, 다음 활동·완료 기준·확인 날짜를 기록하세요.';
}
export function clarify(before,p,facts){
 const m=maps[p],changes=[],replacements=[],evidence={};
 if(!m||before.includes(marker))return {after:before,changes,replacements,evidence};
 const ns=nodes(before),role=roleFor(p,m,ns);if(!role)throw Error('Unclassified mapped page '+p);
 const heading=ns.find(n=>n.tag==='h1'),title=plain(before.slice(heading.open,heading.close));
 const grade=title.match(/(?:초[1-6]|중[1-3]|고[1-3])/g)?.[0]||null;
 const band=grade?.[0]||(title.includes('초등')?'초':title.includes('중등')||title.includes('중학생')?'중':title.includes('고등')?'고':null);
 const subject=title.includes('영어')&&!title.includes('수학')?'영어':title.includes('수학')&&!title.includes('영어')?'수학':null;
 const center=profiles[m.branchPath];if(!center)throw Error('Missing matched center '+p);
 const schools=sourceSchools(before,ns,band),comp=comparison(facts,band);Object.assign(evidence,{role,branch:m.branchPath,branchName:center.branch,grade,band,subject,schoolNames:schools,english:comp.eg,math:comp.mg,profileRow:center.teachers?.[0]?.sourceRow||null});
 const edits=[];
 function replace(n,html,kind){
  if(!n||/<(?:a|img|iframe|time|span)\b/.test(before.slice(n.open,n.close)))throw Error('Unsafe editorial replacement '+p+' '+kind);
  replacements.push({oldText:plain(before.slice(n.open,n.close)),newText:plain(html),kind});
  edits.push([n.open,n.close,html]);changes.push(kind);
 }
 const section=id=>ns.find(n=>n.tag==='section'&&n.a.id===id);
 const classSection=c=>ns.find(n=>n.tag==='section'&&has(n,c));
 const prose=n=>ns.filter(a=>a.tag==='p'&&inside(a,n)&&!has(a,'hc-kicker')&&!has(a,'regional-purpose'));
 if(role==='branch'){
  const sec=section('learning'),n=prose(sec)[0];
  replace(n,`${esc(center.branch)}에서 영어와 수학을 함께 알아본다면 과목별 학년 차이부터 확인하세요. ${esc(comp.text)} 아래의 과목별 준비 자료로 학생의 첫 답안을 정리하고, 현재 모집·수업 범위는 별도로 질문하세요.`,'branch-course-decision');
 }else if(role==='center-profile'){
  const sec=classSection('center-profile-flow'),cards=ns.filter(n=>n.tag==='article'&&inside(n,sec));if(cards.length!==3)throw Error('Profile flow contract '+p);
  const first=prose(cards[0])[0],second=prose(cards[1])[0];
  replace(first,`${before.slice(first.open,first.close)} ${esc(center.branch)}의 자료를 먼저 대조하세요. ${esc(comp.text)} 기재 학년이 같더라도 학생의 현재 교재·진도와 등록 가능한 요일은 따로 확인합니다.`,'profile-course-fit');
  replace(second,`${before.slice(second.open,second.close)} ${esc(teacherQuestion(center))}`,'profile-record-question');
 }else if(role==='subject-offering'){
  const sec=section('prepare-records'),n=prose(sec)[0];if(!subject)throw Error('Missing offering subject '+p);
  const gs=facts[subject].grades;
  const status=gs.length?`${center.branch} ${subject} 자료의 기재 학년은 ${join(gs)}입니다.`:`${center.branch} ${subject} 자료의 기재 학년을 확인하지 못했습니다.`;
  replace(n,`${esc(status)} 먼저 학생의 학년이 이 범위에 있는지 아래 학년별 안내와 대조하세요. 포함되어 있어도 현재 모집·요일·교재 범위는 확정되지 않으며, 미기재 학년은 개설 불가로 단정하지 말고 따로 질문하세요. 학년을 고른 뒤에는 위 학습 점검에서 처음 쓴 답과 막힌 부분을 준비합니다.`,'offering-grade-decision');
 }else if(role==='grade-consultation'){
  if(!grade||!subject)throw Error('Missing grade subject '+p);
  const n=prose(section('grade-center'))[0],listed=facts[subject].grades.includes(grade);
  replace(n,`${esc(center.branch)}의 ${esc(grade+' '+subject)}${subject==='수학'?'은':'는'} 제공 자료에 ${listed?'기재되어 있습니다':'기재된 학년으로 확인되지 않습니다'}. ${listed?'현재 등록 가능 여부와 학생의 진도에 맞는 수업 범위는 따로 질문하세요.':'미기재는 수업 불가를 뜻하지 않습니다. 현재 개설 여부부터 질문하세요.'} ${esc(localSchoolQuestion(schools,band))} 이 페이지의 연습 답안은 실제 학교의 평가 범위를 대신하지 않습니다.`,'grade-local-evidence');
 }else if(role==='subject-guide'){
  const sec=classSection('subject-review-section'),n=prose(sec).find(n=>{const t=plain(before.slice(n.open,n.close));return t.includes('상담에서는 학생이 가져온')||t.startsWith('두 과목을 함께 문의할 때는 상담 답변도')})||ns.find(n=>n.tag==='li'&&inside(n,sec)&&plain(before.slice(n.open,n.close))==='개설 자료와 현재 모집 여부를 구분해 기록하세요.');
  if(!n)throw Error('Guide record contract '+p);
  const m=material[band];
  const task=subject==='영어'?'원문의 근거와 학생이 쓴 표현을 나란히 놓고, 내용 이해와 문장 형태 중 바뀐 부분을 구분하세요.':subject==='수학'?'조건을 읽은 기록, 처음 세운 식, 계산·검산을 나누어 적고 오류가 시작된 줄을 표시하세요.':'영어의 근거·표현 기록과 수학의 조건·풀이 기록을 따로 준비하고, 도움 없이 끝낸 분량으로 두 과목의 우선순위를 비교하세요.';
  replace(n,`${esc(localSchoolQuestion(schools,band))} ${esc(task)} ${esc(center.branch)} 상담에서는 ${m?esc(m.question):'두 과목의 복습 분량과 확인 순서'}에 관해 질문하고 다음에 스스로 해볼 범위를 적으세요.`,'guide-student-record');
 }else if(role==='neighborhood-choice'){
  const sec=classSection('parent-review-section'),n=prose(sec)[0];
  replace(n,`${esc(center.branch)}의 ${band?esc(material[band].label)+' ':''}개설 자료를 비교한 뒤 다음 안내를 고르세요. ${esc(comp.text)} 현재 모집 여부는 기재 자료와 구분해 확인하고, 학습 질문과 방문 질문을 나누어 남기세요.`,'neighborhood-next-decision');
 }
 if(!changes.length)throw Error('Mapped role was not improved '+p);
 edits.sort((a,b)=>b[0]-a[0]);let s=before,boundary=s.length+1;
 for(const [a,b,v]of edits){if(b>boundary)throw Error('Overlapping role edits');s=s.slice(0,a)+v+s.slice(b);boundary=a}
 s=s.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{
  const obj=JSON.parse(b);let changed=false;
  function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){
   const ts=Array.isArray(v['@type'])?v['@type']:[v['@type']];
   if(ts.some(t=>['Article','WebPage'].includes(t))){v.dateModified=config.modifiedDate;changed=true}
   if(v['@graph'])visit(v['@graph']);
  }}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:all;
 });
 s=s.replace('</head>',marker+'</head>');return {after:s,changes,replacements,evidence};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(a=>a.includes('=')).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2))),root=path.resolve(args.root||path.join(here,'.public-release')),dry=process.argv.includes('--dry-run');
 const facts=Object.fromEntries([...new Set(Object.values(maps).map(m=>m.branchPath))].map(p=>[p,branchFacts(fs.readFileSync(path.join(root,p,'index.html'),'utf8'))]));
 const xmlFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(xmlFile,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const report={date:config.modifiedDate,version:config.version,pages:[],pageHashes:{},urls:{},changed:[],totals:{}};let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const url=urls[cursor++],p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=await fs.promises.readFile(f,'utf8'),r=clarify(before,p,facts[maps[p]?.branchPath]);if(!dry&&r.after!==before)await fs.promises.writeFile(f,r.after);const {after,...details}=r;report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...details});report.pageHashes[p]=hash(after);report.urls[p]=url;if(r.changes.length)report.changed.push(p)}}));
 if(!dry){
  const changed=new Set(report.changed),updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${config.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(xmlFile,updated);
  const rssFile=path.join(root,'rss.xml');let count=0;let rss=fs.readFileSync(rssFile,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{const u=body.match(/<link>([^<]+)<\/link>/)?.[1],p=u&&decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('RSS main missing');count++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});if(count){rss=rss.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,`<lastBuildDate>${config.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(rssFile,rss)}report.rssItemsUpdated=count;
 }
 report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.changed.sort();report.totals={checked:report.pages.length,changed:report.changed.length,roles:report.pages.reduce((o,r)=>{if(r.changes.length)o[r.evidence.role]=(o[r.evidence.role]||0)+1;return o},{}),actions:report.pages.reduce((o,r)=>{for(const k of r.changes)o[k]=(o[k]||0)+1;return o},{})};if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
