/* Offline JPG export: copy verified master pixels without rescaling or refitting. */
(() => {
  const receiptName = 'classification-plot-selections.json';
  let urls = [];
  async function sha(bytes) {
    const hash = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function jpeg300(bytes) {
    // Canvas encodes 96 dpi by default. Preserve pixels and set JFIF density.
    if (bytes[0] !== 255 || bytes[1] !== 216) throw Error('Browser did not produce a JPEG');
    for (let offset = 2; offset + 18 <= bytes.length;) {
      if (bytes[offset] !== 255 || bytes[offset+1] === 218) break;
      const size = bytes[offset+2]*256 + bytes[offset+3];
      if (size < 2 || offset+2+size > bytes.length) break;
      if (bytes[offset+1] === 224 && String.fromCharCode(...bytes.slice(offset+4, offset+9)) === 'JFIF\0') {
        bytes[offset+11] = 1;
        bytes.set([1,44,1,44], offset+12);
        return bytes;
      }
      offset += size+2;
    }
    const jfif = Uint8Array.from([255,224,0,16,74,70,73,70,0,1,2,1,1,44,1,44,0,0]);
    const result = new Uint8Array(bytes.length+jfif.length);
    result.set(bytes.slice(0,2)); result.set(jfif,2); result.set(bytes.slice(2),2+jfif.length);
    return result;
  }
  function choices(log, baseline) {
    if (log.report_identity !== baseline.identity || log.schema !== 'spectypus-night-log/1') throw Error('Wrong report selection');
    const found = [], names = new Set();
    for (const row of log.rows) {
      const record = baseline.records.find(r => `c${r.campaign}:${r.source.spectrum_id}` === row.key);
      if (!record) throw Error('Unknown spectrum selection');
      for (const [engine, choice] of Object.entries(row.plot_selections || {})) {
        const run = record.runs.find(r => r.engine === engine && r.execution_id === choice.execution_id);
        const map = run?.figure?.browser_export;
        const panel = map?.panels?.find(p => p.rank === choice.rank);
        const candidate = run?.matches.find(m => m.rank === choice.rank);
        const filename = baseline.plot_names?.[row.key]?.[engine];
        if (!Number.isInteger(choice.rank) || choice.rank < 1 || choice.rank > 6 ||
            map?.status !== 'ready' || map.schema !== 'spectypus-panel-map/1' || map.dpi !== 300 || !panel || !candidate)
          throw Error('This match has no offline export layout; refresh the HTML with Spectypus');
        if (!filename || !/^PLOT_Classification_[A-Za-z0-9_.-]+\.jpg$/.test(filename) || names.has(filename.toLowerCase()))
          throw Error('Invalid or duplicate plot filename');
        names.add(filename.toLowerCase());
        found.push({run, map, panel, entry:{filename, key:row.key, engine, rank:choice.rank,
          execution_id:run.execution_id, mode:run.mode, spectrum_id:record.source.spectrum_id,
          object_id:record.source.object_id, candidate, record_sha256:run.record_sha256,
          source_jpg_sha256:map.jpg_sha256, report_identity:baseline.identity,
          export_method:'embedded-master-pixels', dpi:300}});
      }
    }
    if (!found.length) throw Error('Choose at least one match');
    return found;
  }
  async function render(item) {
    const source = document.getElementById('master-'+item.run.execution_id)?.getAttribute('src');
    if (!source?.startsWith('data:image/jpeg;base64,')) throw Error('Embedded master JPG is missing');
    const bytes = Uint8Array.from(atob(source.split(',')[1]), ch => ch.charCodeAt(0));
    if (await sha(bytes) !== item.map.jpg_sha256) throw Error('Embedded master JPG failed verification');
    const image = new Image(); image.src = source; await image.decode();
    if (image.naturalWidth !== item.map.width || image.naturalHeight !== item.map.height)
      throw Error('Master JPG dimensions changed');
    const canvas = document.createElement('canvas'), panel = item.panel;
    if (![panel.width,panel.height].every(n=>Number.isInteger(n) && n>0 && n<=20000)) throw Error('Invalid export dimensions');
    canvas.width=panel.width; canvas.height=panel.height;
    const context=canvas.getContext('2d');
    context.fillStyle='white'; context.fillRect(0,0,canvas.width,canvas.height);
    context.imageSmoothingEnabled=false;
    for (const part of panel.pieces) {
      const [x,y,w,h]=part.source, [dx,dy]=part.at;
      if (![x,y,w,h,dx,dy].every(Number.isInteger) || x<0 || y<0 || w<=0 || h<=0 ||
          x+w>image.naturalWidth || y+h>image.naturalHeight || dx<0 || dy<0 || dx+w>canvas.width || dy+h>canvas.height)
        throw Error('Invalid panel crop coordinates');
      context.drawImage(image,x,y,w,h,dx,dy,w,h);
    }
    const encoded=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.97));
    if (!encoded) throw Error('Browser could not export a JPG');
    const data=jpeg300(new Uint8Array(await encoded.arrayBuffer()));
    const blob=new Blob([data],{type:'image/jpeg'}), url=URL.createObjectURL(blob);
    urls.push(url);
    return {blob,url,entry:{...item.entry,sha256:await sha(data)}};
  }
  async function readFile(folder,name) {
    try {return await (await folder.getFileHandle(name)).getFile();}
    catch(error) {if(error.name==='NotFoundError') return null; throw error;}
  }
  async function writeFile(folder,name,blob) {
    const file=await folder.getFileHandle(name,{create:true});
    const writer=await file.createWritable();
    try {await writer.write(blob); await writer.close();}
    catch(error) {try {await writer.abort();} catch {} throw error;}
  }
  async function make(log,baseline) {
    const selected=choices(log,baseline);
    let folder=null;
    // Request access directly in the click gesture, before asynchronous rendering.
    if (window.showDirectoryPicker) {
      try {folder=await window.showDirectoryPicker({id:'spectypus-classification-plots',mode:'readwrite'});}
      catch(error) {if(!['SecurityError','NotAllowedError'].includes(error.name)) throw error;}
    }
    let managed={};
    if(folder) {
      const html=await readFile(folder,'index.html');
      const match=html && (await html.text()).match(/<script type="application\/json" id="night-log-data">([\s\S]*?)<\/script>/);
      if(!match || JSON.parse(match[1]).identity!==baseline.identity)
        throw Error('Choose the folder containing this report’s index.html');
      const prior=await readFile(folder,receiptName);
      if(prior) {
        const receipt=JSON.parse(await prior.text());
        if(receipt.schema!=='spectypus-selected-plots/1' || !Array.isArray(receipt.files)) throw Error('Unrecognized plot-selection record');
        managed=Object.fromEntries(receipt.files.map(file=>[file.filename,file]));
      }
      for(const item of selected) {
        const filename=item.entry.filename, existing=await readFile(folder,filename);
        if(existing && (!managed[filename] || await sha(await existing.arrayBuffer())!==managed[filename].sha256))
          throw Error('Keeping an unrecognized or edited file: '+filename);
      }
    }
    urls.forEach(url=>URL.revokeObjectURL(url)); urls=[];
    const prepared=[];
    for(const item of selected) prepared.push(await render(item));
    let saved=0;
    if(folder) {
      try {
        for(const file of prepared) {
          await writeFile(folder,file.entry.filename,file.blob); saved++;
          managed[file.entry.filename]=file.entry;
          await writeFile(folder,receiptName,JSON.stringify({schema:'spectypus-selected-plots/1',files:Object.values(managed)},null,2));
        }
      } catch(error) {throw Error(`Saved ${saved} of ${prepared.length} JPGs; ${error.message}`);}
    } else {
      for(const file of prepared) {
        const a=document.createElement('a'); a.href=file.url; a.download=file.entry.filename;
        document.body.appendChild(a); a.click(); a.remove();
      }
    }
    return {saved:!!folder, folder:folder?.name,
            files:prepared.map(file=>({filename:file.entry.filename,url:file.url}))};
  }
  window.SpectypusPlots={make};
})();
