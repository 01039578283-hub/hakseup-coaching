(() => {
  'use strict';
  if (!('HTMLDialogElement' in window)) return;
  let dialog, originalLink;
  const close = () => dialog.close();
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-original-image]');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); originalLink = link;
    if (!dialog) {
      dialog = document.createElement('dialog'); dialog.className = 'hc-image-dialog'; dialog.setAttribute('aria-label', '안내 이미지 원본 확대');
      dialog.innerHTML = '<div class="hc-image-dialog-header"><p>원본 크기로 표시됩니다. 좌우·아래로 움직여 글씨를 확인하세요.</p><button type="button">닫기</button></div><p class="hc-image-dialog-status" role="status"></p><div class="hc-image-dialog-body" tabindex="0" role="region" aria-label="원본 이미지 스크롤 영역"></div>';
      document.body.append(dialog); dialog.querySelector('button').addEventListener('click', close);
      dialog.addEventListener('click', e => { if (e.target === dialog) close(); });
      dialog.addEventListener('close', () => { dialog.querySelector('.hc-image-dialog-body').replaceChildren(); originalLink?.focus({preventScroll:true}); });
    }
    const body = dialog.querySelector('.hc-image-dialog-body'), status = dialog.querySelector('[role="status"]');
    body.replaceChildren(); status.textContent = '원본을 불러오는 중입니다.';
    const img = new Image(); img.alt = link.dataset.imageLabel || link.querySelector('img')?.alt || '안내 이미지 원본'; img.decoding = 'async';
    img.addEventListener('load', () => { status.textContent = '원본 '+img.naturalWidth+' × '+img.naturalHeight+'픽셀'; });
    img.addEventListener('error', () => { status.textContent = '이미지를 불러오지 못했습니다. '; const retry = document.createElement('a'); retry.href = link.href; retry.textContent = '원본 주소로 보기'; status.append(retry); });
    body.append(img); dialog.showModal(); img.src = link.href;
  });
})();
