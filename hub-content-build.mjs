/** Reviewed directory cohort: useful choices and literal HTML destinations. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(fs.readFileSync(path.join(here,'hub-content-config.json')));
const notes=JSON.parse(fs.readFileSync(path.join(here,'hub-content-notes.json')));
const marker=`<!-- hub-content:${config.version} -->`;
const hash=s=>createHash('sha256').update(s).digest('hex');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const plain=s=>s.replace(/<[^>]*>/g,'').replaceAll('&amp;','&').replaceAll('&nbsp;',' ').replace(/\s+/g,' ').trim();
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const within=(n,p)=>p&&n.start>p.start&&n.end<p.end;
const a=(url,label)=>`<a href="${esc(url)}">${esc(label)}</a>`;
function apply(s,edits){edits.sort((x,y)=>y[0]-x[0]);let bound=s.length+1;for(const [start,end,value]of edits){if(end>bound)throw Error('Overlapping hub edits');s=s.slice(0,start)+value+s.slice(end);bound=start}return s}
const guides={
 '플래너 관리 방법':['실행되는-공부계획','실행되는 공부 계획','할 과제와 끝낸 기준을 정하고, 실제로 해 본 뒤 분량을 조정하는 방법을 확인하세요.'],
 '플래너 관리':['실행되는-공부계획','실행되는 공부 계획','할 과제와 끝낸 기준을 정하고, 실제로 해 본 뒤 분량을 조정하는 방법을 확인하세요.'],
 '오답 관리 방법':['수학-오류-찾기','수학 오답 원인 찾기','처음 틀린 줄과 그때 사용한 조건을 찾아 다음에 다시 확인할 문제를 정하세요.'],
 '오답 재학습':['수학-오류-찾기','수학 오답 원인 찾기','처음 틀린 줄과 그때 사용한 조건을 찾아 다음에 다시 확인할 문제를 정하세요.'],
 '시험 기간 계획표':['시험-준비-계획','시험 범위로 계획 세우기','학교 시험 범위와 현재 풀이를 대조해 남은 기간의 복습 순서를 정하세요.'],
 '시험 기간 계획':['시험-준비-계획','시험 범위로 계획 세우기','학교 시험 범위와 현재 풀이를 대조해 남은 기간의 복습 순서를 정하세요.'],
 '지역별 학원 선택 기준':['학원-수업-비교','수업 조건 비교하기','진단·과제·피드백 방식과 실제 수강 조건에 같은 질문을 해 보고 답변을 비교하세요.'],
 '지역별 학원 찾기':['학원-수업-비교','수업 조건 비교하기','진단·과제·피드백 방식과 실제 수강 조건에 같은 질문을 해 보고 답변을 비교하세요.'],
 '중고등 영어수학 관리':['학습-질문-만들기','학습 질문 구체화하기','최근 답안에서 혼자 할 수 있는 부분과 도움이 필요한 부분을 나누어 질문하세요.']
};
export function improveHub(before,p,cssUrl){
 const hub=config.hubs[p];if(!hub||before.includes(marker))return {after:before,changed:false};
 if(!notes[p])throw Error('Missing reviewed hub copy '+p);
 const ns=nodes(before),edits=[],replacements=[],changedLinks=[],cardEvidence=[];
 const text=n=>plain(before.slice(n.open,n.close));
 function replace(n,value,kind){if(!n)throw Error('Missing '+kind+' '+p);edits.push([n.open,n.close,value]);if(n.tag==='p')replacements.push({oldText:text(n),newText:plain(value),kind});}
 const directory=ns.find(n=>n.a.id==='hub-child-directory');const cards=ns.filter(n=>n.tag==='a'&&has(n,'hub-card')&&n.parent===directory);
 if(cards.length!==hub.children.length)throw Error('Directory size changed '+p);
 for(let i=0;i<cards.length;i++){
  const card=cards[i],k=hub.children[i],oldHref=new URL(card.a.href,'https://xn--ru4bi8s1tac0p.kr'+p).pathname;
  if(decodeURIComponent(oldHref)!==k.path)throw Error('Directory order changed '+p);
  const heading=ns.find(n=>n.tag==='strong'&&n.parent===card),para=ns.find(n=>n.tag==='p'&&n.parent===card),chips=ns.find(n=>has(n,'hub-child-list')&&within(n,card));
  if(!heading||!para||!chips||text(heading)!==k.name)throw Error('Directory card changed '+p);
  let content,links,branchLinks='';
  if(hub.level===3){
   const c=config.branches[k.branchPath];if(!c)throw Error('Missing branch evidence '+k.path);
   content=`${esc(k.name)}에서 참고하는 지점은 ${a(k.branchPath,c.branch)}입니다. `+(c.addressVerified?`방문 주소: ${esc(c.address)}.`:'방문 주소와 층·호수는 연결된 지점 안내에서 확인하세요.');
   links=k.grades.map(g=>a(g.path,g.label)).join('');
   branchLinks=`<nav class="hch-branch-links" aria-label="${esc(k.name)}의 실제 지점 정보">${a(k.branchPath+'#courses',c.branch+' 수강 조건')}${a(k.branchPath+'#directions',c.branch+' 찾아오는 길')}</nav>`;
   cardEvidence.push({path:k.path,branchPath:k.branchPath,addressPrinted:c.addressVerified,grades:k.grades.map(g=>g.path)});
  }else{
   content=hub.level===1?`${esc(k.name)}의 ${k.children.length}개 지역에서 ${k.localCount}개 동네 안내를 찾을 수 있습니다. 아래 지역명을 선택하거나 전체 목록에서 방문할 지점을 확인하세요.`:`${esc(k.name)}의 ${k.localCount}개 동네 안내는 ${k.branchCount}개 지점을 참고합니다. 동네 이름이 달라도 같은 지점일 수 있으니 실제 지점과 과목별 조건을 확인하세요.`;
   const shown=hub.level===1?k.children:k.children.slice(0,3);
   links=shown.map(x=>a(x.path,x.name)).join('');
   if(shown.length<k.children.length)links+=a(k.path,`${k.name} ${k.children.length}개 동네 전체 보기`);
   cardEvidence.push({path:k.path,children:shown.map(x=>x.path),localCount:k.localCount,branchCount:k.branchCount});
  }
  replacements.push({oldText:text(para),newText:plain(content),kind:'directory-card-summary'});
  const innerEdits=[[heading.start-card.open,heading.end-card.open,`<h3>${a(k.path,k.name)}</h3>`],[para.start-card.open,para.end-card.open,`<p class="hch-address">${content}</p>`],[chips.open-card.open,chips.close-card.open,links]];
  const inner=apply(before.slice(card.open,card.close),innerEdits)+branchLinks;
  edits.push([card.start,card.end,`<article class="hub-card hch-card" data-hub-child="${esc(k.path)}">${inner}</article>`]);
 }
 const summary=ns.find(n=>has(n,'hub-summary-copy'));
 if(summary){
  replace(ns.find(n=>n.tag==='h2'&&within(n,summary)),esc(hub.level===2?'지역을 좁힌 뒤 실제 지점을 확인하세요':'동네명과 실제 방문 지점을 함께 확인하세요'),'summary-heading');
  replace(ns.find(n=>n.tag==='p'&&within(n,summary)),esc(notes[p]),'local-selection-summary');
 }else{
  const hero=ns.find(n=>has(n,'hub-hero')),pnode=ns.find(n=>n.tag==='p'&&within(n,hero)&&!has(n,'eyebrow'));
  replace(pnode,esc(notes[p]),'national-role-summary');
 }
 const insight=ns.find(n=>has(n,'hub-insight-section'));
 if(insight){
  const ip=ns.filter(n=>n.tag==='article'&&has(n,'hub-insight-card')&&within(n,insight));if(ip.length!==3)throw Error('Unexpected insight cards '+p);
  const city=hub.level===3;
  const names=hub.children.map(c=>c.name);
  const grouped=Object.entries(hub.groups).filter(([,ls])=>ls.length>1).sort((a,b)=>b[1].length-a[1].length)[0];
  let first;
  if(city&&grouped){const [bp,locals]=grouped;first=`${locals.map(q=>hub.children.find(k=>k.path===q).name).join('·')} 안내는 ${a(bp,config.branches[bp].branch)}에 연결됩니다. 같은 지점으로 묶이는 동네는 한 후보로 정리한 뒤 수강 조건을 비교하세요.`;}
  else if(city){const bp=Object.keys(hub.groups)[0];first=`${esc(names.join('·'))} 안내에서 ${a(bp,config.branches[bp].branch)}의 실제 주소와 과목별 정보를 확인할 수 있습니다. 이 목록을 지역 전체 학원의 순위나 운영 현황으로 해석하지 마세요.`;}
  else first=`${hub.children.length}개 지역의 ${hub.localCount}개 동네 안내가 연결되어 있습니다. 먼저 ${hub.children.slice(0,3).map(k=>a(k.path,k.name)).join('·')} 등 방문 가능한 지역을 고르고, 동네 페이지의 실제 지점 주소를 확인하세요. 이 수는 현재 모집 중인 학원 수가 아닙니다.`;
  const copy=city?[
   ['동네를 실제 지점으로 묶어 비교하기',first],
   ['학습 준비와 수강 가능 여부 구분하기','동네 카드의 초등·중등·고등 링크는 해당 학교급의 상담 준비와 학습 기준으로 연결됩니다. 해당 학년을 지금 모집한다는 뜻은 아닙니다. 같은 카드의 지점 수강 조건에서 영어와 수학의 기재 학년·비고를 각각 확인하세요.'],
   ['상담 후 비교할 기록 남기기',`${a('/학습가이드/학원-수업-비교/','수업 비교 질문')}을 참고해 희망 과목·학년, 상담에서 확인한 조건, 남은 질문을 지점별로 기록하세요. 실제 방문 후보를 정했다면 카드의 찾아오는 길에서 주소와 지도 목적지를 대조하세요.`]
  ]:[
   ['지역별 안내 범위 확인하기',first],
   ['동네 목록과 지점 목록 구분하기',`${hub.localCount}개 동네 안내가 ${hub.branchCount}개 지점에 연결됩니다. 동네 수가 많다고 별도 지점이 그만큼 있는 것은 아닙니다. 동네를 고른 다음 연결된 지점의 이름과 실제 방문 주소를 확인하세요.`],
   ['후보를 좁힌 뒤 같은 기준으로 질문하기',`${a('/학습가이드/학원-수업-비교/','수업 조건 비교 방법')}을 읽고 학생에게 필요한 과목·학년과 현재 막힌 답안을 준비하세요. 지점마다 현재 개설·요일·시간·비용을 확인해 상담 답변을 비교할 수 있습니다.`]
  ];
  for(let i=0;i<3;i++){replace(ns.find(n=>n.tag==='h3'&&within(n,ip[i])),esc(copy[i][0]),'comparison-heading');replace(ns.find(n=>n.tag==='p'&&within(n,ip[i])),copy[i][1],'comparison-step');}
 }
 const guide=ns.find(n=>has(n,'hub-guide-section'));
 for(const card of ns.filter(n=>n.tag==='a'&&has(n,'hub-guide-card')&&within(n,guide))){
  const heading=ns.find(n=>n.tag==='h3'&&within(n,card)),entry=guides[text(heading)];if(!entry)continue;
  const next='/학습가이드/'+entry[0]+'/';
  edits.push([card.start,card.open,before.slice(card.start,card.open).replace(/href="[^"]*"/,`href="${next}"`)]);
  changedLinks.push({oldHref:card.a.href,newHref:next});replace(heading,esc(entry[1]),'guide-heading');replace(ns.find(n=>n.tag==='p'&&within(n,card)),esc(entry[2]),'guide-specific-answer');
 }
 const identity=ns.find(n=>has(n,'coaching-identity-head'));
 if(identity){
  replace(ns.find(n=>n.tag==='h2'&&within(n,identity)),'후보를 고른 뒤 학습관리 방식을 질문하세요','coaching-question-heading');
  replace(ns.find(n=>n.tag==='p'&&within(n,identity)&&!has(n,'parent-faq-eyebrow')),'아래 항목은 수업 후보를 비교할 때 사용할 질문 기준입니다. 지점마다 같은 방식으로 운영된다고 가정하지 말고, 실제 상담에서 과제 확인·재풀이·피드백이 어떻게 진행되는지 물어보세요.','coaching-evidence-boundary');
 }
 let after=apply(before,edits);
 after=after.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{
  const obj=JSON.parse(b);let changed=false;
  function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){if(['CollectionPage','WebPage','Article'].includes(v['@type'])){v.dateModified=config.modifiedDate;changed=true;}Object.values(v).forEach(x=>{if(x&&typeof x==='object')visit(x)})}}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:all;
 });
 after=after.replace('</head>',`<link rel="stylesheet" href="${cssUrl}">${marker}</head>`);
 return {after,changed:true,replacements,changedLinks,cardEvidence,level:hub.level};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(x=>x.includes('=')).map(x=>x.replace(/^--/,'').split(/=(.*)/s).slice(0,2)));
 const root=path.resolve(args.root||path.join(here,'.public-release')),dry=process.argv.includes('--check');
 const css=fs.readFileSync(path.join(here,'hub-content.css'),'utf8').replaceAll('\r\n','\n'),cssUrl='/assets/search-quality-cache/'+hash(css)+'.css';
 if(!dry){fs.mkdirSync(path.dirname(path.join(root,cssUrl)),{recursive:true});fs.writeFileSync(path.join(root,cssUrl),css)}
 const sf=path.join(root,'sitemap.xml'),xml=fs.readFileSync(sf,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(x=>x[1]);
 const report={version:config.version,date:config.modifiedDate,cssUrl,changed:[],pages:[],pageHashes:{}};
 for(const url of urls){const p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=fs.readFileSync(f,'utf8'),r=improveHub(before,p,cssUrl);if(r.changed&&!dry)fs.writeFileSync(f,r.after);report.pageHashes[p]=hash(r.after);if(r.changed){const{after,...data}=r;report.changed.push(p);report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...data})}}
 if(!dry){
  const changed=new Set(report.changed);const updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,b)=>{const u=b.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${config.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(sf,updated);
  const rf=path.join(root,'rss.xml'),rss=fs.readFileSync(rf,'utf8');let count=0;
  const next=rss.replace(/<item>([\s\S]*?)<\/item>/g,(all,b)=>{const u=b.match(/<link>([^<]+)<\/link>/)?.[1];if(!u)return all;const p=decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');count++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});
  if(count)fs.writeFileSync(rf,next.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,'<lastBuildDate>Tue, 27 Oct 2026 06:40:00 +0900</lastBuildDate>'));report.rssItemsUpdated=count;
 }
 report.totals={checked:urls.length,changed:report.changed.length,cards:report.pages.reduce((n,p)=>n+p.cardEvidence.length,0),national:report.pages.filter(p=>p.level===1).length,regions:report.pages.filter(p=>p.level===2).length,cities:report.pages.filter(p=>p.level===3).length};
 if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
