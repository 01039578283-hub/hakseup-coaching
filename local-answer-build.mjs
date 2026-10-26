/** A reviewed cohort from Search Console. Rewrite bounded editorial areas only. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(fs.readFileSync(path.join(here,'local-answer-config.json')));
const notes=JSON.parse(fs.readFileSync(path.join(here,'local-answer-notes.json')));
const maps=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'))).pages;
const targets=new Set([...config.neighborhoodPaths,...Object.keys(config.centers)]);
const marker=`<!-- local-answers:${config.version} -->`;
const plain=s=>s.replace(/<[^>]*>/g,'').replaceAll('&amp;','&').replaceAll('&nbsp;',' ').replaceAll('&quot;','"').replace(/\s+/g,' ').trim();
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const hash=s=>createHash('sha256').update(s).digest('hex');
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const inside=(n,p)=>p&&n.start>p.start&&n.end<p.end;
const common='기재 학년은 현재 모집을 뜻하지 않습니다. 미기재 학년도 수업 불가로 단정하지 말고, 현재 개설 여부와 학생의 진도에 맞는 범위를 지점에 확인하세요.';
const tasks={
 초:{label:'초등',school:'학교에서 받은 학습 안내와 최근 과제',english:'낱말이나 짧은 문장을 듣고 말한 기록에서 혼자 한 부분과 도움받은 부분',math:'그림·구체물로 수의 뜻을 설명한 부분과 식으로 바꾸다 멈춘 부분',action:'보호자가 답을 알려준 시점을 표시하고, 다음에는 학생이 혼자 시작할 활동과 도움을 줄 시점을 정하세요.'},
 중:{label:'중등',school:'학교의 최신 지필평가 범위·수행평가 안내와 교과서',english:'본문에서 답의 근거를 찾은 문장과 스스로 바꾸어 쓴 문장',math:'문제 조건을 옮긴 첫 식과 계산 과정에서 처음 틀린 줄',action:'시험 범위의 단원과 수행평가 요구사항을 나누고, 재풀이할 문제와 확인 날짜를 각각 정하세요.'},
 고:{label:'고등',school:'실제 이수 과목명·학교 평가 안내와 현재 교재',english:'지문에 직접 적힌 정보와 추론한 내용을 구분한 답안',math:'이수 과목의 문제에서 사용한 조건과 다른 풀이가 가능한지 검토한 기록',action:'학년만 적지 말고 선택 과목과 단원을 적으세요. 현재 범위에서 먼저 보완할 내용과 다음 점검에 가져올 답안을 정하세요.'},
 all:{label:'영어·수학',school:'학생의 재학 학교·학년·현재 교재와 최신 학습 안내',english:'읽거나 쓴 답에서 근거를 설명하지 못한 부분',math:'첫 식을 세우거나 계산하다 멈춘 부분',action:'영어와 수학의 남은 질문을 따로 적고, 공부 가능한 시간 안에서 먼저 보완할 과목과 다음 확인 날짜를 정하세요.'}
};
export function improve(before,p){
 if(!targets.has(p)||before.includes(marker))return {after:before,changes:[],replacements:[]};
 const branchPath=maps[p]?.branchPath,c=config.centers[branchPath],memo=notes[c?.branch];
 if(!c||!memo)throw Error('Missing reviewed source '+p);
 const ns=nodes(before),edits=[],changes=[],replacements=[],faqEdits={};
 const content=n=>plain(before.slice(n.open,n.close));
 const id=x=>ns.find(n=>n.a.id===x);
 const sectionClass=x=>ns.find(n=>n.tag==='section'&&has(n,x));
 const paragraphs=n=>ns.filter(e=>e.tag==='p'&&inside(e,n)&&!has(e,'hc-kicker'));
 function replace(n,value,kind){
  if(!n||/<(?:a|img|iframe|span|time)\b/.test(before.slice(n.open,n.close)))throw Error('Unsafe edit '+p+' '+kind);
  edits.push([n.open,n.close,value]);replacements.push({oldText:content(n),newText:plain(value),kind});changes.push(kind);
 }
 function faq(question,answer){
  const summary=ns.find(n=>n.tag==='summary'&&content(n)===question);
  if(!summary)throw Error('Missing FAQ '+p+' '+question);
  const detail=ns.find(n=>n.tag==='details'&&inside(summary,n));const ps=paragraphs(detail);
  if(ps.length!==1)throw Error('FAQ paragraph contract '+p);
  replace(ps[0],answer,'faq-answer');faqEdits[question]=plain(answer);
 }
 const branch=p===branchPath;
 let band=null;
 if(branch){
  const learning=id('learning'),intro=paragraphs(learning)[0];
  replace(intro,esc(memo.decision+' '+common),'branch-decision');
  const cards=ns.filter(n=>n.tag==='article'&&inside(n,learning));
  if(cards.length!==3)throw Error('Branch learning cards '+p);
  replace(paragraphs(cards[2])[0],esc(`${c.branch} 상담을 마친 뒤 과목·단원·분량·완료 기준을 한 줄씩 적으세요. 처음 쓴 답안과 다시 푼 답안을 비교할 날짜, 남은 질문을 누구에게 어떻게 전달할지도 정합니다. 실제 피드백 방식과 주기는 상담 답변으로 확인하세요.`),'branch-followup-record');
  faq(`${c.branch} 상담 전 어떤 자료를 준비하면 좋나요?`,esc(`${c.branch}의 과목별 기재 학년을 학생의 현재 학년과 먼저 대조하세요. 학교 교재와 첫 답안, 희망 요일을 준비하고 상담 뒤에는 시작 단원·분량·완료 기준·다음 확인 날짜를 기록하세요. `)+`<a href="#learning">${esc(c.branch)} 학습 계획과 확인 조건</a>에서 과목별 질문을 이어서 확인할 수 있습니다.`);
  const visit=id('visit-checklist'),links=ns.find(n=>has(n,'hc-links')&&inside(n,visit));
  if(!links)throw Error('Missing visit links '+p);
  edits.push([links.start,links.start,`<p data-local-answer="visit">${esc(memo.visit)}</p>`]);changes.push('branch-visit-context');
 }else{
  const title=content(ns.find(n=>n.tag==='h1'));band=title.includes('초등')?'초':title.includes('중등')?'중':title.includes('고등')?'고':null;
  const t=tasks[band||'all'];
  const hero=sectionClass('page-hero'),lead=paragraphs(hero).filter(n=>!has(n,'eyebrow'))[0];
  replace(lead,esc(`이 페이지에서 안내하는 실제 지점은 ${c.branch}이며, 방문 주소는 ${c.address}입니다. ${band?t.label+' 학생의 ':''}영어·수학은 과목별 기재 학년과 현재 모집 여부를 따로 확인하세요.`),'neighborhood-direct-answer');
  const decision=sectionClass('seo-answer-section');
  replace(paragraphs(decision)[0],esc(memo.decision+' '+common),'neighborhood-local-decision');
  const checklist=sectionClass('seo-checklist-section'),items=ns.filter(n=>n.tag==='li'&&inside(n,checklist));
  if(items.length!==3)throw Error('Checklist contract '+p);
  const values=[`${t.school}를 준비하고, 영어는 ${t.english}을 표시하세요.`, `수학은 ${t.math}을 표시하세요. 두 과목의 점수만 비교하지 않고 학생이 설명할 수 있는 단계와 막힌 단계를 나눕니다.`,t.action];
  items.forEach((n,i)=>replace(n,esc(values[i]),'school-record-checklist'));
  replace(paragraphs(sectionClass('coaching-identity-section'))[0],esc(`${c.branch} 상담에서는 준비한 답안으로 시작 단원과 한 번에 할 분량을 의논하세요. 완료 기준은 ‘문제를 풀었다’에서 멈추지 않고, 풀이·답의 근거를 혼자 설명할 수 있는지까지 정해 보세요. 다음 확인 날짜와 질문 전달 방법은 실제 상담 답변으로 기록합니다.`),'consultation-outcome');
  const summary=ns.find(n=>n.tag==='summary'&&content(n).endsWith('학교 참고 목록은 실제 모집 학교인가요?'));
  if(!summary)throw Error('Missing school FAQ '+p);
  if(summary){
   const facts=id('regional-page-facts');if(!facts)throw Error('Missing school reference '+p);
   faq(content(summary),`학교 목록은 상담 참고 자료이며 전용반·현재 모집을 뜻하지 않습니다. <a href="#regional-page-facts">이 페이지의 학교 참고 목록과 ${esc(c.branch)} 개설 정보</a>를 확인한 뒤 ${esc(t.school)}를 준비하세요. ${esc(t.action)}`);
  }
  const gs=s=>c.facts[s].grades.filter(g=>!band||g.startsWith(band));
  const eg=gs('영어'),mg=gs('수학');
  const scope=`${t.label} 범위에서 영어 자료에 적힌 학년은 ${eg.length?eg.join('·')+'입니다':'추가 확인이 필요합니다'}. 수학 자료에 적힌 학년은 ${mg.length?mg.join('·')+'입니다':'추가 확인이 필요합니다'}.`;
  const condition=ns.find(n=>n.tag==='summary'&&content(n)===`${c.branch}에 추가로 확인할 수업 조건이 있나요?`);
  if(condition)faq(content(condition),esc(`${scope} 원하는 학년의 개설 여부를 확인한 뒤 시작일·요일·한 번의 수업 시간·교재를 과목별로 질문하세요. `)+`<a href="${esc(branchPath)}#courses">${esc(c.branch)}의 과목별 확인 조건</a>도 함께 확인하세요.`);
 }
 edits.sort((a,b)=>a[0]-b[0]);for(let i=1;i<edits.length;i++)if(edits[i][0]<edits[i-1][1])throw Error('Overlapping changes '+p);
 let after=before;for(const [a,b,s]of edits.reverse())after=after.slice(0,a)+s+after.slice(b);
 const synced=new Set();
 after=after.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{
  const data=JSON.parse(b);let modified=false;
  function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){
   if(v['@type']==='Question'&&Object.hasOwn(faqEdits,v.name)){if(!v.acceptedAnswer)throw Error('Missing schema answer');v.acceptedAnswer.text=faqEdits[v.name];synced.add(v.name);modified=true;}
   if(['WebPage','Article'].includes(v['@type'])){v.dateModified=config.modifiedDate;modified=true;}
   Object.values(v).forEach(x=>{if(x&&typeof x==='object')visit(x)});
  }}visit(data);return modified?a+JSON.stringify(data).replaceAll('<','\\u003c')+c:all;
 });
 for(const q of Object.keys(faqEdits))if(!synced.has(q))throw Error('Visible FAQ not in schema '+p+' '+q);
 after=after.replace('</head>',marker+'</head>');
 return {after,changes,replacements,faqEdits,role:branch?'branch':'neighborhood',branchPath,band,sourceRow:c.sourceRow};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(x=>x.includes('=')).map(x=>x.replace(/^--/,'').split(/=(.*)/s).slice(0,2)));
 const root=path.resolve(args.root||path.join(here,'.public-release')),dry=process.argv.includes('--check');
 const sf=path.join(root,'sitemap.xml'),xml=fs.readFileSync(sf,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(x=>x[1]);
 const report={version:config.version,date:config.modifiedDate,changed:[],pages:[],pageHashes:{},urls:{}};
 for(const url of urls){const p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=fs.readFileSync(f,'utf8'),r=improve(before,p);if(r.after!==before&&!dry)fs.writeFileSync(f,r.after);const {after,...details}=r;report.pageHashes[p]=hash(after);report.urls[p]=url;if(after!==before){report.changed.push(p);report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...details})}}
 if(!dry){
  const changed=new Set(report.changed);const updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,b)=>{const u=b.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${config.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(sf,updated);
  const rf=path.join(root,'rss.xml');const rss=fs.readFileSync(rf,'utf8');let rssChanged=false;
  const next=rss.replace(/<item>([\s\S]*?)<\/item>/g,(all,b)=>{const url=b.match(/<link>([^<]+)<\/link>/)?.[1];if(!url)return all;const p=decodeURIComponent(new URL(url).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');rssChanged=true;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});
  if(rssChanged)fs.writeFileSync(rf,next.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,'<lastBuildDate>Tue, 27 Oct 2026 06:00:00 +0900</lastBuildDate>'));
 }
 report.changed.sort();report.totals={checked:urls.length,changed:report.changed.length,branches:report.pages.filter(x=>x.role==='branch').length,neighborhoods:report.pages.filter(x=>x.role==='neighborhood').length};
 if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
