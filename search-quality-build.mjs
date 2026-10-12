/** Final, deterministic public transform. Dates record reviewed changes, never build time. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const args=Object.fromEntries(process.argv.slice(2).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2)));
const root=path.resolve(args.root||path.join(here,'.public-release'));
const config=JSON.parse(fs.readFileSync(path.join(here,'search-quality-config.json'),'utf8'));
const marker=`<!-- search-quality:${config.version} -->`;
const base='https://xn--ru4bi8s1tac0p.kr';
const photoPaths=new Set(config.photoPaths);
const hash=b=>createHash('sha256').update(b).digest('hex');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const decode=s=>s.replace(/&(?:amp|quot|apos|lt|gt|#\d+|#x[\da-f]+);/gi,m=>({'&amp;':'&','&quot;':'"','&apos;':"'",'&lt;':'<','&gt;':'>'}[m]??String.fromCodePoint(m.startsWith('&#x')?parseInt(m.slice(3),16):parseInt(m.slice(2)))));
const plain=s=>decode(s.replace(/<[^>]*>/g,' ')).replace(/\s+/g,' ').trim();
function attrs(s){const out={};for(const m of s.matchAll(/([^\s=<>/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g))out[m[1].toLowerCase()]=decode(m[2]??m[3]??m[4]??'');return out}
function urlPath(u){try{return decodeURIComponent(new URL(decode(u),base).pathname)}catch{return ''}}
const sitemapDates=new Map([...fs.readFileSync(path.join(root,'sitemap.xml'),'utf8').matchAll(/<url>\s*<loc>([^<]+)<\/loc>\s*<lastmod>([^<]+)<\/lastmod>/g)].map(m=>[urlPath(m[1]),m[2]]));
// Keep source byte ranges; do not reserialize body images, maps or manuscripts.
function nodes(s){
 const all=[],stack=[],voids=new Set('area base br col embed hr img input link meta param source track wbr'.split(' '));
 const re=/<!--[\s\S]*?-->|<![^>]*>|<\/?[A-Za-z][^>]*>/g;let m;
 while((m=re.exec(s))){const t=m[0];if(t.startsWith('<!'))continue;const name=t.match(/^<\/?([^\s/>]+)/)[1].toLowerCase();
  if(t.startsWith('</')){let i=stack.length-1;while(i>=0&&stack[i].tag!==name)i--;if(i>=0){const n=stack[i];n.close=m.index;n.end=re.lastIndex;stack.length=i;}continue;}
  const n={tag:name,start:m.index,open:re.lastIndex,close:re.lastIndex,end:re.lastIndex,a:attrs(t.slice(name.length+1,-1)),parent:stack.at(-1)};all.push(n);
  if(['script','style','textarea'].includes(name)){const end=new RegExp('</'+name+'\\s*>','ig');end.lastIndex=re.lastIndex;const c=end.exec(s);if(!c)throw Error('Unclosed '+name);n.close=c.index;n.end=end.lastIndex;re.lastIndex=n.end;}
  else if(!voids.has(name)&&!t.endsWith('/>'))stack.push(n);
 }
 return all;
}
function edits(s,list){list.sort((a,b)=>b[0]-a[0]);let bound=s.length+1;for(const [a,b,v] of list){if(b>bound)throw Error('Overlapping edits');s=s.slice(0,a)+v+s.slice(b);bound=a;}return s}
const inside=(n,tag)=>{for(let p=n.parent;p;p=p.parent)if(p.tag===tag)return true;return false};
const inner=(s,n)=>s.slice(n.open,n.close);
const css=`.sq-resources,.sq-preparation,.sq-shared-note{box-sizing:border-box;width:calc(100% - 36px);max-width:1160px;margin:32px auto;padding:26px;border:1px solid #ddd9cf;border-radius:20px;background:#fffdf7;color:#273c32;line-height:1.8}.sq-resources h2,.sq-preparation h2{font-size:clamp(1.25rem,2.3vw,1.65rem);line-height:1.5;margin:0 0 12px}.sq-resources>p{margin:0 0 20px}.sq-resource-grid{display:grid;grid-template-columns:1.6fr 1fr 1fr;gap:24px}.sq-resource-grid h3{font-size:1.06rem;margin:0 0 10px}.sq-resource-grid ul{padding:0;margin:0;list-style:none}.sq-resource-grid li+li{margin-top:8px}.sq-resource-grid a{display:block;color:#244e3e;text-decoration:underline;text-underline-offset:3px;line-height:1.6;padding:6px 0;overflow-wrap:anywhere}.sq-resource-grid a:hover{color:#8e482c}.sq-resource-grid a:focus-visible{outline:3px solid #367757;outline-offset:3px;border-radius:4px}.sq-preparation dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.sq-preparation dl>div{background:white;border:1px solid #e0e4da;border-radius:12px;padding:16px}.sq-preparation dt{font-weight:700}.sq-preparation dd{margin:8px 0 0}.sq-preparation li{margin:8px 0}.sq-preparation p:last-child{margin-bottom:0}.sq-shared-note{padding:18px 24px}.sq-shared-note p{margin:0}@media(max-width:700px){.sq-resource-grid,.sq-preparation dl{grid-template-columns:1fr}.sq-resources,.sq-preparation{padding:20px;margin:24px auto}.sq-resource-grid{gap:20px}.sq-resource-grid>div+div{border-top:1px solid #e0e4da;padding-top:18px}}`;
const assetDir=path.join(root,'assets/search-quality-cache');fs.mkdirSync(assetDir,{recursive:true});
function asset(content){const name=hash(content)+'.css';fs.writeFileSync(path.join(assetDir,name),content);return '/assets/search-quality-cache/'+name}
const qualityCss=asset(css),cssMap=new Map();
function cachedCss(href){
 const u=new URL(decode(href),base);if(u.origin!==base||!u.pathname.endsWith('.css')||u.pathname.startsWith('/assets/search-quality-cache/'))return href;
 if(cssMap.has(u.pathname))return cssMap.get(u.pathname);
 const file=path.resolve(root,decodeURIComponent(u.pathname).slice(1));if(!file.startsWith(root+path.sep)||!fs.existsSync(file))throw Error('Missing CSS '+href);
 let text=fs.readFileSync(file,'utf8').replaceAll('\r\n','\n');
 // Moving CSS must preserve relative font/image/import locations.
 text=text.replace(/url\(\s*(['"]?)([^)'"\s]+)\1\s*\)/g,(m,q,url)=>url.startsWith('#')||/^(?:data:|https?:|\/)/.test(url)?m:`url("${new URL(url,u).pathname}")`);
 text=text.replace(/(@import\s+)(['"])([^'"]+)\2/g,(m,p,q,url)=>/^(?:https?:|\/)/.test(url)?m:p+q+new URL(url,u).pathname+q);
 const result=asset(text);cssMap.set(u.pathname,result);return result;
}
function preparation(g){
 const math=g.subject==='수학',stage=g.grade[0],question=math?(stage==='초'?'문제의 수량과 그림을 어떻게 식으로 옮겼는지':stage==='중'?'정의·성질과 조건을 어느 풀이 단계에 적용했는지':'조건에서 필요한 개념을 고르고 풀이 근거를 어떻게 연결했는지'):(stage==='초'?'소리와 뜻을 연결하고 짧은 문장을 스스로 읽을 수 있는지':stage==='중'?'문장 구조를 나누고 지문의 근거 문장을 찾을 수 있는지':'긴 지문의 논리 관계와 선택지 판단 근거를 설명할 수 있는지');
 const rows=math?[
 ['오늘 확인할 자료','현재 배우는 단원에서 문제 한 개를 고르고, 교재명·쪽수·문제 번호를 적으세요.'],
 ['처음 풀었던 과정','정답을 보고 고치기 전의 식·그림·풀이를 남기세요. '+question+' 표시하세요.'],
 ['막힌 지점과 받은 도움','문제 해석·개념 선택·계산 중 막힌 단계와 도움받은 설명을 한 줄씩 적으세요.'],
 ['다시 확인할 과제','비슷한 문제 한 개를 도움 없이 풀고, 처음과 달라진 풀이와 아직 남은 질문을 기록하세요.']
 ]:[
 ['오늘 확인할 자료','학교나 현재 교재에서 짧은 문장·지문 하나를 고르고 교재명과 쪽수를 적으세요.'],
 ['혼자 읽은 흔적','모르는 어휘와 이해하기 어려운 부분을 표시하세요. '+question+' 확인하세요.'],
 ['판단 근거와 받은 도움','답을 고른 이유를 본문에서 찾아 표시하고, 해설을 보기 전 생각과 설명받은 내용을 나눠 적으세요.'],
 ['다시 확인할 과제','다음 날 같은 내용을 자기 말로 설명한 뒤 새 문장·지문에도 적용되는지 확인하고 질문을 남기세요.']
 ];
 return `<section class="sq-preparation" id="learning-preparation-record" aria-labelledby="learning-preparation-title"><h2 id="learning-preparation-title">${esc(g.grade)} ${g.subject} 학습 기록과 상담 질문</h2><p>${esc(g.center)}의 해당 학년 개설은 확인이 필요합니다. 아래는 수업 등록 여부와 관계없이 학생과 보호자가 함께 작성할 수 있는 기록 항목입니다.</p><dl>${rows.map(([a,b])=>`<div><dt>${a}</dt><dd>${b}</dd></div>`).join('')}</dl><h3>기록을 보며 지점에 확인할 질문</h3><ul><li>${esc(g.grade)} ${g.subject} 수강이 현재 가능한가요? 안내 자료에 없는 학년이라면 먼저 어떤 조건을 확인해야 하나요?</li><li>학생이 가져온 풀이·읽기 기록에서 먼저 보완할 부분은 무엇이고, 시작 전에 필요한 학습은 무엇인가요?</li><li>수강이 가능하다면 실제 담당 선생님, 수업 요일·시간, 교재와 교습비는 어떻게 확인하나요?</li></ul><p>학교 진도와 평가 범위는 학생이 받은 최신 안내로 확인하세요. 이 기록 항목은 실제 학생 사례나 특정 지점의 개설 수업을 뜻하지 않습니다.</p></section>`;
}
const files=[];function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){if(e.isSymbolicLink())throw Error('Public symlink');const f=path.join(dir,e.name);if(e.isDirectory())walk(f);else if(e.name.endsWith('.html'))files.push(f)}}walk(root);
const report={version:config.version,pages:[],css:[],totals:{}};const dates=new Map();
for(const file of files){
 const page='/'+path.relative(root,file).replaceAll('\\','/').replace(/index\.html$/,'');
 let s=fs.readFileSync(file,'utf8');if(!s.includes('</head>'))continue;const before=s,changes=[];let ns=nodes(s),patch=[];
 if(!s.includes(marker)){
  const groups=['education-information','study-curriculum','teacher-introductions'].map(id=>ns.find(n=>n.tag==='section'&&n.a.id===id));
  const gallery=ns.find(n=>n.tag==='section'&&n.a['data-branch-photo-gallery']==='true');
  if(groups.every(Boolean)&&gallery){
   const labels=['공부 방법과 교육정보','학년·과목별 공부 계획','선생님 소개'];
   const columns=groups.map((n,i)=>{const links=ns.filter(a=>a.tag==='a'&&a.start>n.start&&a.end<n.end).map(a=>`<li><a href="${esc(a.a.href)}">${inner(s,a)}</a></li>`).join('');return `<div id="${n.a.id}"><h3>${labels[i]}</h3><ul>${links}</ul></div>`}).join('');
   const section=`<section class="sq-resources" id="related-learning-resources" aria-labelledby="related-learning-resources-title"><h2 id="related-learning-resources-title">학습 준비에 도움이 되는 자료</h2><p>현재 필요한 공부 방법과 학습 계획을 살펴보고, 선생님 소개에서 상담할 질문을 준비하세요. 실제 담당 학년·과목과 수강 가능 여부는 지점에 확인해 주세요.</p><div class="sq-resource-grid">${columns}</div></section>`;
   groups.forEach(n=>patch.push([n.start,n.end,'']));patch.push([gallery.start,gallery.start,section]);changes.push('related-resources');
  }
  // Remove only ordinary-body duplicates, preserving all FAQ answers and anchors.
  const repeated=new Map();let removed=0;
  for(const n of ns.filter(n=>n.tag==='p'&&inside(n,'main')&&!inside(n,'details')&&!groups.some(g=>g&&n.start>g.start&&n.end<g.end))){const value=plain(inner(s,n));if(value.length<60||/<(?:a|img)\b/.test(inner(s,n))||n.a.id)continue;if(!repeated.has(value))repeated.set(value,[]);repeated.get(value).push(n);}
  for(const [value,matches] of repeated){if(matches.length<2)continue;const first=matches[0];
   // A condition shared by multiple course cards belongs before their grid.
   // Keeping it inside only the first card would incorrectly narrow its scope.
   if(matches.every(n=>n.parent?.tag==='article')&&first.parent.parent?.tag==='div'){
    matches.forEach(n=>patch.push([n.start,n.end,'']));const grid=first.parent.parent;
    patch.push([grid.start,grid.start,`<p class="sq-course-condition">${esc(value)}</p>`]);
   }else matches.slice(1).forEach(n=>patch.push([n.start,n.end,'']));
   removed+=matches.length-1;
  }
  if(removed)changes.push('duplicate-paragraphs:'+removed);
  const g=config.unknownGrades[page];
  if(g){const facts=ns.find(n=>n.a.id==='regional-page-facts');if(!facts)throw Error('Missing grade facts '+page);patch.push([facts.end,facts.end,preparation(g)]);changes.push('grade-preparation');}
  const shared='후보 교재는 학년·학기·과목명·개정판과 현재 수준을 확인해 선택하세요. 특정 지점이 실제 사용한다는 뜻은 아닙니다.';
  if(page==='/공부커리큘럼/수준별-학습/'){
   const notes=ns.filter(n=>n.tag==='p'&&plain(inner(s,n))===shared),hero=ns.find(n=>n.tag==='section'&&(n.a.class||'').includes('cur-hero'));
   if(notes.length>1&&hero){notes.forEach(n=>patch.push([n.start,n.end,'']));patch.push([hero.end,hero.end,`<aside class="sq-shared-note" id="book-selection-note"><p>${shared}</p></aside>`]);changes.push('curriculum-common-note');}
  }
  s=edits(s,patch);ns=nodes(s);patch=[];
  if(page==='/안내-작성기준/'){
   const replacements={responsibility:'<h2>학원 정보를 확인할 때</h2><p>지점별 주소·등록 정보·개설 학년은 제공된 센터 자료를 바탕으로 안내합니다. 방문 전에는 희망 학년과 과목, 현재 모집 여부, 실제 수업 장소를 지점에 함께 확인하세요. 학교 목록은 상담 참고 자료이며 제휴나 학교별 전용반을 뜻하지 않습니다.</p>',updates:'<h2>다른 정보를 발견했을 때</h2><p>지점명과 해당 페이지 주소, 확인하려는 항목을 함께 알려 주세요. 개설 학년 안내와 현재 모집 상황은 다를 수 있으므로 수업 가능 여부는 등록 전에 다시 확인하세요.</p><div class="hc-links"><a href="/%EC%83%81%EB%8B%B4%EB%AC%B8%EC%9D%98/">정보 확인·정정 문의 <span aria-hidden="true">↗</span></a><a href="/%EC%A7%80%EC%A0%90%EC%95%88%EB%82%B4/">전국 지점 찾기 <span aria-hidden="true">↗</span></a></div>'};
   for(const [id,v] of Object.entries(replacements)){const n=ns.find(n=>n.tag==='section'&&n.a.id===id);if(!n)throw Error('Missing information section');patch.push([n.open,n.close,`<div class="hc-wrap">${v}</div>`]);}
   s=edits(s,patch).replaceAll('자료 출처와 안내 작성 기준','학원 정보 확인 안내').replaceAll('안내 작성 기준','학원 정보 확인 안내').replaceAll('EDITORIAL POLICY','INFORMATION CHECK').replaceAll('작성·편집 주체','학원 정보를 확인할 때').replaceAll('수정일과 정정 요청','다른 정보를 발견했을 때');
   s=s.replaceAll('직통번호·운영시간·지도 좌표·학생 사례는 확인 자료가 있을 때만 안내합니다. 확인되지 않은 성적 향상이나 후기를 실제 사례처럼 만들지 않습니다.','직통번호·운영시간·정확한 방문 위치는 지점에 확인하세요. 학습 예시는 학생이 따라 해 볼 참고 자료이며 실제 성적 향상이나 후기를 뜻하지 않습니다.');
   changes.push('information-check-guide');
  }
  s=s.replace(/<aside\b[^>]*\bid="editorial-note"[^>]*>[\s\S]*?<\/aside>/g,()=>{changes.push('information-note');return '<aside class="hr-editorial hc-wrap" id="editorial-note"><p>지점 정보는 제공된 센터 자료를 기준으로 안내합니다. 기재된 개설 학년과 현재 모집 상황은 다를 수 있으니, 희망 학년·과목의 수강 가능 여부와 방문 위치를 상담에서 확인해 주세요.</p><a href="/%EC%95%88%EB%82%B4-%EC%9E%91%EC%84%B1%EA%B8%B0%EC%A4%80/">학원 정보 확인 안내</a></aside>'});
  if(g){s=s.replaceAll(g.oldH1,g.newH1);const oldTitle=inner(before,nodes(before).find(n=>n.tag==='title')),newTitle=oldTitle.replace(g.subject+'학원',g.subject+' 학습 준비');s=s.replaceAll(oldTitle,newTitle);const newDesc=g.description.replace(g.subject+'학원 안내는',g.subject+' 학습 준비는');s=s.replaceAll(g.description,newDesc);}
  s=s.replace(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi,(all,at,label)=>{const a=attrs(at),target=urlPath(a.href||''),g=config.unknownGrades[target];if(g&&plain(label)===g.oldH1){changes.push('grade-link-label');return `<a${at}>${esc(g.newH1)}</a>`;}if(target==='/안내-작성기준/'&&/작성|편집/.test(plain(label))){changes.push('information-link-label');return `<a${at}>학원 정보 확인 안내</a>`;}return all;});
  if(changes.length)s=s.replace('</head>',marker+'</head>');
 }
 const contentChanged=s.includes(marker),recorded=[sitemapDates.get(page)||'',config.knownModifiedDates?.[page]||''].sort().at(-1)||null;
 const modified=contentChanged?config.modifiedDate:photoPaths.has(page)?[config.photoModifiedDate,recorded||''].sort().at(-1):recorded;
 if(modified)dates.set(page,modified);
 s=s.replace(/<script\b[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi,(all,json)=>{
  const value=JSON.parse(json);let changed=false;
  function walk(v){if(!v||typeof v!=='object')return;if(!Array.isArray(v)){
   if(v.publishingPrinciples&&urlPath(v.publishingPrinciples)==='/안내-작성기준/'){delete v.publishingPrinciples;changed=true;}
   if(modified&&v.dateModified&&urlPath(v.url||v['@id']||'')===page&&v.dateModified<modified){v.dateModified=modified;changed=true;}
  }Object.values(v).forEach(walk)}walk(value);return changed?all.replace(json,JSON.stringify(value)):all;
 });
 s=s.replace(/<link\b[^>]*>/gi,tag=>{const a=attrs(tag.slice(5,-1));if(a.rel!=='stylesheet'||!a.href)return tag;const cached=cachedCss(a.href);return cached===a.href?tag:tag.replace(/\bhref\s*=\s*(['"])[\s\S]*?\1/i,`href="${cached}"`)});
 if((s.includes('sq-resources')||s.includes('sq-preparation')||s.includes('sq-shared-note'))&&!s.includes(`href="${qualityCss}"`))s=s.replace('</head>',`<link rel="stylesheet" href="${qualityCss}"></head>`);
 if(s!==before)fs.writeFileSync(file,s);
 report.pages.push({path:page,changed:s!==before,contentChanged,changes,modified,sha256:hash(s)});
}
const sm=path.join(root,'sitemap.xml');let sitemap=fs.readFileSync(sm,'utf8');sitemap=sitemap.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const loc=body.match(/<loc>([\s\S]*?)<\/loc>/)?.[1],date=dates.get(urlPath(loc||''));if(!date)return all;return all.replace(/<lastmod>([^<]+)<\/lastmod>/,(m,old)=>old<date?`<lastmod>${date}</lastmod>`:m)});fs.writeFileSync(sm,sitemap);
const rssFile=path.join(root,'rss.xml');if(fs.existsSync(rssFile)){
 let rss=fs.readFileSync(rssFile,'utf8');let changed=false;
 rss=rss.replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{const loc=body.match(/<link>([^<]*)<\/link>/)?.[1],p=urlPath(loc||''),file=path.join(root,p,'index.html');if(!fs.existsSync(file))return all;const s=fs.readFileSync(file,'utf8'),ns=nodes(s),main=ns.find(n=>n.tag==='main'),title=ns.find(n=>n.tag==='title');if(!main||!title)return all;let result=all.replace(/<title>[\s\S]*?<\/title>/,`<title>${esc(plain(inner(s,title)))}</title>`);if(dates.has(p))result=result.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`);if(result!==all)changed=true;return result;});
 if(changed)rss=rss.replace(/<lastBuildDate>[^<]*<\/lastBuildDate>/,`<lastBuildDate>${config.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(rssFile,rss);
}
report.css=[...cssMap.entries()];report.totals={pages:report.pages.length,changed:report.pages.filter(p=>p.changed).length,content:report.pages.filter(p=>p.contentChanged).length,cssFiles:cssMap.size+1};
if(args.report)fs.writeFileSync(args.report,JSON.stringify(report,null,2));
console.log(JSON.stringify({searchQuality:report.totals,modifiedDate:config.modifiedDate}));
