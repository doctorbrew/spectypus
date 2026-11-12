(() => {
  const search = document.querySelector('#atlas-search');
  if (!search) return;
  search.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    document.querySelectorAll('[data-atlas-name]').forEach(item => {
      item.hidden = !item.dataset.atlasName.includes(query);
    });
  });
  function reveal() {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!target) return;
    for (let node = target; node; node = node.parentElement) {
      if (node.tagName === 'DETAILS') node.open = true;
    }
    target.scrollIntoView();
  }
  window.addEventListener('hashchange', reveal);
  reveal();
})();
