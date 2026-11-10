(() => {
  const search = document.querySelector('#sn-search');
  const links = [...document.querySelectorAll('.sn-list a')];
  search.value = new URLSearchParams(location.search).get('q') || '';
  function filter() {
    const query = search.value.trim().toLowerCase();
    links.forEach(link => {
      link.hidden = !link.dataset.sn.includes(query);
      const url = new URL(link.href);
      if (query) url.searchParams.set('q', search.value); else url.searchParams.delete('q');
      link.href = url.href;
    });
    document.querySelector('#sn-count').textContent = `${links.filter(link => !link.hidden).length} of ${links.length} objects`;
  }
  search.addEventListener('input', filter); filter();
  document.querySelector('[aria-current="page"]')?.scrollIntoView({block:'nearest'});
  const epochs = [...document.querySelectorAll('details.epoch')];
  document.querySelector('#expand-epochs')?.addEventListener('click', () => epochs.forEach(e => e.open = true));
  document.querySelector('#collapse-epochs')?.addEventListener('click', () => epochs.forEach(e => e.open = false));
  function openEpoch(id) {
    const epoch = document.getElementById(id);
    if (!epoch?.matches('details.epoch')) return;
    epoch.open = true; epoch.scrollIntoView({block:'start',behavior:'smooth'});
  }
  document.querySelector('#epoch-jump')?.addEventListener('change', event => {
    if (event.target.value) { history.replaceState(null, '', '#' + event.target.value); openEpoch(event.target.value); }
  });
  if (location.hash) openEpoch(decodeURIComponent(location.hash.slice(1)));
})();
