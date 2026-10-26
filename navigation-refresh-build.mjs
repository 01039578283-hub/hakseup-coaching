/** Reorganize navigation without removing source facts, URLs, images or maps. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const version='20261027',modifiedDate='2026-10-27';
const marker=`<!-- navigation-refresh:${version} -->`;
const maps=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'))).pages;
const centers=JSON.parse(fs.readFileSync(path.join(here,'local-content-config.json'))).centers;
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const inner=(s,n)=>s.slice(n.open,n.close);
const plain=s=>s.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const hash=s=>createHash('sha256').update(s).digest('hex');
const inNode=(n,p)=>n.start>p.start&&n.end<p.end;
function edit(s,list){list.sort((a,b)=>b[0]-a[0]);let bound=s.length+1;for(const[a,b,v]of list){if(b>bound)throw Error('Overlapping navigation edit');s=s.slice(0,a)+v+s.slice(b);bound=a}return s}
function home(s,ns){
 const area=ns.find(n=>n.a.id==='learning-paths'),grid=ns.find(n=>has(n,'hc-home-grid')&&inNode(n,area));
 const cards=ns.filter(n=>n.tag==='article'&&n.parent===grid);
 if(cards.length!==6)throw Error('Expected six existing home directory cards');
 const groups=[{id:'hcn-find-center',title:'가까운 학원 찾기',label:'01 · 지역과 지점',indexes:[3,4,5]},{id:'hcn-study-plan',title:'학년·과목별 공부',label:'02 · 지금 배우는 내용',indexes:[0]},{id:'hcn-study-help',title:'학습 고민 해결',label:'03 · 방법과 실천',indexes:[1,2]}];
 const blocks=groups.map(g=>{
  const items=g.indexes.map(i=>{const card=cards[i],h=ns.find(n=>n.tag==='h3'&&inNode(n,card));const p=ns.filter(n=>n.tag==='p'&&n.parent===card&&!has(n,'hc-home-label'));const actions=ns.find(n=>has(n,'hc-home-actions')&&inNode(n,card));if(!h||p.length!==1||!actions)throw Error('Home card structure changed');return `<div class="hcn-home-item"><h4>${inner(s,h)}</h4>${s.slice(p[0].start,p[0].end)}${s.slice(actions.start,actions.end)}</div>`}).join('');
  const shortcuts=g.id==='hcn-study-plan'?'<div class="hcn-home-shortcuts" aria-label="학교급별 공부 계획"><a href="/공부커리큘럼/초등/">초등</a><a href="/공부커리큘럼/중등/">중등</a><a href="/공부커리큘럼/고등/">고등</a></div>':g.id==='hcn-study-help'?'<a class="hcn-extra-link" href="/진단상담/">첫 상담 준비하기 ↗</a>':'';
  return `<article class="hcn-home-card" id="${g.id}"><p class="hcn-step">${g.label}</p><h3>${g.title}</h3>${items}${shortcuts}</article>`;
 }).join('');
 const hero=ns.find(n=>has(n,'hc-hero')),links=ns.find(n=>has(n,'hc-links')&&inNode(n,hero));if(!links)throw Error('Missing home hero links');
 const guide='<nav class="hcn-hero-links" aria-label="목적별 시작"><a href="#hcn-find-center">가까운 학원 찾기</a><a href="#study-curriculum">학년·과목별 공부</a><a href="#education-information">학습 고민 해결</a></nav>';
 // Keep every old hero destination in a quieter supporting row.
 const support='<div class="hcn-hero-secondary">'+inner(s,links)+'</div>';
 return {after:edit(s,[[grid.start,grid.end,`<div class="hcn-home-grid">${blocks}</div>`],[links.start,links.end,guide+support]]),role:'home',links:[],movedToc:false,targets:[]};
}
export function refreshNavigation(before,p,cssUrl){
 if(before.includes(marker)||p!=='/'&&!maps[p])return {after:before,changed:false};
 const ns=nodes(before),main=ns.find(n=>n.tag==='main');if(!main)throw Error('Missing main '+p);
 let r;
 if(p==='/')r=home(before,ns);
 else{
  const map=maps[p],center=centers[map.branchPath];if(!center)throw Error('Missing matched branch '+p);
  const hero=ns.find(n=>n.tag==='section'&&/(?:^|\s)(?:hc-hero|subject-local-hero|page-hero)(?:\s|$)/.test(n.a.class||''));if(!hero)throw Error('Missing detail hero '+p);
  const byId=id=>ns.find(n=>n.a.id===id),byClass=c=>ns.find(n=>has(n,c));
  const role=p===map.branchPath?'branch':byClass('center-profile-flow')?'center-profile':byId('grade-focus')?'grade':byId('subject-courses')?'offering':byClass('subject-local-hero')?'subject-guide':'neighborhood';
  const intro={branch:'주소와 안내 학년·과목을 확인한 뒤 상담을 준비하세요.','center-profile':'소개된 학습 방향과 지점 정보를 함께 확인하세요.',grade:'현재 학년의 학습 범위와 실제 개설 정보를 구분해 확인하세요.',offering:'과목별 안내 학년과 수강 조건을 확인한 뒤 필요한 학년으로 이동하세요.','subject-guide':'수강 정보를 확인하고, 학생의 답안에 맞는 학습 기준을 살펴보세요.',neighborhood:'이 동네에서 안내하는 지점의 과목·학년과 방문 정보를 확인하세요.'}[role];
  const targets=[
   ['수강·지점 정보',byId('center-info')||byId('regional-page-facts')||byId('subject-courses')||byClass('center-profile-context'),'facts'],
   ['위치·찾아오는 길',byId('directions'),'directions'],
   ['상담 준비 자료',byClass('hc-consult-tasks')||byId('learning-preparation-record')||byId('visit-checklist')||byId('grade-center')||byId('learning')||byClass('center-profile-flow'),'preparation'],
   ['자주 묻는 질문',byId('regional-content-faq')||byId('faq'),'questions'],
   ['관련 학년·과목',byClass('local-study-network')||byId('neighborhood-pages')||byId('subject-grades')||byId('related-pages'),'related'],
   ['공부 자료·교사',byId('related-learning-resources'),'resources']
  ].filter(([,n])=>n);
  const ids=new Set(ns.map(n=>n.a.id).filter(Boolean)),edits=[],seen=new Set(),links=[];
  for(const[label,n,key]of targets){if(seen.has(n))continue;seen.add(n);const id=n.a.id||`hcn-${key}`;if(!n.a.id&&ids.has(id))throw Error('Target ID collision '+p);ids.add(id);edits.push([n.start,n.open,before.slice(n.start,n.open-1)+(n.a.id?'':` id="${id}"`)+' data-hcn-target>']);links.push({label,href:'#'+id});}
  if(links.length<3||!links.some(x=>x.href==='#directions'))throw Error('Incomplete detail navigation '+p);
  if(ids.has('hcn-page-guide')||ids.has('hcn-guide-title'))throw Error('Guide ID collision '+p);
  const oldToc=ns.find(n=>n.tag==='nav'&&has(n,'subject-page-toc'));
  const heroLinks=ns.find(n=>has(n,'hc-links')&&inNode(n,hero));
  if(oldToc)edits.push([oldToc.start,oldToc.end,'']);
  if(heroLinks)edits.push([heroLinks.start,heroLinks.end,'']);
  const branchLink=p!==map.branchPath?`<a class="hcn-branch-link" href="${esc(map.branchPath)}">${esc(center.branch)} 전체 안내 ↗</a>`:'';
  const toc=(oldToc?`<details class="hcn-full-toc"><summary>학습 내용 목차도 보기</summary>${before.slice(oldToc.start,oldToc.end)}</details>`:'')+(heroLinks?`<details class="hcn-full-toc"><summary>지점 세부 항목도 보기</summary>${before.slice(heroLinks.start,heroLinks.end)}</details>`:'');
  const nav=`<aside class="hcn-guide" id="hcn-page-guide" aria-labelledby="hcn-guide-title"><div class="hcn-guide-heading"><h2 id="hcn-guide-title">${esc(center.branch)} 안내, 필요한 곳부터</h2>${branchLink}</div><p>${intro}</p><nav class="hcn-jumps" aria-label="이 페이지 바로가기">${links.map(x=>`<a href="${x.href}">${x.label}</a>`).join('')}</nav>${toc}</aside>`;
  edits.push([hero.end,hero.end,nav]);
  r={after:edit(before,edits),role,links,movedToc:!!oldToc,movedHeroLinks:!!heroLinks,targets:links.map(x=>x.href.slice(1)),branch:map.branchPath};
 }
 // Only page editorial modification dates change. Source verification dates remain intact.
 r.after=r.after.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{const obj=JSON.parse(b);let changed=false;function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){const t=Array.isArray(v['@type'])?v['@type']:[v['@type']];if(t.some(x=>['Article','WebPage'].includes(x))){v.dateModified=modifiedDate;changed=true}if(v['@graph'])visit(v['@graph'])}}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:all});
 r.after=r.after.replace('</head>',`<link rel="stylesheet" href="${cssUrl}">${marker}</head>`);r.changed=true;return r;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(x=>x.includes('=')).map(x=>x.replace(/^--/,'').split(/=(.*)/s).slice(0,2))),root=path.resolve(args.root||path.join(here,'.public-release'));
 const dryRun=process.argv.includes('--check');
 const css=fs.readFileSync(path.join(here,'navigation-refresh.css'),'utf8').replaceAll('\r\n','\n'),cssUrl='/assets/search-quality-cache/'+hash(css)+'.css';if(!dryRun){fs.mkdirSync(path.dirname(path.join(root,cssUrl)),{recursive:true});fs.writeFileSync(path.join(root,cssUrl),css)}
 const xmlFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(xmlFile,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const report={date:modifiedDate,version,cssUrl,pages:[],pageHashes:{},urls:{},changed:[]};let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const url=urls[cursor++],p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=await fs.promises.readFile(f,'utf8'),r=refreshNavigation(before,p,cssUrl);if(r.changed&&!dryRun)await fs.promises.writeFile(f,r.after);const {after,...data}=r;report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...data});report.pageHashes[p]=hash(after);report.urls[p]=url;if(r.changed)report.changed.push(p)}}));
 if(dryRun){console.log(JSON.stringify({preflight:true,checked:urls.length,changed:report.changed.length}));process.exit(0)}
 const changed=new Set(report.changed);const updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(xmlFile,updated);
 const rf=path.join(root,'rss.xml');let rssCount=0,rss=fs.readFileSync(rf,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,b)=>{const u=b.match(/<link>([^<]+)<\/link>/)?.[1],p=u&&decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('Missing RSS main');rssCount++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});if(rssCount){rss=rss.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,'<lastBuildDate>Tue, 27 Oct 2026 04:48:00 +0900</lastBuildDate>');fs.writeFileSync(rf,rss)}
 report.changed.sort();report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.totals={checked:urls.length,changed:changed.size,movedTocs:report.pages.filter(x=>x.movedToc).length,movedHeroLinks:report.pages.filter(x=>x.movedHeroLinks).length,rssItemsUpdated:rssCount};if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
