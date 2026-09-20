/* All center links are server-rendered; filtering never changes URLs or content. */
(() => {
  'use strict';
  const form = document.querySelector('[data-branch-search]');
  if (form) {
    const input = form.querySelector('input');
    const status = form.querySelector('[data-search-status]');
    const empty = document.querySelector('[data-search-empty]');
    const cards = [...document.querySelectorAll('[data-center-keywords]')];
    const groups = [...document.querySelectorAll('[data-region-group]')];
    const normalize = text => text.normalize('NFC').toLowerCase().replace(/\s+/g, '');
    const entries = cards.map(card => [card, normalize(card.dataset.centerKeywords)]);
    const filter = () => {
      const query = normalize(input.value);
      let count = 0;
      for (const [card, keywords] of entries) {
        card.hidden = Boolean(query) && !keywords.includes(query);
        if (!card.hidden) count++;
      }
      for (const group of groups) {
        group.hidden = ![...group.querySelectorAll('[data-center-keywords]')].some(card => !card.hidden);
      }
      status.textContent = query ? `검색 결과 ${count}개 지점` : `전체 ${count}개 지점`;
      empty.hidden = count !== 0;
    };
    form.addEventListener('submit', event => { event.preventDefault(); filter(); });
    input.addEventListener('input', filter);
    form.addEventListener('reset', () => { input.value = ''; filter(); input.focus(); });
    filter();
  }
  const menu = document.querySelector('.hc-mobile-menu');
  if (menu) {
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
    });
    menu.addEventListener('click', event => { if (event.target.closest('a')) menu.open = false; });
  }
})();
