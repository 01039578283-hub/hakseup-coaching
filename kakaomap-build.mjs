/** Add verified branch directions without rewriting existing text or media. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.argv.find(x=>x.startsWith('--root='))?.slice(7)||path.join(here,'.public-release'));
const config=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'),'utf8'));
const reportArg=process.argv.find(x=>x.startsWith('--report='))?.slice(9);
const marker='<!-- kakao-directions:20261015:start -->',end='<!-- kakao-directions:20261015:end -->';
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const base='https://xn--ru4bi8s1tac0p.kr';
function modified(s,p){return s.replace(/<script\b[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi,(all,json)=>{
 const value=JSON.parse(json);let changed=false;
 function visit(v){if(!v||typeof v!=='object')return;if(!Array.isArray(v)&&v.dateModified){let own;try{own=decodeURIComponent(new URL(v.url||v['@id']||'',base).pathname)}catch{}if(own===p&&v.dateModified<config.reviewedDate){v.dateModified=config.reviewedDate;changed=true}}Object.values(v).forEach(visit)}visit(value);
 return changed?all.replace(json,JSON.stringify(value)):all;
})}
const assetNames=[config.css,...Object.values(config.branches).map(b=>b.frame)];
for(const name of assetNames){
 const source=path.join(here,name),dest=path.join(root,name);
 if(!fs.existsSync(source))throw Error('Missing reviewed map asset '+name);
 fs.mkdirSync(path.dirname(dest),{recursive:true});
 if(source!==dest)fs.copyFileSync(source,dest);
}
function head(s){const link=`<link rel="stylesheet" href="${esc(config.css)}">`;return s.includes(link)?s:s.replace('</head>',link+'</head>')}
function directions(b){
 return marker+`<section class="km-directions" id="directions" aria-labelledby="directions-title"><h2 id="directions-title">찾아오시는 길</h2><p><strong>${esc(b.branch)}</strong> 방문 위치를 카카오맵에서 확인하세요.</p><address>${esc(b.address)}</address><iframe class="km-map-frame" src="${esc(b.frame)}" title="${esc(b.branch)} 카카오맵 위치 안내" loading="lazy" width="640" height="394" referrerpolicy="strict-origin-when-cross-origin"></iframe><p><a class="km-map-link" href="${esc(b.mapUrl)}" target="_blank" rel="noopener noreferrer">카카오맵에서 ${esc(b.branch)} 지도·길찾기 열기</a></p><p class="km-map-note">방문 전 층·호실과 상담 가능 시간을 지점에 확인해 주세요.</p></section>`+end;
}
let changed=0;const rows=[];
for(const [p,entry] of Object.entries(config.pages)){
 const file=path.join(root,p,'index.html');let s=fs.readFileSync(file,'utf8');const before=s;
 const b=config.branches[entry.branchPath];if(!b)throw Error('Unknown branch '+p);
 if(!s.includes(marker)){
  if(/id=["']directions["']/.test(s))throw Error('Directions anchor already used '+p);
  const images=[...s.matchAll(/<img\b[^>]*>/g)].filter(m=>m[0].includes(`src="${entry.existingMap}"`));
  if(images.length!==1)throw Error('Expected exactly one existing map '+p);
  const image=images[0],closing='</'+entry.containerTag+'>';
  const at=s.indexOf(closing,image.index+image[0].length);
  if(at<0)throw Error('Map container missing '+p);
  const position=at+closing.length;
  s=s.slice(0,position)+directions(b)+s.slice(position);s=modified(head(s),p);
  fs.writeFileSync(file,s);changed++;
 }
 if((s.match(/id="directions"/g)||[]).length!==1||!s.includes(`src="${b.frame}"`))throw Error('Directions mismatch '+p);
 rows.push({path:p,branch:b.branch,frame:b.frame,changed:s!==before});
}
// Hubs expose direct HTML links to each branch map without loading many maps.
const hubs=new Map();
for(const [bp,b] of Object.entries(config.branches)){
 const region='/지점안내/'+bp.split('/')[2]+'/';
 if(!hubs.has(region))hubs.set(region,[]);hubs.get(region).push([bp,b]);
}
hubs.set('/지점안내/',null);
let hubChanged=0;
for(const [p,branches] of hubs){
 const file=path.join(root,p,'index.html');if(!fs.existsSync(file))throw Error('Missing branch hub '+p);
 let s=fs.readFileSync(file,'utf8');if(s.includes(marker))continue;
 const items=branches?branches.sort((a,b)=>a[1].branch.localeCompare(b[1].branch,'ko')).map(([bp,b])=>`<li><a href="${esc(bp)}#directions">${esc(b.branch)} 찾아오시는 길<small>${esc(b.address)}</small></a></li>`).join(''):[...hubs.keys()].filter(v=>v!==p).map(r=>`<li><a href="${esc(r)}#branch-map-directory">${esc(r.split('/')[2])} 지점별 지도 안내</a></li>`).join('');
 const block=marker+`<section class="km-hub" id="branch-map-directory" aria-labelledby="branch-map-directory-title"><h2 id="branch-map-directory-title">지점별 찾아오시는 길</h2><p>방문할 지점을 선택하면 위치 안내 이미지 바로 아래의 카카오맵과 길찾기를 확인할 수 있습니다.</p><ul>${items}</ul></section>`+end;
 if(!s.includes('</main>'))throw Error('Hub main missing '+p);
 s=modified(head(s.replace('</main>',block+'</main>')),p);fs.writeFileSync(file,s);hubChanged++;rows.push({path:p,role:'hub',changed:true});
}
// Only actual changed page dates advance; all existing loc/canonical values stay.
const sitemapFile=path.join(root,'sitemap.xml');let sm=fs.readFileSync(sitemapFile,'utf8');
const changedPaths=new Set([...Object.keys(config.pages),...hubs.keys()]);
sm=sm.replace(/<url>([\s\S]*?)<\/url>/g,(all,body)=>{
 const loc=body.match(/<loc>([^<]+)<\/loc>/)?.[1];if(!loc)return all;
 const p=decodeURIComponent(new URL(loc.replaceAll('&amp;','&'),base).pathname);
 if(!changedPaths.has(p))return all;
 return all.replace(/<lastmod>([^<]+)<\/lastmod>/,(tag,date)=>date<config.reviewedDate?`<lastmod>${config.reviewedDate}</lastmod>`:tag);
});fs.writeFileSync(sitemapFile,sm);
if(reportArg)fs.writeFileSync(reportArg,JSON.stringify({pages:rows,totals:{details:rows.filter(r=>!r.role).length,hubs:hubs.size,branches:Object.keys(config.branches).length,changed,hubChanged}},null,2));
console.log(JSON.stringify({kakaoDirections:{details:Object.keys(config.pages).length,branches:Object.keys(config.branches).length,hubs:hubs.size,changed,hubChanged,originalImagesPreserved:true,lazyFrames:true}}));
