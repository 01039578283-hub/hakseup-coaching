/** Keep concise head descriptions and the current-page JSON-LD in agreement.
 * Does not change Article.abstract, visible content, URLs, dates or services.
 */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const decode=(s)=>s.replace(/&(?:amp|quot|apos|lt|gt|#39);/g,m=>({'&amp;':'&','&quot;':'"','&apos;':"'",'&#39;':"'",'&lt;':'<','&gt;':'>'}[m]));
const attr=(tag,name)=>decode(tag.match(new RegExp('\\b'+name+'\\s*=\\s*(["\'])([\\s\\S]*?)\\1','i'))?.[2]||'');
export function transform(html){
  let changedNodes=0;
  const next=html.replace(/<head\b[^>]*>[\s\S]*?<\/head>/i,head=>{
    const meta=[...head.matchAll(/<meta\b[^>]*>/gi)].map(m=>m[0]);
    if(meta.some(m=>attr(m,'name')==='robots'&&/noindex/i.test(attr(m,'content'))))return head;
    const description=attr(meta.find(m=>attr(m,'name')==='description')||'','content');
    const canonical=attr([...head.matchAll(/<link\b[^>]*>/gi)].map(m=>m[0]).find(m=>attr(m,'rel')==='canonical')||'','href');
    if(!description||!canonical)return head;
    const same=u=>{try{return decodeURIComponent(u).split('#')[0]===decodeURIComponent(canonical);}catch{return false;}};
    return head.replace(/(<script\b[^>]*type=["']application\/ld\+json["'][^>]*>)([\s\S]*?)(<\/script>)/gi,(all,start,body,end)=>{
      const value=JSON.parse(body);let dirty=false;
      function visit(n){
        if(!n||typeof n!=='object')return;
        if(Array.isArray(n)){n.forEach(visit);return;}
        const types=Array.isArray(n['@type'])?n['@type']:[n['@type']];
        if(types.some(t=>['WebPage','CollectionPage','Article'].includes(t)) && (same(n.url)||same(n['@id'])||same(n.mainEntityOfPage?.['@id'])) && n.description!==description){n.description=description;dirty=true;changedNodes++;}
        Object.values(n).forEach(visit);
      }
      visit(value);
      return dirty?start+JSON.stringify(value).replaceAll('</','<\\/')+end:all;
    });
  });
  return {html:next,changed:html!==next,changedNodes};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const check=process.argv.includes('--check');const errors=[];let pages=0,changed=0,nodes=0;
  const skip=new Set(['assets','tools','tmp','reports','node_modules','dist','public','outputs']);
  function walk(dir){for(const d of fs.readdirSync(dir,{withFileTypes:true})){
    if(d.name.startsWith('.'))continue;const p=path.join(dir,d.name);
    if(d.isDirectory()){if(!skip.has(d.name))walk(p);continue;}
    if(!p.endsWith('.html'))continue;
    try{const result=transform(fs.readFileSync(p,'utf8'));pages++;nodes+=result.changedNodes;if(result.changed){changed++;if(!check)fs.writeFileSync(p,result.html);}}
    catch(e){errors.push({file:p,message:e.message});}
  }}
  walk(root);console.log(JSON.stringify({pages,changed,changedNodes:nodes,check,errors}));
  if(errors.length||(check&&changed))process.exitCode=1;
}
