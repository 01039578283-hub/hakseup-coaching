(() => {
  const input=document.getElementById('subject-local-search');
  if(!input)return;
  input.setAttribute('aria-label','지역명 검색');
  const reset=document.getElementById('subject-search-reset');
  const status=document.getElementById('subject-search-status');
  const cards=[...document.querySelectorAll('[data-local-name]')];
  const cities=[...document.querySelectorAll('[data-city-group]')];
  const regions=[...document.querySelectorAll('[data-region-group]')];
  const update=()=>{
    const words=input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    let count=0;
    cards.forEach(card=>{
      const matched=words.every(word=>card.dataset.search.toLowerCase().includes(word));
      card.hidden=!matched;if(matched)count++;
    });
    cities.forEach(city=>{city.hidden=![...city.querySelectorAll('[data-local-name]')].some(card=>!card.hidden);});
    regions.forEach(region=>{
      region.hidden=![...region.querySelectorAll('[data-local-name]')].some(card=>!card.hidden);
      if(words.length&&!region.hidden)region.open=true;
    });
    reset.hidden=!words.length;
    status.textContent=words.length?(count?`${count}개 지역을 찾았습니다.`:'일치하는 동네가 없습니다. 지역명이나 동네명을 바꿔 검색해 보세요.') : '';
  };
  input.addEventListener('input',update);
  reset.addEventListener('click',()=>{input.value='';update();input.focus();});
  document.querySelectorAll('.directory-area-shortcuts a').forEach(link=>{
    link.addEventListener('click',()=>{
      input.value='';update();
      const target=document.getElementById(link.hash.slice(1));if(target)target.open=true;
    });
  });
})();
