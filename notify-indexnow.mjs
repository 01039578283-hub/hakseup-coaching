/** Notify only changes after an explicitly initialized, verified production release. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const args=Object.fromEntries(process.argv.slice(2).filter(a=>a.includes('=')).map(a=>a.replace(/^--/,'').split(/=(.*)/s).slice(0,2)));
const initialize=process.argv.includes('--initialize'),notify=process.argv.includes('--notify'),dryRun=process.argv.includes('--dry-run');
if([initialize,notify,dryRun].filter(Boolean).length!==1)throw Error('Choose exactly one of --initialize, --dry-run or --notify');
const config=JSON.parse(fs.readFileSync(path.join(here,'indexnow-config.json'),'utf8'));
if(!args.report||!args.validation||!args.state)throw Error('Require --report, --validation and private --state paths');
const report=JSON.parse(fs.readFileSync(args.report,'utf8'));
const validation=JSON.parse(fs.readFileSync(args.validation,'utf8'));
const host=new URL(config.base).hostname;
if(validation.base!==config.base||validation.errors?.length||validation.count!==Object.keys(report.pageHashes).length||validation.rows.some(r=>r.status!==200||!r.matches))throw Error('Complete matching production GET validation is required');
if(!Object.keys(report.pageHashes).length)throw Error('Empty release report');
const keyResponse=await fetch(config.base+'/'+config.key+'.txt');
if(!keyResponse.ok||(await keyResponse.text()).trim()!==config.key)throw Error('Public ownership key failed verification');
const statePath=path.resolve(args.state);
if(initialize){
 if(fs.existsSync(statePath))throw Error('State already exists; do not silently reset the notification baseline');
 fs.mkdirSync(path.dirname(statePath),{recursive:true});
 fs.writeFileSync(statePath,JSON.stringify({initializedAt:new Date().toISOString(),pageHashes:report.pageHashes,urls:report.urls,notifications:[]},null,2));
 console.log(JSON.stringify({initialized:true,baselineUrls:Object.keys(report.pageHashes).length,submitted:0}));
}else{
 if(!fs.existsSync(statePath))throw Error('Initialize after the first verified release; never backfill historical URLs');
 const state=JSON.parse(fs.readFileSync(statePath,'utf8'));
 const changed=Object.keys(report.pageHashes).filter(p=>state.pageHashes[p]!==report.pageHashes[p]);
 const removed=Object.keys(state.pageHashes).filter(p=>!(p in report.pageHashes));
 const urls=[...changed.map(p=>report.urls[p]),...removed.map(p=>state.urls[p])];
 for(const u of urls)if(new URL(u).origin!==config.base)throw Error('Unexpected notification origin');
 const receipts=[];
 if(dryRun){
  console.log(JSON.stringify({dryRun:true,changed:changed.length,removed:removed.length,wouldSubmit:urls.length,submitted:0}));
 }else{
 for(let start=0;start<urls.length;start+=10000){
  const batch=urls.slice(start,start+10000);
  const response=await fetch('https://searchadvisor.naver.com/indexnow',{method:'POST',headers:{'Content-Type':'application/json; charset=utf-8'},body:JSON.stringify({host,key:config.key,keyLocation:config.base+'/'+config.key+'.txt',urlList:batch})});
  if(![200,202].includes(response.status))throw Error('Notification failed: '+response.status+'; baseline was not advanced');
  receipts.push({at:new Date().toISOString(),status:response.status,urls:batch});
 }
 fs.writeFileSync(statePath,JSON.stringify({...state,pageHashes:report.pageHashes,urls:report.urls,notifications:[...state.notifications,...receipts]},null,2));
 console.log(JSON.stringify({submitted:urls.length,receipts:receipts.map(r=>({status:r.status,count:r.urls.length})),indexingConfirmed:false}));
 }
}
