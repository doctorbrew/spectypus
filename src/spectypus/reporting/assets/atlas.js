(() => {
  const dialog = document.querySelector('dialog');
  let trigger;
  document.querySelectorAll('.enlarge').forEach(button => button.addEventListener('click', () => {
    trigger = button;
    const image = button.querySelector('img');
    dialog.querySelector('img').src = image.src;
    dialog.querySelector('img').alt = image.alt;
    dialog.querySelector('p').textContent = image.alt;
    dialog.classList.remove('zoomed');
    dialog.querySelector('.zoom').textContent = 'Zoom to full resolution';
    dialog.querySelector('.zoom').setAttribute('aria-pressed', 'false');
    dialog.showModal();
    dialog.querySelector('.close').focus();
  }));
  dialog.querySelector('.close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.zoom').addEventListener('click', event => {
    const zoomed = dialog.classList.toggle('zoomed');
    event.currentTarget.textContent = zoomed ? 'Fit figure to width' : 'Zoom to full resolution';
    event.currentTarget.setAttribute('aria-pressed', String(zoomed));
  });
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { if (trigger) trigger.focus(); });
  const search = document.querySelector('#search');
  if (!search) return;
  const campaign = document.querySelector('#campaign');
  const issues = document.querySelector('#issues-only');
  const rows = [...document.querySelectorAll('#objects tbody tr')];
  function filter() {
    const query = search.value.trim().toLowerCase();
    rows.forEach(row => { row.hidden = !(row.dataset.search.includes(query) && (!campaign.value || row.dataset.campaign === campaign.value) && (!issues.checked || row.dataset.unresolved === 'true')); });
    document.querySelector('#visible-count').textContent = `${rows.filter(row => !row.hidden).length} of ${rows.length} campaign/object records shown`;
  }
  [search, campaign, issues].forEach(control => control.addEventListener('input', filter));
  filter();
})();
