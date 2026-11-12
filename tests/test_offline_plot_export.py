"""Exercise the shipped offline compositor, file permissions and JPG contract."""
import base64
import hashlib
import io
import json
import shutil
import subprocess

import pytest

from spectypus.reporting.html import ASSETS


@pytest.mark.parametrize('mode', ['folder', 'download', 'denied', 'wrong-folder', 'edited', 'cancel', 'tampered'])
def test_offline_selected_jpgs_without_network(tmp_path, mode):
    Image = pytest.importorskip('PIL.Image')
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to exercise the shipped JavaScript')
    data = io.BytesIO()
    Image.new('RGB', (20, 20), color='white').save(data, format='JPEG', dpi=(96, 96))
    fixture = tmp_path / 'image.json'
    fixture.write_text(json.dumps({'image':base64.b64encode(data.getvalue()).decode(),
                                   'hash':hashlib.sha256(data.getvalue()).hexdigest()}))
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const mode=process.argv[1], fixture=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const bytes=Buffer.from(fixture.image,'base64'), stored=new Map(), drawn=[], downloads=[];
const names={snid_sage:'PLOT_Classification_SNID-SAGE_SN-A.jpg',ngsf:'PLOT_Classification_NGSF_SN-A.jpg'};
const map={status:'ready',schema:'spectypus-panel-map/1',dpi:300,width:20,height:20,jpg_sha256:fixture.hash,
 panels:[1,2].map(rank=>({rank,width:20,height:20,pieces:[{source:[rank,rank,5,5],at:[10,10]}]}))};
const runs=['snid_sage','ngsf'].map(engine=>({engine,execution_id:engine,mode:engine==='ngsf'?'fixed':'free',
 matches:[{rank:1,template:'SN2012dn'},{rank:2,template:'SN2007ca'}],figure:{browser_export:map}}));
const baseline={identity:'report',plot_names:{'c0:a':names},records:[{campaign:0,source:{spectrum_id:'a',object_id:'SN-A'},runs}]};
const log={schema:'spectypus-night-log/1',report_identity:'report',rows:[{key:'c0:a',plot_selections:{
 snid_sage:{execution_id:'snid_sage',rank:2},ngsf:{execution_id:'ngsf',rank:1}}}]};
stored.set('index.html',Buffer.from('<script type="application/json" id="night-log-data">'+JSON.stringify(baseline)+'</script>'));
if(mode==='wrong-folder') stored.clear();
if(mode==='edited') stored.set(names.snid_sage,Buffer.from('user-edited'));
if(mode==='tampered') map.jpg_sha256='bad';
const err=(name,message=name)=>Object.assign(Error(message),{name});
const folder={name:'night',async getFileHandle(name,opts={}) {
 if(!stored.has(name) && !opts.create) throw err('NotFoundError');
 return {getFile:async()=>({text:async()=>stored.get(name).toString(),arrayBuffer:async()=>Uint8Array.from(stored.get(name)).buffer}),
 createWritable:async()=>({write:async content=>{stored.set(name,typeof content==='string'?Buffer.from(content):Buffer.from(await content.arrayBuffer()));},close:async()=>{},abort:async()=>{}})};
}};
const document={getElementById:()=>({getAttribute:()=>`data:image/jpeg;base64,${fixture.image}`}),
 body:{appendChild(){}},createElement:type=>type==='canvas'?{getContext:()=>({fillRect(){},drawImage(...args){drawn.push(args.slice(1));}}),
 toBlob:fn=>fn(new Blob([bytes],{type:'image/jpeg'}))}:{click(){downloads.push(this.download);},remove(){}}};
const window={};
if(mode!=='download') window.showDirectoryPicker=async()=>{
 if(mode==='cancel') throw err('AbortError'); if(mode==='denied') throw err('SecurityError'); return folder;};
const context={window,document,Uint8Array,Blob,URL,atob,crypto:require('crypto').webcrypto,
 Image:class {naturalWidth=20;naturalHeight=20;async decode(){}},
 fetch:()=>{throw Error('No network allowed');}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),context);
(async()=>{
 let result,error;
 try {result=await window.SpectypusPlots.make(log,baseline);}catch(e){error={name:e.name,message:e.message};}
 const files={};for(const [name,value] of stored) if(name.endsWith('.jpg')) files[name]=value.toString('base64');
 console.log(JSON.stringify({result,error,drawn,downloads,files,
   receipt:stored.has('classification-plot-selections.json')?JSON.parse(stored.get('classification-plot-selections.json')):null}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    process = subprocess.run([node, '-e', script, mode, str(ASSETS / 'selected-plots.js'), str(fixture)],
                             check=True, capture_output=True, text=True)
    value = json.loads(process.stdout)
    if mode in {'wrong-folder', 'edited', 'cancel', 'tampered'}:
        assert value['error'] and not value.get('result') and not value['drawn']
        assert not value['downloads'] and value['receipt'] is None
        if mode == 'edited':
            assert base64.b64decode(next(iter(value['files'].values()))) == b'user-edited'
        return
    assert value['drawn'] == [[2,2,5,5,10,10,5,5], [1,1,5,5,10,10,5,5]]
    assert len(value['result']['files']) == 2
    if mode == 'folder':
        assert value['result']['saved'] and value['result']['folder'] == 'night' and not value['downloads']
        assert len(value['files']) == 2 and len(value['receipt']['files']) == 2
        for name, encoded in value['files'].items():
            jpg = base64.b64decode(encoded)
            with Image.open(io.BytesIO(jpg)) as image:
                assert image.format == 'JPEG' and image.info['dpi'] == (300, 300)
            receipt = next(f for f in value['receipt']['files'] if f['filename'] == name)
            assert receipt['sha256'] == hashlib.sha256(jpg).hexdigest()
            assert receipt['source_jpg_sha256'] == hashlib.sha256(data.getvalue()).hexdigest()
            assert receipt['rank'] == (2 if receipt['engine'] == 'snid_sage' else 1)
    else:
        assert not value['result']['saved'] and len(value['downloads']) == 2 and not value['files']
