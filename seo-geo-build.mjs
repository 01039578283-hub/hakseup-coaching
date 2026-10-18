/** Consolidate verified content roles without touching URLs, photographs or maps. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const opt=Object.fromEntries(process.argv.slice(2).filter(x=>x.startsWith('--')).map(x=>x.slice(2).split(/=(.*)/s).slice(0,2)));
const dryRun=process.argv.includes('--dry-run');
const root=path.resolve(opt.root||path.join(here,'.public-release'));
const config=JSON.parse(fs.readFileSync(path.join(here,'seo-geo-config.json'),'utf8'));
const date=config.modifiedDate,marker=`<!-- seo-geo:${config.version} -->`;
const base='https://xn--ru4bi8s1tac0p.kr';
const hash=s=>createHash('sha256').update(s.replaceAll('\r\n','\n')).digest('hex');
const plain=s=>s.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const inner=(s,n)=>s.slice(n.open,n.close);
const ancestor=(n,test)=>{for(let p=n.parent;p;p=p.parent)if(test(p))return p;return null};
const within=(n,p)=>p&&n.start>p.start&&n.end<p.end;
function edit(s,patch){patch.sort((a,b)=>b[0]-a[0]);let end=s.length+1;for(const [a,b,v] of patch){if(b>end)throw Error('Overlapping content edit');s=s.slice(0,a)+v+s.slice(b);end=a}return s}
function lowerHeading(s){return s.replace(/<h2\b([^>]*)>([\s\S]*?)<\/h2>/,(_m,a,t)=>`<h3${a}>${t}</h3>`)}
export function improve(before,page){
 if(before.includes(marker))return {after:before,changes:[]};
 let s=before,ns=nodes(s),patch=[],changes=[];
 const faq=ns.find(n=>n.tag==='section'&&n.a.id==='regional-content-faq');
 // Keep the complete source list and qualifications in the existing FAQ. Replace
 // only an exact second copy outside the FAQ with an actionable reference.
 if(faq){
  const faqParagraphs=new Map(ns.filter(n=>n.tag==='p'&&within(n,faq)).map(n=>[plain(inner(s,n)),n]));
  const anchored=new Set();
  for(const n of ns.filter(n=>n.tag==='p'&&!within(n,faq))){
   const text=plain(inner(s,n));
   if(!n.a.id&&!/<(?:a|img)\b/.test(inner(s,n))&&text.includes('학교명은 상담 참고 목록입니다.')&&faqParagraphs.has(text)){
    const source=ancestor(n,p=>(p.a.class||'').split(/\s+/).includes('priority-intent-source'));
    const advice=source?'학교 참고 목록은 현재 모집의 근거가 아닙니다. 재학 학교에서 받은 최신 평가 안내와 현재 교재의 단원을 대조해 상담 범위를 확인하세요.':'학교에서 받은 시험 범위표의 단원과 현재 교재 목차를 나란히 적으세요. 첫 답안에서 설명이 막힌 문항을 표시하고, 그 범위를 상담할 수 있는지 지점에 확인하세요.';
    const answer=ancestor(faqParagraphs.get(text),p=>p.tag==='details');let anchor=answer?.a.id||'regional-content-faq';
    if(answer&&!answer.a.id&&!ns.some(p=>p.a.id==='school-reference-answer')){
     anchor='school-reference-answer';if(!anchored.has(answer.start)){patch.push([answer.open-1,answer.open-1,' id="'+anchor+'"']);anchored.add(answer.start)}
    }
    patch.push([n.open,n.close,advice+' <a class="sg-school-reference-link" href="#'+anchor+'">학교 참고 목록의 의미 확인</a>']);changes.push('school-reference-once');
   }
  }
 }
 s=edit(s,patch);ns=nodes(s);patch=[];
 const review=ns.find(n=>n.tag==='section'&&(n.a.class||'').split(/\s+/).includes('subject-review-section'));
 const question=ns.find(n=>n.tag==='section'&&(n.a.class||'').split(/\s+/).includes('subject-copy-section')&&ns.some(h=>h.tag==='h2'&&within(h,n)&&plain(inner(s,h))==='상담 답변을 기록하고 다음 안내 선택하기'));
 if(review&&question&&!/<(?:img|iframe|script)\b/.test(s.slice(question.start,question.end))){
  const heading=ns.find(n=>n.tag==='h2'&&within(n,review));
  if(!heading)throw Error('Review heading missing '+page);
  const copy=lowerHeading(s.slice(question.start,question.end)).replace('상담 답변을 기록하고 다음 안내 선택하기','학생 답안으로 확인할 질문').replace(/^<section\b/,'<div').replace(/<\/section>$/,'</div>');
  const list=ns.find(n=>n.tag==='ul'&&within(n,review));if(!list)throw Error('Review list missing '+page);
  patch.push([question.start,question.end,''],[heading.open,heading.close,inner(s,heading).replace('상담 답변 기록','상담 질문과 답변 기록')]);
  // Adjacent heading/list boundaries share an offset. Compose a single insertion
  // there so that the answer label cannot precede the question block.
  if(list.start===heading.end)patch.push([heading.end,heading.end,copy+'<h3>상담 뒤 남길 답변</h3>']);
  else patch.push([heading.end,heading.end,copy],[list.start,list.start,'<h3>상담 뒤 남길 답변</h3>']);
  changes.push('consultation-questions-and-record');
 }
 const prep=ns.find(n=>n.tag==='section'&&n.a.id==='learning-preparation-record');
 const grade=ns.find(n=>n.tag==='section'&&n.a.id==='grade-center');
 if(prep&&grade){
  const heading=ns.find(n=>n.tag==='h2'&&within(n,grade));if(!heading)throw Error('Grade heading missing '+page);
  const copy=lowerHeading(s.slice(prep.start,prep.end)).replace(/(<h3\b[^>]*>)[\s\S]*?(<\/h3>)/,'$1공부한 과정과 남은 질문 기록$2').replace(/^<section\b/,'<div').replace(/<\/section>$/,'</div>').replace('class="sq-preparation"','class="sq-preparation sg-record"');
  patch.push([prep.start,prep.end,''],[heading.end,heading.end,copy]);changes.push('grade-preparation-and-consultation');
 }
 // City names such as Jung-gu occur in several provinces. Preserve each group
 // and every link; make its heading independently understandable.
 if(/^\/과목별학원\/[^/]+\/$/.test(page)){
  for(const h of ns.filter(n=>n.tag==='h3'&&n.parent?.a.class==='subject-city-group')){
   const group=ancestor(h,n=>n.tag==='details'&&(n.a.class||'').includes('subject-region-group'));
   const summary=group&&ns.find(n=>n.tag==='summary'&&within(n,group));
   const span=summary&&ns.find(n=>n.tag==='span'&&within(n,summary));
   if(span){const region=plain(inner(s,span));if(region&&!plain(inner(s,h)).startsWith(region+' ')){patch.push([h.open,h.open,region+' ']);changes.push('unambiguous-region-heading')}}
  }
 }
 s=edit(s,patch);
 if(changes.length){
  if(changes.includes('school-reference-once'))s=s.replace('</head>','<style data-seo-geo-link>.sg-school-reference-link{display:flex;align-items:center;min-height:44px;width:fit-content;max-width:100%;margin-top:6px;text-decoration:underline;text-underline-offset:3px;font-weight:600}#school-reference-answer{scroll-margin-top:96px}</style></head>');
  if(changes.includes('grade-preparation-and-consultation'))s=s.replace('</head>','<style data-seo-geo-style>.sq-preparation.sg-record{width:100%;max-width:none;margin:20px 0;padding:20px;box-sizing:border-box}.sg-record>h3:first-child{margin-top:0}.subject-review-section .subject-copy-section{margin:20px 0}</style></head>');
  // A real editorial consolidation changes this document, not the source-fact
  // verification date. Keep visible source dates and publication dates intact.
  s=s.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(m,a,b,c)=>{
   const obj=JSON.parse(b);let changed=false;
   function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){const ts=Array.isArray(v['@type'])?v['@type']:[v['@type']];if(ts.some(t=>['WebPage','Article'].includes(t))){v.dateModified=date;changed=true}if(v['@graph'])visit(v['@graph'])}}
   visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:m;
  });
  s=s.replace('</head>',marker+'</head>');
 }
 return {after:s,changes};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const sitemapFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(sitemapFile,'utf8');
 const urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const selected=opt.paths?new Set(JSON.parse(fs.readFileSync(opt.paths,'utf8'))):null;
 const report={date,pages:[],pageHashes:{},urls:{},changed:[],totals:{}};let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const url=urls[cursor++],p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html');if(selected&&!selected.has(p))continue;
  const before=await fs.promises.readFile(f,'utf8'),result=improve(before,p);if(!dryRun&&result.after!==before)await fs.promises.writeFile(f,result.after);
  const row={path:p,changes:result.changes,beforeHash:hash(before),afterHash:hash(result.after)};report.pages.push(row);report.pageHashes[p]=row.afterHash;report.urls[p]=url;if(row.changes.length)report.changed.push(p);
 }}));
 if(!selected&&!dryRun){
  const changed=new Set(report.changed);const updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${date}</lastmod>`):all});
  if(updated!==xml)fs.writeFileSync(sitemapFile,updated);
  const rssFile=path.join(root,'rss.xml');let rssChanged=0;
  if(fs.existsSync(rssFile)){
   let rss=fs.readFileSync(rssFile,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{
    const u=body.match(/<link>([^<]+)<\/link>/)?.[1],p=u&&decodeURIComponent(new URL(u).pathname);if(!p||!changed.has(p))return all;
    const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('RSS main missing '+p);
    rssChanged++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`);
   });
   if(rssChanged){rss=rss.replace(/<lastBuildDate>[^<]*<\/lastBuildDate>/,`<lastBuildDate>${config.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(rssFile,rss)}
  }
  report.rssItemsUpdated=rssChanged;
 }
 report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.changed.sort();report.totals={checked:report.pages.length,changed:report.changed.length,actions:report.pages.reduce((a,p)=>{for(const k of p.changes)a[k]=(a[k]||0)+1;return a},{})};
 if(opt.report)fs.writeFileSync(path.resolve(opt.report),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report.totals));
}
