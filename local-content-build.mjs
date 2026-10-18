/** Enrich existing preparation areas with matched source facts and student records. */
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {nodes} from './media-placement-build.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const args=Object.fromEntries(process.argv.slice(2).filter(a=>a.includes('=')).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2)));
const root=path.resolve(args.root||path.join(here,'.public-release'));
const dryRun=process.argv.includes('--dry-run');
const data=JSON.parse(fs.readFileSync(path.join(here,'local-content-config.json'),'utf8'));
const maps=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'),'utf8'));
const marker=`<!-- local-content:${data.version} -->`;
const hash=s=>createHash('sha256').update(s.replaceAll('\r\n','\n')).digest('hex');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const plain=s=>s.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const within=(n,p)=>n.start>p.start&&n.end<p.end;
const has=(n,c)=>(n.a.class||'').split(/\s+/).includes(c);
const records={
 '개념 사이 연결':'새 개념 옆에 연결되는 이전 개념을 적고, 같은 점과 달라진 조건을 구분하세요.',
 '공부 시작 습관':'공부를 시작하기 전 준비한 자료와 첫 행동을 적고, 실제로 시작한 지점을 표시하세요.',
 '과제 난도 조절':'혼자 해결한 문항과 설명이 필요했던 문항을 나누고, 어려움이 생긴 조건을 표시하세요.',
 '과제 분량 조절':'정한 분량과 실제 완료한 분량을 나란히 적고, 남은 이유를 시간·이해·난도로 구분하세요.',
 '기초 개념 재확인':'풀이에 쓴 기본 용어의 뜻을 먼저 적고, 그 뜻을 적용하지 못한 줄을 표시하세요.',
 '내용 분류하기':'자료를 묶은 기준을 한 문장으로 적고, 같은 묶음에 넣기 어려운 항목을 따로 표시하세요.',
 '다른 사람에게 설명':'처음 보는 사람에게 설명한다고 생각하고, 필요한 정보와 설명 순서를 적어 보세요.',
 '마지막 풀이 검토':'문제에서 구하라는 것과 실제로 쓴 답을 대조하고, 마지막에 확인한 조건을 남기세요.',
 '문제 조건 읽기':'주어진 조건과 구할 것을 따로 적고, 풀이에 사용한 조건마다 표시하세요.',
 '변형 문제 살피기':'원래 문제와 바뀐 문제의 조건을 나란히 적고, 풀이에서 달라지는 단계를 표시하세요.',
 '복습 간격 조절':'처음 공부한 날과 다시 확인한 날을 적고, 다시 볼 때 도움 없이 설명한 범위를 표시하세요.',
 '비슷한 내용 비교':'비슷한 두 개념이나 문장의 공통점과 차이점을 각각 한 가지씩 적으세요.',
 '선택 근거 말하기':'답이나 풀이 방법을 고른 이유와 다른 선택이 맞지 않는 이유를 각각 남기세요.',
 '수정 과정 익히기':'처음 답안을 지우지 말고, 바꾼 부분과 바꾼 이유를 다른 줄에 적으세요.',
 '스스로 문제 만들기':'배운 내용의 조건 하나를 바꾼 문제를 만들고, 원래 풀이가 그대로 쓰이는지 확인하세요.',
 '스스로 이해 점검':'답을 가린 뒤 설명한 부분과 다시 펼쳐 본 부분을 나누어 적으세요.',
 '오답 원인 구분':'개념·문제 해석·계산이나 표현 중 어디에서 오류가 시작됐는지 표시하세요.',
 '익숙한 예시 활용':'익숙한 예시 하나로 개념을 설명한 뒤, 예시가 바뀌어도 유지되는 원리를 적으세요.',
 '자기 언어로 설명':'교재 문장을 그대로 옮기기 전에 학생의 말로 한 문장을 쓰고, 설명이 막힌 표현을 표시하세요.',
 '자료 정돈하기':'교재명·단원·쪽수·문제 번호를 함께 적고, 다시 볼 개념과 연습할 문제를 나누세요.',
 '작은 목표 설정':'오늘 할 활동 한 가지와 완료 기준을 적고, 끝난 뒤 실제로 확인한 결과를 남기세요.',
 '진행 과정 기록':'과제를 시작한 상태, 중간에 바꾼 방법, 마친 결과를 순서대로 적으세요.',
 '질문을 구체화':'모른다고만 적지 말고, 이해한 마지막 단계와 바로 다음에 막힌 단계를 질문으로 쓰세요.',
 '짧은 집중 구간':'스스로 정한 짧은 활동 구간과 완료량을 적고, 집중이 끊긴 이유를 돌아보세요.',
 '표와 그림 정리':'문장 속 정보를 표나 그림으로 옮기고, 각 항목이 무엇을 뜻하는지 설명을 붙이세요.',
 '풀이 과정 기록':'처음 풀이에서 판단이 달라진 줄에 표시하고, 판단을 바꾼 이유를 한 문장으로 적으세요.',
 '학습 목표 대화':'현재 어려운 점과 바꾸고 싶은 점을 학생의 말로 각각 적고, 먼저 해볼 활동을 고르세요.',
 '학습 순서 설계':'현재 과제의 단계를 적고, 다음 단계로 가기 전에 필요한 개념이나 자료를 표시하세요.',
 '학습 시간 배분':'읽기·생각하기·쓰기나 계산에 쓴 시간을 나누어 적고, 도움이 필요한 단계를 찾으세요.',
 '학습 전후 비교':'처음 설명과 활동 뒤의 설명을 나란히 적고, 새로 이해한 내용과 남은 질문을 나누세요.',
 '핵심 내용 요약':'문단이나 풀이의 핵심을 한 문장으로 적고, 그 문장을 뒷받침하는 근거를 표시하세요.',
 '핵심 표현 정리':'새 용어의 뜻과 직접 고른 예시를 함께 적고, 비슷한 표현과의 차이를 표시하세요.'
};
function recordFor(c){
 if(c.subject==='수학')return c.grade.startsWith('초')?'그림·수·도형이나 자료를 표현한 과정, 연결한 식, 결과를 확인한 방법을 나누어 남기세요.':'주어진 조건, 선택한 식·그림·그래프, 결과가 조건에 맞는지 확인한 근거를 나누어 남기세요.';
 if(/^초[12]$/.test(c.grade))return '선택 활동에서 들은 표현과 반응한 그림을 짝지어 남기고, 짧은 표현을 도움 없이 말했는지 표시하세요.';
 if(/^초[34]$/.test(c.grade))return '들은 표현이나 읽은 낱말, 뜻을 연결한 그림, 스스로 말한 짧은 표현을 나누어 남기세요.';
 return '근거가 되는 원문, 스스로 쓴 답이나 표현, 고친 이유와 받은 도움을 나누어 남기세요.';
}
function patchText(s,edits){edits.sort((a,b)=>b[0]-a[0]);let end=s.length+1;for(const [a,b,v] of edits){if(b>end)throw Error('Overlapping local content edits');s=s.slice(0,a)+v+s.slice(b);end=a}return s}
export function enrich(before,page,urlByPath){
 if(before.includes(marker))return {after:before,changes:[],courseKeys:[],teacherRows:[]};
 const mapping=maps.pages[page];
 if(!mapping)return {after:before,changes:[],courseKeys:[],teacherRows:[]};
 const input=before,center=data.centers[mapping.branchPath];if(!center)throw Error('Center source missing '+page);
 const ns=nodes(input),edits=[],changes=[],courseKeys=[],teacherRows=[],citations=[];
 for(const area of ns.filter(n=>mapping&&n.tag==='div'&&has(n,'hc-consult-tasks'))){
  for(const entry of ns.filter(n=>n.tag==='div'&&n.parent?.tag==='dl'&&within(n,area))){
   const dt=ns.find(n=>n.tag==='dt'&&n.parent===entry),dd=ns.find(n=>n.tag==='dd'&&n.parent===entry);
   if(!dt||!dd)throw Error('Incomplete course record '+page);
   const label=plain(input.slice(dt.open,dt.close));const match=label.match(/^(초[1-6]|중[1-3]|고[1-3]) (영어|수학)$/);
   if(!match)throw Error('Unexpected course label '+page+' '+label);
   const key=match[1]+'|'+match[2],course=data.courses[key];if(!course)throw Error('Unmatched curriculum '+key);
   const task=input.slice(dd.open,dd.close);if(!plain(task).includes(course.task))throw Error('Published course differs from source '+page+' '+key);
   const extra=`<span class="lc-task-scope" data-curriculum-grade="${course.grade}" data-curriculum-subject="${course.subject}"><strong>현재 단원 고르기:</strong> ${esc(course.focus)}.<br><strong>답안에 남길 기록:</strong> ${esc(recordFor(course))}</span>`;
   edits.push([dd.close,dd.close,extra]);courseKeys.push(key);changes.push('grade-subject-record');
  }
 }
 const teacherBox=ns.find(n=>n.tag==='div'&&n.a.id==='teacher-introductions');
 if(teacherBox&&center?.teachers.length){
  const isBranch=page===mapping.branchPath||/^\/과목별학원\/와와학습코칭센터\//.test(page);
  const selected=isBranch?center.teachers:center.teachers.slice(0,1);
  const rows=selected.map(t=>{
   if(!records[t.focus])throw Error('Missing coaching record '+t.focus);
   const target=urlByPath[center.teacherPage]+'#'+t.anchor;if(!urlByPath[center.teacherPage])throw Error('Profile canonical missing');
   teacherRows.push(t.sourceRow);citations.push(target);
   return `<div class="lc-coaching-note" data-profile-source-row="${t.sourceRow}"><p><strong>${esc(t.name)} 선생님 소개 · ${esc(t.focus)}</strong></p><p>${esc(records[t.focus])}</p><a class="lc-profile-link" href="${esc(target)}">${esc(t.name)} 선생님의 지도 관점 읽기</a></div>`;
  }).join('');
  edits.push([teacherBox.close,teacherBox.close,`<div class="lc-coaching-records"><p class="lc-source-label">${esc(center.branch)}의 공개 소개 자료를 참고한 상담 준비 예시입니다.</p>${rows}</div>`]);changes.push('branch-profile-to-consultation');
 }
 if(!changes.length)return {after:before,changes,courseKeys,teacherRows};
 let after=patchText(input,edits);
 after=after.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/g,(m,a,b,c)=>{
  const obj=JSON.parse(b);let changed=false;
  function visit(v){if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object'){
   const ts=Array.isArray(v['@type'])?v['@type']:[v['@type']];
   if(ts.some(t=>['Article','WebPage'].includes(t))){v.dateModified=data.modifiedDate;changed=true}
   if(ts.includes('Article')&&citations.length){const old=v.citation===undefined?[]:Array.isArray(v.citation)?v.citation:[v.citation];v.citation=[...old,...citations.filter(u=>!old.includes(u))];changed=true}
   if(v['@graph'])visit(v['@graph']);
  }}visit(obj);return changed?a+JSON.stringify(obj).replaceAll('<','\\u003c')+c:m;
 });
 const css='<style data-local-content>.lc-task-scope{display:block;margin-top:10px;line-height:1.8}.lc-coaching-note{margin-top:18px;border-top:1px solid rgba(23,59,48,.16);padding-top:12px}.lc-coaching-note p{margin:8px 0;line-height:1.8}.lc-source-label{font-size:.9rem;line-height:1.7}.lc-profile-link{display:flex;align-items:center;min-height:44px;width:fit-content;max-width:100%;text-decoration:underline;text-underline-offset:3px;font-weight:600}</style>';
 after=after.replace('</head>',(mapping?css:'')+marker+'</head>');return {after,changes,courseKeys,teacherRows};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const xmlFile=path.join(root,'sitemap.xml'),xml=fs.readFileSync(xmlFile,'utf8');
 const urls=[...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
 const urlByPath=Object.fromEntries(urls.map(u=>[decodeURIComponent(new URL(u).pathname),u]));
 const report={date:data.modifiedDate,version:data.version,pages:[],pageHashes:{},urls:urlByPath,changed:[],totals:{},sourceCoverage:{centers:Object.keys(data.centers).length,centersWithProfiles:Object.values(data.centers).filter(c=>c.teachers.length).length}};
 let cursor=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<urls.length){const u=urls[cursor++],p=decodeURIComponent(new URL(u).pathname),file=path.join(root,p,'index.html');const before=await fs.promises.readFile(file,'utf8'),result=enrich(before,p,urlByPath);if(!dryRun&&result.after!==before)await fs.promises.writeFile(file,result.after);const row={path:p,changes:result.changes,beforeHash:hash(before),afterHash:hash(result.after),courseKeys:result.courseKeys,teacherRows:result.teacherRows};report.pages.push(row);report.pageHashes[p]=row.afterHash;if(result.changes.length)report.changed.push(p)}}));
 if(!dryRun){
  const changed=new Set(report.changed);const updated=xml.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{const u=body.match(/<loc>([^<]+)<\/loc>/)?.[1];return u&&changed.has(decodeURIComponent(new URL(u).pathname))?all.replace(/<lastmod>[^<]+<\/lastmod>/,`<lastmod>${data.modifiedDate}</lastmod>`):all});if(updated!==xml)fs.writeFileSync(xmlFile,updated);
  let rssUpdated=0;const rssFile=path.join(root,'rss.xml');let rss=fs.readFileSync(rssFile,'utf8').replace(/<item>([\s\S]*?)<\/item>/g,(all,body)=>{const u=body.match(/<link>([^<]+)<\/link>/)?.[1];const p=u&&decodeURIComponent(new URL(u).pathname);if(!changed.has(p))return all;const s=fs.readFileSync(path.join(root,p,'index.html'),'utf8'),main=nodes(s).find(n=>n.tag==='main');if(!main)throw Error('Missing RSS main '+p);rssUpdated++;return all.replace(/<description>[\s\S]*?<\/description>/,`<description><![CDATA[${s.slice(main.start,main.end).replaceAll(']]>',']]]]><![CDATA[>')}]]></description>`)});if(rssUpdated){rss=rss.replace(/<lastBuildDate>[^<]+<\/lastBuildDate>/,`<lastBuildDate>${data.rssBuildDate}</lastBuildDate>`);fs.writeFileSync(rssFile,rss)}report.rssItemsUpdated=rssUpdated;
 }
 report.pages.sort((a,b)=>a.path.localeCompare(b.path,'ko'));report.changed.sort();report.totals={checked:report.pages.length,changed:report.changed.length,actions:report.pages.reduce((out,r)=>{for(const k of r.changes)out[k]=(out[k]||0)+1;return out},{})};
 if(args.report)fs.writeFileSync(path.resolve(args.report),JSON.stringify(report,null,2));console.log(JSON.stringify(report.totals));
}
