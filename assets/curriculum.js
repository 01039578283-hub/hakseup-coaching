/** Optional finding and study records; all curriculum content is static HTML. */
(() => {
  const filters = document.querySelector('[data-cur-filters]');
  if (filters) {
    const cards = [...document.querySelectorAll('[data-cur-card]')];
    const count = document.querySelector('[data-cur-count]');
    const empty = document.querySelector('[data-cur-empty]');
    const normalize = text => text.normalize('NFKC').toLocaleLowerCase('ko-KR').replace(/\s+/g, ' ').trim();
    const apply = () => {
      const values = new FormData(filters);
      const words = normalize(String(values.get('search') || '')).split(' ').filter(Boolean);
      let visible = 0;
      for (const card of cards) {
        const match = ['stage', 'grade', 'subject'].every(key => !values.get(key) || values.get(key) === card.dataset[key]) && words.every(word => normalize(card.dataset.search).includes(word));
        card.hidden = !match;
        if (match) visible++;
      }
      count.textContent = `과목별 학습 안내 ${visible}개`;
      empty.hidden = visible !== 0;
    };
    filters.hidden = false;
    filters.addEventListener('submit', event => event.preventDefault());
    filters.addEventListener('input', apply);
    filters.addEventListener('change', apply);
    filters.addEventListener('reset', () => setTimeout(apply, 0));
    apply();
  }
  for (const form of document.querySelectorAll('[data-cur-record]')) {
    form.addEventListener('submit', event => event.preventDefault());
    const status = form.querySelector('[data-cur-status]');
    form.querySelector('[data-cur-save]').addEventListener('click', () => {
      const values = new FormData(form);
      const labels = {level:'선택한 학습 단계',unit:'이번에 확인할 단원·과제',alone:'스스로 설명하거나 해결한 것',help:'도움이 필요했던 부분',next:'다음에 다시 확인할 것'};
      const content = ['학습코칭 공부 계획', form.dataset.title, '', ...Object.entries(labels).map(([key,label]) => `${label}\n${values.get(key) || '(아직 작성하지 않음)'}\n`)].join('\r\n');
      const url = URL.createObjectURL(new Blob(['\uFEFF',content], {type:'text/plain;charset=utf-8'}));
      const anchor = document.createElement('a');
      anchor.href = url;anchor.download = form.dataset.title.replace(/\s+/g,'-')+'-공부계획.txt';
      document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = '기록 파일 저장을 시작했습니다.';
    });
    form.querySelector('[data-cur-print]').addEventListener('click', () => window.print());
    form.addEventListener('reset', () => {status.textContent='기록을 초기화했습니다.';});
  }
})();
