"""Run the shipped reviewer controls without a browser or native classifiers."""
import json
import shutil
import subprocess

import pytest

from spectypus.reporting.html import ASSETS


@pytest.mark.parametrize('mode', ['folder', 'download', 'failure', 'cancel'])
def test_selection_save_load_and_make_plots(mode):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to exercise the shipped JavaScript')
    script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const mode = process.argv[1], elements = {};
function element(id) {
  return elements[id] ||= {handlers:{}, value:'', textContent:'', children:[],
    addEventListener(event, fn) {this.handlers[event] = fn;},
    replaceChildren() {this.children = [];}, appendChild(child) {this.children.push(child);}};
}
const baseline = {identity:'report',
  records:[{campaign:0,source:{spectrum_id:'a',object_id:'SN-A'}}]};
element('#night-log-data').textContent = JSON.stringify(baseline);
const inputs = ['Name','Type','z','Phase','Survey'].map((field, i) => ({
  ...element(field), dataset:{key:'c0:a',field}, value:['SN-A','Ia','0.02','+2d','ATLAS'][i]}));
const selects = ['snid_sage','ngsf'].map(engine => ({...element(engine),
  dataset:{key:'c0:a',engine}, options:['','fixed:1','free:2'].map(value=>({value}))}));
let saved = '', cached = '', posted = null;
const context = {console, setTimeout, localStorage:{getItem:()=>null,setItem(key,value){cached=value;}},
  window:{showSaveFilePicker:async()=>({createWritable:async()=>({write:async text=>{saved=text;},close:async()=>{}})}),
    SpectypusPlots:{make:async(log,data)=>{
      posted=log; assert.equal(data.identity,'report');
      if(mode==='failure') throw Error('Changed evidence');
      if(mode==='cancel') {const error=Error('cancelled'); error.name='AbortError'; throw error;}
      return {saved:mode==='folder',folder:'2026-10-28',files:[
        {filename:'PLOT_Classification_SNID-SAGE_SN-A.jpg',url:'blob:snid'},
        {filename:'PLOT_Classification_NGSF_SN-A.jpg',url:'blob:ngsf'}]};
    }}},
  document:{querySelector:element,
    querySelectorAll:selector=>selector.includes('select[')?selects:inputs,
    createElement:()=>({})},
  fetch:()=>{throw Error('No server or network requests allowed');}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
async function load(log) {
  await element('#load-night-log').handlers.change({target:{files:[{text:async()=>JSON.stringify(log)}]}});
}
(async()=>{
  selects[0].value='free:2'; selects[1].value='fixed:1'; inputs[1].value='reviewed';
  await element('#save-night-log').handlers.click();
  const log=JSON.parse(saved);
  assert.deepEqual(log.rows[0].plot_selections,{snid_sage:{execution_id:'free',rank:2},ngsf:{execution_id:'fixed',rank:1}});
  selects[0].value=''; selects[1].value=''; inputs[1].value='other';
  await load(log);
  assert.equal(selects[0].value,'free:2'); assert.equal(selects[1].value,'fixed:1'); assert.equal(inputs[1].value,'reviewed');
  const invalid=JSON.parse(saved); invalid.rows[0].Type='should not apply'; invalid.rows[0].plot_selections.ngsf.rank=6;
  await load(invalid);
  assert.match(element('#night-log-status').textContent,/Log not loaded/);
  assert.equal(inputs[1].value,'reviewed'); assert.equal(selects[1].value,'fixed:1');
  const button=element('#make-night-plots');
  await button.handlers.click({currentTarget:button});
  const result={posted,status:element('#night-log-status').textContent,
    files:element('#night-plot-results').children,disabled:button.disabled,cached:JSON.parse(cached)};
  const old=JSON.parse(saved); delete old.rows[0].plot_selections;
  await load(old); assert.equal(selects[0].value,''); assert.equal(selects[1].value,'');
  await button.handlers.click({currentTarget:button});
  assert.match(element('#night-log-status').textContent,/Choose a configuration and rank/);
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    run = subprocess.run([node, '-e', script, mode, str(ASSETS / 'night-log.js')],
                         check=True, capture_output=True, text=True)
    result = json.loads(run.stdout)
    assert result['cached']['rows'][0]['plot_selections']['snid_sage']['rank'] == 2
    assert not result['disabled']
    assert result['posted']['rows'][0]['plot_selections']['ngsf'] == {'execution_id': 'fixed', 'rank': 1}
    if mode == 'failure':
        assert result['status'] == 'Changed evidence' and not result['files']
    elif mode == 'cancel':
        assert result['status'] == 'Save cancelled · selections retained' and not result['files']
    else:
        assert result['status'] == ('Saved 2 JPGs in 2026-10-28' if mode == 'folder'
                                    else 'Prepared 2 JPG downloads · save them beside index.html')
        assert result['files'][0]['href'] == 'blob:snid'
        assert result['files'][0]['download'] == 'PLOT_Classification_SNID-SAGE_SN-A.jpg'
