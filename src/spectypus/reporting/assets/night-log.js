(() => {
  const element = document.querySelector('#night-log-data');
  if (!element) return;
  const baseline = JSON.parse(element.textContent);
  const inputs = [...document.querySelectorAll('#night-log input[data-key]')];
  const status = document.querySelector('#night-log-status');
  const storageKey = 'spectypus-night-log:' + baseline.identity;
  const original = inputs.map(input => input.value);
  const keys = [...new Set(inputs.map(input => input.dataset.key))];
  function collect() {
    const rows = keys.map(key => {
      const record = baseline.records.find(r => `c${r.campaign}:${r.source.spectrum_id}` === key);
      const row = {key, Name: record.source.object_id};
      inputs.filter(i => i.dataset.key === key).forEach(i => row[i.dataset.field] = i.value);
      return row;
    });
    return {schema:'spectypus-night-log/1', report_identity:baseline.identity,
            saved_at:new Date().toISOString(), rows, automatic_evidence:baseline.records};
  }
  function restore(log) {
    if (log.schema !== 'spectypus-night-log/1' || log.report_identity !== baseline.identity ||
        !Array.isArray(log.rows) || log.rows.length !== keys.length ||
        new Set(log.rows.map(r => r.key)).size !== keys.length ||
        !keys.every(key => log.rows.some(r => r.key === key))) throw Error('Log belongs to different spectra or fits');
    const values = inputs.map(input => {
      const row = log.rows.find(r => r.key === input.dataset.key);
      if (typeof row[input.dataset.field] !== 'string') throw Error('Invalid log field');
      return row[input.dataset.field];
    });
    inputs.forEach((input, index) => input.value = values[index]);
  }
  function cache() {
    try { localStorage.setItem(storageKey, JSON.stringify(collect())); return true; }
    catch { return false; }
  }
  try {
    const cached = localStorage.getItem(storageKey);
    if (cached) { restore(JSON.parse(cached)); status.textContent = 'Browser draft restored · Save log to keep a file'; }
  } catch { inputs.forEach((input, index) => input.value = original[index]); }
  inputs.forEach(input => input.addEventListener('input', () => {
    status.textContent = cache() ? 'Draft saved in browser · Save log to keep a file' : 'Unsaved changes · Save log to keep a file';
  }));
  function download(text, name, type) {
    const url = URL.createObjectURL(new Blob([text], {type}));
    const link = document.createElement('a'); link.href = url; link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  document.querySelector('#save-night-log').addEventListener('click', async () => {
    const text = JSON.stringify(collect(), null, 2);
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({suggestedName:'night-log.json',
          types:[{description:'Reviewer log',accept:{'application/json':['.json']}}]});
        const writer = await handle.createWritable(); await writer.write(text); await writer.close();
        cache(); status.textContent = 'Reviewer log saved'; return;
      } catch (error) {
        if (error.name === 'AbortError') { status.textContent = 'Save cancelled · draft retained'; return; }
        if (!['SecurityError','NotAllowedError'].includes(error.name)) { status.textContent = 'Save failed: ' + error.message; return; }
      }
    }
    download(text, 'night-log.json', 'application/json'); cache(); status.textContent = 'Reviewer log download prepared';
  });
  document.querySelector('#csv-night-log').addEventListener('click', () => {
    const columns = ['Name','Type','z','Phase','Survey'];
    const cell = value => '"' + String(value).replaceAll('"','""') + '"';
    const rows = [columns, ...collect().rows.map(row => columns.map(c => row[c]))];
    download(rows.map(row => row.map(cell).join(',')).join('\r\n') + '\r\n', 'night-log.csv', 'text/csv');
  });
  document.querySelector('#copy-night-log').addEventListener('click', async () => {
    const columns = ['Name','Type','z','Phase','Survey'];
    const rows = [columns, ...collect().rows.map(row => columns.map(c => String(row[c]).replace(/\s+/g, ' ').trim()))];
    const widths = columns.map((_, i) => Math.max(...rows.map(row => row[i].length)));
    const text = rows.map(row => row.map((cell, i) => cell.padEnd(widths[i])).join('  ').trimEnd()).join('\n');
    const fallback = document.querySelector('#night-log-copy-text');
    fallback.hidden = true;
    try {
      await navigator.clipboard.writeText(text);
      status.textContent = 'Log copied as text';
    } catch {
      // Offline/file browsers may disallow the Clipboard API. Keep the exact
      // current edits available for ordinary keyboard copy if both APIs fail.
      fallback.value = text; fallback.hidden = false; fallback.focus(); fallback.select();
      let copied = false;
      try { copied = document.execCommand('copy'); } catch {}
      fallback.hidden = copied;
      if (copied) document.querySelector('#copy-night-log').focus();
      status.textContent = copied ? 'Log copied as text' : 'Text selected below · press Command+C or Ctrl+C to copy';
    }
  });
  document.querySelector('#load-night-log').addEventListener('change', async event => {
    if (!event.target.files.length) return;
    try { restore(JSON.parse(await event.target.files[0].text())); cache(); status.textContent = 'Reviewer log loaded'; }
    catch (error) { status.textContent = 'Log not loaded: ' + error.message; }
    event.target.value = '';
  });
})();
