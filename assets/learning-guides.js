/* Progressive enhancement. All guide text and blank downloads work without JS. */
(()=>{
 'use strict';
 const controls=document.querySelector('[data-guide-controls]');
 if(controls){
  const input=document.getElementById('guide-query');
  const audience=document.getElementById('guide-audience');
  const cards=[...document.querySelectorAll('[data-guide-card]')];
  const groups=[...document.querySelectorAll('[data-guide-category]')];
  const buttons=[...controls.querySelectorAll('[data-category]')];
  const normalize=s=>s.normalize('NFC').toLocaleLowerCase('ko-KR');
  const rows=cards.map(card=>({card,text:normalize(card.textContent),categories:card.dataset.category.split(' '),ages:card.dataset.ages.split(' ')}));
  let category='';
  function filter(){
   const terms=normalize(input.value.trim()).split(/\s+/).filter(Boolean);
   let count=0;
   for(const row of rows){
    row.card.hidden=!(terms.every(term=>row.text.includes(term))&&(!category||row.categories.includes(category))&&(!audience.value||row.ages.includes(audience.value)));
    if(!row.card.hidden)count++;
   }
   for(const group of groups){
    const visible=[...group.querySelectorAll('[data-guide-card]')].filter(card=>!card.hidden).length;
    group.hidden=visible===0;
    group.querySelector('h3 span').textContent=visible+'개';
   }
   document.getElementById('guide-count').textContent=count+'개 가이드를 볼 수 있습니다.';
   document.getElementById('guide-empty').hidden=count>0;
   for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.category===category));
  }
  input.addEventListener('input',filter);audience.addEventListener('change',filter);
  for(const button of buttons)button.addEventListener('click',()=>{category=button.dataset.category;filter();});
  document.getElementById('guide-reset').addEventListener('click',()=>{input.value='';audience.value='';category='';filter();input.focus();});
  controls.hidden=false;
 }
 function download(text,name){
  const objectUrl=URL.createObjectURL(new Blob(['\ufeff',text],{type:'text/plain;charset=utf-8'}));
  const link=document.createElement('a');link.href=objectUrl;link.download=name;link.hidden=true;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
 }
 for(const form of document.querySelectorAll('[data-guide-record]')){
  const save=form.querySelector('[data-save-record]');
  const print=form.querySelector('[data-print-record]');
  const status=form.querySelector('[data-record-status]');
  form.addEventListener('submit',event=>event.preventDefault());
  save.hidden=false;print.hidden=false;
  save.addEventListener('click',()=>{
   const fields=[...form.querySelectorAll('textarea')];
   if(!fields.some(field=>field.value.trim())){status.textContent='기록을 입력한 뒤 내려받으세요. 빈 양식은 별도 버튼으로 내려받을 수 있습니다.';fields[0].focus();return;}
   const text=form.dataset.title+'\r\n'+form.dataset.url+'\r\n\r\n'+fields.map(field=>field.labels[0].childNodes[0].textContent.trim()+'\r\n'+(field.value.trim()||'(미작성)')+'\r\n').join('\r\n');
   download(text,'학습기록-'+new Date().toISOString().slice(0,10)+'.txt');
   status.textContent='TXT 내려받기를 요청했습니다. 저장된 파일에서 기록을 확인하세요.';
  });
  print.addEventListener('click',()=>{
   const section=form.closest('section');section.dataset.printTitle=form.dataset.title;
   const values=[...form.querySelectorAll('textarea')].map(field=>{
    const value=document.createElement('p');value.className='lg-print-value';
    value.textContent=field.value.trim()||field.placeholder;field.after(value);return value;
   });
   document.body.classList.add('lg-print-record');
   try{window.print();}finally{document.body.classList.remove('lg-print-record');for(const value of values)value.remove();}
  });
  form.addEventListener('reset',()=>{status.textContent='입력란을 비웠습니다. 내려받은 파일은 그대로 남습니다.';});
 }
})();
