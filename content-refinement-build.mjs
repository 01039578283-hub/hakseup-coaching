/** Consolidate exact repeated facts while preserving their meaning and scope. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(fs.readFileSync(path.join(here,'content-refinement-config.json'),'utf8'));
const mappings=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'),'utf8')).pages;
const marker=`<!-- content-refinement:${config.version} -->`;
const conditions=new Set(config.conditionTexts);
const plain=s=>s.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const inside=(n,p)=>p&&n.start>p.start&&n.end<p.end;
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const ancestor=(n,test)=>{for(let a=n.parent;a;a=a.parent)if(test(a))return a;return null};
const inner=(s,n)=>s.slice(n.open,n.close);
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const hash=s=>createHash('sha256').update(s.replaceAll('\r\n','\n')).digest('hex');
function edit(s,patches){patches.sort((a,b)=>b[0]-a[0]);let boundary=s.length+1;for(const [a,b,v]of patches){if(b>boundary)throw Error('Overlapping refinement edit');s=s.slice(0,a)+v+s.slice(b);boundary=a}return s}
function groups(ns,s,predicate){const out=new Map();for(const n of ns.filter(predicate)){const t=plain(inner(s,n));const a=out.get(t)||[];a.push(n);out.set(t,a)}return out}
function idFor(n,patches,value,used){if(n.a.id)return n.a.id;if(used.has(value))throw Error('Refinement anchor collision '+value);used.add(value);patches.push([n.open-1,n.open-1,` id="${value}"`]);return value}
export function refine(before,page){
 const changes=[],schoolAnswers=[],sharedNotes=[],noteReferences=[],missingBands=[],grammar=[],addressCopies=[];
 if(!mappings[page]||before.includes(marker))return {after:before,changes,schoolAnswers,sharedNotes,noteReferences,missingBands,grammar,addressCopies};
 let s=before,ns=nodes(s),patches=[],used=new Set(ns.map(n=>n.a.id).filter(Boolean));
 // The full source list stays visible in the main preparation section. The FAQ
 // answers the question concisely and links to that unchanged list.
 for(const [text,arr]of groups(ns,s,n=>n.tag==='p'&&plain(inner(s,n)).includes('학교명은 상담 참고 목록입니다.'))){
  if(arr.length<2)continue;
  const keeper=arr.find(n=>ancestor(n,a=>a.a.id==='prepare-records')&&!ancestor(n,a=>a.tag==='details'));
  const copies=arr.filter(n=>n!==keeper);
  if(!keeper||copies.some(n=>!ancestor(n,a=>a.tag==='details'&&has(a,'regional-content-faq'))))continue;
  const id=idFor(keeper,patches,'cr-school-reference',used);
  for(const n of copies){
   const details=ancestor(n,a=>a.tag==='details');const summary=ns.find(a=>a.tag==='summary'&&a.parent===details);if(!summary)throw Error('School question missing '+page);
   const answer=`본문의 학교 목록은 상담 참고용입니다. 전용반·현재 모집·학교별 수업 가능 여부를 뜻하지 않습니다. 학생이 받은 최신 평가 안내와 교재의 단원을 준비해 상담할 범위를 확인하세요. <a class="cr-fact-link" href="#${id}">학교 참고 목록과 준비 자료 확인</a>`;
   patches.push([n.open,n.close,answer]);schoolAnswers.push({question:plain(inner(s,summary)),oldText:text,newText:plain(answer),anchor:id});changes.push('school-list-once');
  }
 }
 for(const n of ns.filter(n=>n.tag==='p'&&inner(s,n).includes('수학는'))){
  const old=inner(s,n);patches.push([n.open,n.close,old.replaceAll('수학는','수학은')]);grammar.push({oldText:plain(old),newText:plain(old.replaceAll('수학는','수학은'))});changes.push('korean-subject-particle');
 }
 for(const address of ns.filter(n=>n.tag==='p'&&has(n,'hc-address')&&ancestor(n,a=>a.a.id==='location'))){
  const next=ns.find(n=>n.tag==='p'&&n.start===address.end&&n.parent===address.parent);
  if(next&&!Object.keys(next.a).length&&!/<[a-z]/i.test(inner(s,next))&&plain(inner(s,next))===plain(inner(s,address))){patches.push([next.start,next.end,'']);addressCopies.push(plain(inner(s,address)));changes.push('adjacent-address-once')}
 }
 if(patches.length){s=edit(s,patches);ns=nodes(s)}patches=[];
 let noteNumber=0;
 // Identical qualifications in distinct subject cards are scoped explicitly in
 // one visible block; grade lists and unique qualifications stay in each card.
 for(const grid of ns.filter(n=>n.tag==='div'&&(has(n,'hc-course-grid')||has(n,'center-profile-grade-grid')))){
  const entries=[];
  for(const [text,arr]of groups(ns,s,n=>n.tag==='p'&&inside(n,grid)&&has(n,'hc-small')&&conditions.has(plain(inner(s,n))))){
   if(arr.length<2||arr.some(n=>n.a.id||/<(?:a|img|iframe)\b/.test(inner(s,n))))continue;
   const cards=arr.map(n=>ancestor(n,a=>a.tag==='article'&&inside(a,grid)));
   if(cards.some(n=>!n)||new Set(cards).size!==cards.length)continue;
   const subjects=cards.map(card=>{
    const fact=ns.find(n=>n.tag==='p'&&inside(n,card)&&n.a['data-fact-subject']);
    if(!fact)throw Error('Shared qualification subject missing '+page);return fact.a['data-fact-subject'];
   });
   const id='cr-course-condition-'+(++noteNumber);if(used.has(id))throw Error('Anchor collision');used.add(id);
   entries.push(`<li id="${id}"><strong>${subjects.map(esc).join('·')}:</strong> <span>${inner(s,arr[0])}</span></li>`);
   arr.forEach((n,i)=>patches.push([n.open,n.close,`<a class="cr-fact-link" href="#${id}">${esc(subjects[i])}의 공통 확인 조건</a>`]));
   sharedNotes.push({text,subjects,anchor:id,copies:arr.length});changes.push('shared-course-qualification');
  }
  if(entries.length){
   const id='cr-shared-conditions';if(used.has(id))throw Error('Shared block collision');used.add(id);
   patches.push([grid.end,grid.end,`<aside class="cr-shared-conditions" id="${id}" aria-labelledby="cr-shared-conditions-title"><h3 id="cr-shared-conditions-title">과목별로 함께 확인할 조건</h3><ul>${entries.join('')}</ul></aside>`]);
  }
 }
 if(patches.length){s=edit(s,patches);ns=nodes(s)}patches=[];
 // Other exact copies become short references to the visible original. This
 // never deduplicates addresses, subject-grade facts, school data or FAQ text.
 for(const text of config.conditionTexts){
  const original=ns.filter(n=>n.tag==='p'&&plain(inner(s,n))===text&&!ancestor(n,a=>a.tag==='details')&&!/<(?:a|img|iframe)\b/.test(inner(s,n)));
  const shared=sharedNotes.find(n=>n.text===text);
  if(original.length+(shared?1:0)<2)continue;
  const keeper=shared?null:original.find(n=>ancestor(n,a=>has(a,'regional-course-notes')))||original[0];
  const id=shared?.anchor||idFor(keeper,patches,'cr-course-condition-'+(++noteNumber),used);
  for(const n of original){
   if(n===keeper)continue;
   const section=ancestor(n,a=>a.tag==='section'),card=ancestor(n,a=>a.tag==='article');
   const cardHeading=card&&ns.find(a=>a.tag==='h3'&&inside(a,card));
   const subject=cardHeading&&plain(inner(s,cardHeading)).match(/영어|수학|국어|과학|사회/)?.[0];
   const label=section?.a.id==='subject-location'?'방문 전 추가 수업 조건 확인':section?.a.id==='subject-courses'?'학년 선택 전 추가 수업 조건 확인':section?.a.id==='prepare-records'?'상담 준비에 반영할 추가 조건 확인':subject?`${subject} 상담의 추가 조건 확인`:'과목별 추가 수업 조건 확인';
   patches.push([n.open,n.close,`<a class="cr-fact-link" href="#${id}">${label}</a>`]);noteReferences.push({text,anchor:id,context:section?.a.id||section?.a.class||null});changes.push('course-qualification-once');
  }
 }
 // Missing operating data stays missing. Replace repeated empty statements with
 // age-appropriate preparation actions, without inventing availability.
 const missing='영어 기재 학년: 해당 학교급 학년 미기재 / 수학 기재 학년: 해당 학교급 학년 미기재.';
 const empty=ns.filter(n=>n.tag==='p'&&plain(inner(s,n))===missing);
 if(empty.length===3){
  const copy=empty[0].parent;
  if(empty.every(n=>n.parent===copy)&&has(copy,'seo-answer-copy')){
   const firstHeading=ns.find(n=>n.tag==='h3'&&n.parent===copy);if(!firstHeading)throw Error('Missing band heading '+page);
   patches.push([firstHeading.start,firstHeading.start,`<p class="cr-missing-status"><strong>초·중·고 공통 확인 상태:</strong> ${missing} 미기재는 수업 불가를 뜻하지 않습니다. 희망 학년·과목의 실제 개설 여부를 먼저 확인하세요.</p>`]);
   const actions=['학년·현재 단원과 학생이 혼자 읽고 푼 자료를 준비하세요. 필요한 과목의 개설 학년과 실제 수업 장소를 확인한 뒤 학습 안내를 선택하세요.','최근 시험·수행평가 안내에서 현재 범위를 표시하고, 설명이 막힌 답안을 준비하세요. 해당 학년·과목의 상담 가능 여부를 먼저 확인하세요.','교과서에 적힌 이수 과목명과 학교 평가 범위를 준비하세요. 선택 과목과 수업 방식에 맞는 상담인지 확인한 뒤 학습 안내를 선택하세요.'];
   empty.forEach((n,i)=>{patches.push([n.open,n.close,actions[i]]);missingBands.push({band:['초등','중등','고등'][i],action:actions[i]})});changes.push('missing-data-preparation');
  }
 }
 s=edit(s,patches);
 if(!changes.length)return {after:before,changes,schoolAnswers,sharedNotes,noteReferences,missingBands,grammar,addressCopies};
 const matched=new Set();
 s=s.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{
  const obj=JSON.parse(b);let changed=false;
  function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){
   const types=Array.isArray(v['@type'])?v['@type']:[v['@type']];
   if(types.some(t=>['Article','WebPage'].includes(t))){v.dateModified=config.modifiedDate;changed=true}
   if(types.includes('FAQPage'))for(const q of v.mainEntity||[]){const row=schoolAnswers.find(x=>x.question===q.name);if(row){if(q.acceptedAnswer?.text!==row.oldText)throw Error('School answer source mismatch '+page);q.acceptedAnswer.text=row.newText;matched.add(row.question);changed=true}}
   if(v['@graph'])visit(v['@graph']);
  }}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:all;
 });
 if(schoolAnswers.some(x=>!matched.has(x.question)))throw Error('School schema question missing '+page);
 const css='<style data-content-refinement>.cr-fact-link{display:inline-flex;align-items:center;min-height:44px;max-width:100%;text-decoration:underline;text-underline-offset:3px;font-weight:600}.cr-shared-conditions{margin:20px 0;padding:20px;border:1px solid rgba(23,59,48,.16);border-radius:16px;box-sizing:border-box}.cr-shared-conditions h3{margin-top:0}.cr-shared-conditions li{margin:10px 0;line-height:1.8}.cr-missing-status{line-height:1.8}[id^="cr-course-condition-"],#cr-school-reference{scroll-margin-top:100px}</style>';
 s=s.replace('</head>',css+marker+'</head>');
 return {after:s,changes,schoolAnswers,sharedNotes,noteReferences,missingBands,grammar,addressCopies};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(a=>a.includes('=')).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2))),root=path.resolve(args.root||path.join(here,'.public-release')),dryRun=process.argv.includes('--dry-run');
 const xmlFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(xmlFile,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const report={date:config.modifiedDate,version:config.version,pages:[],pageHashes:{},urls:{},changed:[],totals:{}};let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const url=urls[cursor++],p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=await fs.promises.readFile(f,'utf8'),r=refine(before,p);if(!dryRun&&r.after!==before)await fs.promises.writeFile(f,r.after);const {after,...details}=r;report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...details});report.pageHashes[p]=hash(after);report.urls[p]=url;if(r.changes.length)report.changed.push(p)}}));
 if(!dryRun){
  const changed=new Set(report.changed),updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${config.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(xmlFile,updated);
  const rssFile=path.join(root,'rss.xml');let count=0;let rss=fs.readFileSync(rssFile,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{const u=body.match(/<link>([^<]+)<\/link>/)?.[1],p=u&&decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('RSS main missing');count++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});if(count){rss=rss.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,`<lastBuildDate>${config.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(rssFile,rss)}report.rssItemsUpdated=count;
 }
 report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.changed.sort();report.totals={checked:report.pages.length,changed:report.changed.length,actions:report.pages.reduce((o,r)=>{for(const k of r.changes)o[k]=(o[k]||0)+1;return o},{})};if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
