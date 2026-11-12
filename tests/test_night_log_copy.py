"""Exercise the shipped offline log script, including clipboard restrictions."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from spectypus.reporting.html import ASSETS


@pytest.mark.parametrize('mode', ['clipboard', 'fallback', 'manual'])
def test_copy_current_reviewer_text(mode):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to exercise the shipped JavaScript')
    script = r'''
const fs = require('fs'), vm = require('vm');
const mode = process.argv[1];
let copied = null;
const elements = {};
function element(id) {
  return elements[id] ||= {handlers:{}, hidden:true, value:'', textContent:'',
    addEventListener(event, fn) { this.handlers[event] = fn; },
    focus() {}, select() { this.selected = true; }};
}
const baseline = {identity:'report', records:[{campaign:0, source:{spectrum_id:'a',object_id:'AT2026agwm'}}]};
element('#night-log-data').textContent = JSON.stringify(baseline);
const inputs = ['Name','Type','z','Phase','Survey'].map((field, index) => ({
  ...element(field), dataset:{key:'c0:a',field}, value:['AT2026agwm','old type','0.019','-9.3 d','ATLAS'][index]}));
const context = {console, setTimeout, localStorage:{getItem:()=>null,setItem(){}},
  navigator:{clipboard:{writeText:async text => {
    if (mode !== 'clipboard') throw Error('blocked'); copied = text;
  }}},
  document:{querySelector:element, querySelectorAll:()=>inputs,
    execCommand(command) {
      if (command !== 'copy') throw Error('unexpected command');
      if (mode === 'manual') return false;
      copied = element('#night-log-copy-text').value; return true;
    }}};
vm.runInNewContext(fs.readFileSync(process.argv[2], 'utf8'), context);
// Reviewer changes must win over the automatic draft, including edited name.
inputs[0].value = '2026agwm'; inputs[1].value = 'SNIa-03fg or SNIa';
inputs[3].value = '-7 to -4 days';
(async () => {
  await element('#copy-night-log').handlers.click();
  console.log(JSON.stringify({copied, fallback:element('#night-log-copy-text'),
    status:element('#night-log-status').textContent, baseline}));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', script, mode, str(ASSETS / 'night-log.js')],
                            check=True, capture_output=True, text=True)
    value = json.loads(result.stdout)
    text = value['copied'] if mode != 'manual' else value['fallback']['value']
    assert text.splitlines()[0].split() == ['Name', 'Type', 'z', 'Phase', 'Survey']
    assert 'SNIa-03fg or SNIa' in text and '-7 to -4 days' in text
    assert 'old type' not in text and 'AT2026agwm' not in text
    assert value['baseline']['records'][0]['source']['object_id'] == 'AT2026agwm'
    assert value['fallback']['hidden'] == (mode != 'manual')
    if mode == 'manual':
        assert value['fallback']['selected'] and 'Command+C' in value['status']
    else:
        assert value['status'] == 'Log copied as text'
