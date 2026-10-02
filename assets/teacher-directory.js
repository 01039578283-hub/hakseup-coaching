/* All profiles and branch links remain available without JavaScript. */
(()=>{'use strict';
 const controls=document.querySelector('[data-teacher-controls]');if(!controls)return;
 const query=document.getElementById('teacher-query'),region=document.getElementById('teacher-region'),focus=document.getElementById('teacher-focus');
 const cards=[...document.querySelectorAll('[data-teacher-branch]')],groups=[...document.querySelectorAll('[data-teacher-region-group]')];
 const normal=x=>x.normalize('NFC').toLocaleLowerCase('ko-KR');
 const rows=cards.map(card=>({card,text:normal(card.dataset.search),region:card.dataset.region,focus:card.dataset.focus.split('|')}));
 function filter(){const terms=normal(query.value.trim()).split(/\s+/).filter(Boolean);let branches=0,profiles=0;
  for(const row of rows){row.card.hidden=!(terms.every(term=>row.text.includes(term))&&(!region.value||row.region===region.value)&&(!focus.value||row.focus.includes(focus.value)));if(!row.card.hidden){branches++;profiles+=Number(row.card.dataset.profiles);}}
  for(const group of groups)group.hidden=![...group.querySelectorAll('[data-teacher-branch]')].some(card=>!card.hidden);
  document.getElementById('teacher-count').textContent=branches+'개 지점의 프로필 '+profiles+'건을 볼 수 있습니다.';
  document.getElementById('teacher-empty').hidden=branches>0;
 }
 query.addEventListener('input',filter);region.addEventListener('change',filter);focus.addEventListener('change',filter);
 document.getElementById('teacher-reset').addEventListener('click',()=>{query.value='';region.value='';focus.value='';filter();query.focus();});
 controls.hidden=false;
})();
