/** Run the static release stages in order without shell command-length limits. */
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const here=path.dirname(fileURLToPath(import.meta.url));
export const steps=[
 ['favicon-build.mjs'],
 ['search-quality-build.mjs'],
 ['kakaomap-build.mjs'],
 ['media-placement-build.mjs'],
 ['seo-geo-build.mjs','--report=.seo-geo-report.json'],
 ['local-content-build.mjs','--report=.local-content-report.json'],
 ['content-refinement-build.mjs','--report=.content-refinement-report.json'],
 ['page-roles-build.mjs','--report=.page-roles-report.json'],
 ['learning-levels-build.mjs','--report=.learning-levels-report.json']
];
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 for(const step of steps){
  const result=spawnSync(process.execPath,step,{cwd:here,stdio:'inherit'});
  if(result.error)throw result.error;
  if(result.signal)throw Error('Release stage interrupted: '+step[0]);
  if(result.status!==0){process.exitCode=result.status||1;break}
 }
}
