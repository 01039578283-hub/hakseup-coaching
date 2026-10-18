/** Replace repeated consultation prompts with grouped source-based learning questions. */
import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const config=JSON.parse(fs.readFileSync(path.join(here,'learning-levels-config.json')));
const maps=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'))).pages;
const marker=`<!-- learning-levels:${config.version} -->`;
const commonQuestion='이 과제에서 막힌 부분을 어떤 순서로 확인하고 다음 학습 범위를 정하면 좋을까요?';
const originalIntro='다음은 학년·과목별 공부 자료의 학습 참고 예시입니다. 지점의 확정 시간표나 실제 사용 교재를 뜻하지 않습니다.';
const updatedIntro='아래 과제와 학습 상태별 질문은 공부 자료의 참고 예시입니다. 학생이 직접 쓴 답안을 보고 필요한 점검을 골라보세요. 실제 분반·모집·사용 교재는 지점에 확인하며, 한 학생도 영역에 따라 다른 점검부터 시작할 수 있습니다.';
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const plain=s=>s.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const inside=(n,p)=>p&&n.start>p.start&&n.end<p.end;
const hash=s=>createHash('sha256').update(s.replaceAll('\r\n','\n')).digest('hex');
const bandName={'초':'초등','중':'중등','고':'고등'};
function anchor(key,number){return `ll-${number}-${{'초':'elementary','중':'middle','고':'high'}[key[0]]}-${key.endsWith('영어')?'english':'math'}`}
export function enrichLevels(before,p){
 const changes=[],entries=[],groups=[],replacements=[];
 if(!maps[p]||before.includes(marker))return {after:before,changes,entries,groups,replacements};
 const ns=nodes(before),areas=ns.filter(n=>n.tag==='div'&&has(n,'hc-consult-tasks'));if(!areas.length)return {after:before,changes,entries,groups,replacements};
 const ids=new Set(ns.map(n=>n.a.id).filter(Boolean)),edits=[];let areaNo=0;
 for(const area of areas){
  areaNo++;const local=new Map(),dts=ns.filter(n=>n.tag==='dt'&&inside(n,area));
  for(const dt of dts){
   const label=plain(before.slice(dt.open,dt.close)),m=label.match(/^(초[1-6]|중[1-3]|고[1-3]) (영어|수학)$/),dd=ns.find(n=>n.tag==='dd'&&n.parent===dt.parent);
   if(!m||!dd)throw Error('Unexpected curriculum entry '+p+' '+label);
   const key=m[1][0]+'|'+m[2],rows=config.levels[key];if(!rows||rows.length!==3)throw Error('Missing learning source '+key);
   const html=before.slice(dd.open,dd.close),at=html.indexOf(commonQuestion);if(at<0||html.indexOf(commonQuestion,at+1)>=0)throw Error('Repeated prompt mismatch '+p+' '+label);
   const id=anchor(key,areaNo),link=`<a class="ll-question-link" href="#${id}">${bandName[m[1][0]]} ${m[2]} 학습 상태별 질문 고르기</a>`;
   edits.push([dd.open+at,dd.open+at+commonQuestion.length,link]);
   local.set(key,{key,anchor:id,grades:[...(local.get(key)?.grades||[]),m[1]]});entries.push({grade:m[1],subject:m[2],anchor:id});changes.push('grouped-consultation-prompt');
  }
  if(!local.size)throw Error('Empty curriculum source area '+p);
  const intro=ns.find(n=>n.tag==='p'&&inside(n,area)&&plain(before.slice(n.open,n.close))===originalIntro);if(!intro)throw Error('Source introduction mismatch '+p);
  edits.push([intro.open,intro.close,updatedIntro]);replacements.push({oldText:originalIntro,newText:updatedIntro,kind:'source-scope'});
  const blocks=[];
  for(const group of local.values()){
   if(ids.has(group.anchor))throw Error('Learning anchor collision '+p);ids.add(group.anchor);
   const rows=config.levels[group.key],label=bandName[group.key[0]]+' '+group.key.split('|')[1];
   const details=rows.map(r=>`<details class="ll-question" data-learning-level="${r.level}" data-learning-source-row="${r.sourceRow}"><summary><strong>${r.level} 점검</strong><span>${esc(r.target)}</span></summary><div class="ll-answer"><p><strong>공부 순서 예시:</strong> ${esc(r.sequence)}</p><p><strong>확인 과제:</strong> ${esc(r.task)}</p><p><strong>다음 상담에서 물을 질문:</strong> ${esc(r.question)}</p></div></details>`).join('');
   const optional=group.key==='초|영어'&&group.grades.some(g=>['초1','초2'].includes(g))?'<p class="ll-optional">초1·초2 영어는 정규 교과 밖의 선택 활동 예시입니다. 학교 정규 영어의 선행 필수 과정으로 보지 마세요.</p>':'';
   blocks.push(`<div class="ll-group" id="${group.anchor}" data-learning-key="${group.key}"><h4>${esc(label)} 답안 상태별 상담 질문</h4>${details}${optional}</div>`);
   groups.push({...group,sourceRows:rows.map(r=>r.sourceRow)});changes.push('learning-state-questions');
  }
  const dl=ns.find(n=>n.tag==='dl'&&inside(n,area));if(!dl)throw Error('Missing curriculum list '+p);edits.push([dl.end,dl.end,`<div class="ll-groups">${blocks.join('')}</div>`]);
 }
 edits.sort((a,b)=>b[0]-a[0]);let s=before,end=s.length+1;for(const[a,b,v]of edits){if(b>end)throw Error('Overlapping learning edit');s=s.slice(0,a)+v+s.slice(b);end=a}
 s=s.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(all,a,b,c)=>{const obj=JSON.parse(b);let changed=false;function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){const t=Array.isArray(v['@type'])?v['@type']:[v['@type']];if(t.some(x=>['Article','WebPage'].includes(x))){v.dateModified=config.modifiedDate;changed=true}if(v['@graph'])visit(v['@graph'])}}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:all});
 const css='<style data-learning-levels>.ll-groups{margin-top:22px}.ll-group{margin:18px 0;scroll-margin-top:100px}.ll-group h4{font-size:1rem;margin:0 0 10px}.ll-question{border:1px solid rgba(23,59,48,.16);border-radius:12px;margin:10px 0;background:rgba(255,255,255,.65)}.ll-question summary{cursor:pointer;min-height:44px;padding:12px 14px;box-sizing:border-box;line-height:1.7}.ll-question summary strong{margin-right:10px}.ll-answer{padding:0 14px 12px}.ll-answer p,.ll-optional{line-height:1.8;overflow-wrap:anywhere}.ll-question-link{display:inline-flex;align-items:center;min-height:44px;max-width:100%;text-decoration:underline;text-underline-offset:3px;font-weight:600}.ll-question summary:focus-visible,.ll-question-link:focus-visible{outline:2px solid currentColor;outline-offset:3px}</style>';
 s=s.replace('</head>',css+marker+'</head>');return {after:s,changes,entries,groups,replacements};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).filter(a=>a.includes('=')).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2))),root=path.resolve(args.root||path.join(here,'.public-release')),dry=process.argv.includes('--dry-run');
 const xmlFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(xmlFile,'utf8'),urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const report={date:config.modifiedDate,version:config.version,pages:[],pageHashes:{},urls:{},changed:[],totals:{}};let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const url=urls[cursor++],p=decodeURIComponent(new URL(url).pathname),f=path.join(root,p,'index.html'),before=await fs.promises.readFile(f,'utf8'),r=enrichLevels(before,p);if(!dry&&r.after!==before)await fs.promises.writeFile(f,r.after);const {after,...details}=r;report.pages.push({path:p,beforeHash:hash(before),afterHash:hash(after),...details});report.pageHashes[p]=hash(after);report.urls[p]=url;if(r.changes.length)report.changed.push(p)}}));
 if(!dry){const changed=new Set(report.changed),updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${config.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(xmlFile,updated);
  const f=path.join(root,'rss.xml');let count=0;let rss=fs.readFileSync(f,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{const u=body.match(/<link>([^<]+)<\/link>/)?.[1],p=u&&decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;count++;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('RSS main missing');return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});if(count){rss=rss.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,`<lastBuildDate>${config.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(f,rss)}report.rssItemsUpdated=count;
 }
 report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.changed.sort();report.totals={checked:report.pages.length,changed:report.changed.length,entries:report.pages.reduce((n,r)=>n+r.entries.length,0),groups:report.pages.reduce((n,r)=>n+r.groups.length,0)};if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
