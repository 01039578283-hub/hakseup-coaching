/** Move the original body/map section before branch facts. No CSS reordering. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.argv.find(x=>x.startsWith('--root='))?.slice(7)||path.join(here,'.public-release'));
const config=JSON.parse(fs.readFileSync(path.join(here,'kakaomap-config.json'),'utf8'));
const reportPath=process.argv.find(x=>x.startsWith('--report='))?.slice(9);
const audit=process.argv.includes('--audit-only');
const hash=s=>createHash('sha256').update(s).digest('hex');
const attrs=s=>Object.fromEntries([...s.matchAll(/([^\s=<>/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)].map(m=>[m[1].toLowerCase(),m[2]??m[3]??m[4]??'']));
export function nodes(s){
 const all=[],stack=[],voids=new Set('area base br col embed hr img input link meta param source track wbr'.split(' '));
 const re=/<!--[\s\S]*?-->|<![^>]*>|<\/?[A-Za-z][^>]*>/g;let m;
 while((m=re.exec(s))){const t=m[0];if(t.startsWith('<!'))continue;const tag=t.match(/^<\/?([^\s/>]+)/)[1].toLowerCase();
  if(t.startsWith('</')){let i=stack.length-1;while(i>=0&&stack[i].tag!==tag)i--;if(i>=0){const n=stack[i];n.close=m.index;n.end=re.lastIndex;stack.length=i;}continue;}
  const n={tag,start:m.index,open:re.lastIndex,close:re.lastIndex,end:re.lastIndex,a:attrs(t.slice(tag.length+1,-1)),parent:stack.at(-1)};all.push(n);
  if(['script','style','textarea'].includes(tag)){const end=new RegExp('</'+tag+'\\s*>','ig');end.lastIndex=re.lastIndex;const c=end.exec(s);if(!c)throw Error('Unclosed '+tag);n.close=c.index;n.end=end.lastIndex;re.lastIndex=n.end;}
  else if(!voids.has(tag)&&!t.endsWith('/>'))stack.push(n);
 }
 return all;
}
export function analyze(s,entry,p){
 const ns=nodes(s);
 const maps=ns.filter(n=>n.tag==='img'&&n.a.src===entry.existingMap);
 if(maps.length!==1)throw Error('Expected one original map '+p);
 let media=maps[0].parent;while(media&&media.tag!=='section')media=media.parent;
 if(!media||media.end<=media.open)throw Error('Missing complete media section '+p);
 const target=ns.find(n=>n.tag==='section'&&(['center-info','regional-page-facts','local-course-facts'].includes(n.a.id)||(n.a.class||'').split(/\s+/).includes('center-profile-overview')));
 if(!target||target.end<=target.open)throw Error('Missing branch facts section '+p);
 if(media.start<target.end&&media.end>target.start)throw Error('Media/facts overlap '+p);
 if(media.parent!==target.parent||media.parent?.tag!=='main')throw Error('Different media/facts context '+p);
 const content=s.slice(media.start,media.end);
 const images=ns.filter(n=>n.tag==='img'&&n.start>media.start&&n.end<media.end);
 if(images.length<2)throw Error('Body/map pair missing '+p);
 if(content.includes('data-branch-photo-gallery')||content.includes('data-branch-representative'))throw Error('Bottom photo inside moved section '+p);
 if((content.match(/id="directions"/g)||[]).length!==1)throw Error('Directions not grouped with map '+p);
 const targetLabel=target.a.id||'center-profile-overview';
 return {ns,media,target,content,images,targetLabel};
}
export function transform(s,entry,p){
 const a=analyze(s,entry,p);if(a.media.end<=a.target.start)return {after:s,a,changed:false};
 const rest=s.slice(0,a.media.start)+s.slice(a.media.end);
 const after=rest.slice(0,a.target.start)+a.content+rest.slice(a.target.start);
 return {after,a,changed:true};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const pages=Object.entries(config.pages),results=new Array(pages.length);let cursor=0,done=0;
 await Promise.all(Array.from({length:8},async()=>{while(cursor<pages.length){const i=cursor++,[p,entry]=pages[i],f=path.join(root,p,'index.html'),s=await fs.promises.readFile(f,'utf8');
  const {after,a,changed}=transform(s,entry,p);
  if(!audit&&changed)await fs.promises.writeFile(f,after);
  results[i]={path:p,target:a.targetLabel,section:a.media.a.id||a.media.a.class,changed,originalHash:hash(s.replaceAll('\r\n','\n')),mediaHash:hash(a.content.replaceAll('\r\n','\n')),restHash:hash((s.slice(0,a.media.start)+s.slice(a.media.end)).replaceAll('\r\n','\n')),resultHash:hash(after.replaceAll('\r\n','\n')),images:a.images.length,beforeFactsAfter:true};
  if(++done%3000===0)console.log(JSON.stringify({mediaPlacementChecked:done,audit}));
 }}));
 const targets={},sections={};for(const r of results){targets[r.target]=(targets[r.target]||0)+1;sections[r.section]=(sections[r.section]||0)+1;}
 const totals={pages:results.length,changed:results.filter(r=>r.changed).length,alreadyCorrect:results.filter(r=>!r.changed).length,targets,sections,audit};
 if(reportPath)await fs.promises.writeFile(reportPath,JSON.stringify({totals,pages:results},null,2));
 console.log(JSON.stringify({mediaPlacement:totals}));
}
