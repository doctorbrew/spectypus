#!/usr/bin/env python3
"""Bounded read-only native loaders: no classifier arithmetic or output writers.

Run in the configured interpreter; output must be a new directory. NGSF aborts
at entry to its first core call, after native loading and before any fit.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine',choices=['snid_sage','ngsf'],required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    settings=json.loads(args.config.read_text())['engines'][args.engine]
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    timings=[]
    digest=hashlib.sha256()
    def arrays(name, values):
        digest.update(name.encode())
        for value in values:
            if value is not None:
                digest.update(str(value.shape).encode())
                digest.update(str(value.dtype).encode())
                digest.update(value.tobytes())
    if args.engine=='snid_sage':
        from snid_sage.snid.core.integration import load_templates_unified
        from snid_sage.snid.template_fft_storage import TemplateFFTStorage
        imports=time.perf_counter()-start
        original=TemplateFFTStorage._load_templates_from_single_file
        lock=threading.Lock()
        def measured(self, filename, *pos, **kw):
            profile=cProfile.Profile(); begin=time.perf_counter()
            try:
                return profile.runcall(original,self,filename,*pos,**kw)
            finally:
                elapsed=time.perf_counter()-begin
                profile.dump_stats(str(output/('worker-'+hashlib.sha256(str(filename).encode()).hexdigest()[:16]+'.prof')))
                with lock:
                    timings.append({'file':str(filename),'seconds':elapsed})
        TemplateFFTStorage._load_templates_from_single_file=measured
        profile=cProfile.Profile();start=time.perf_counter()
        templates=profile.runcall(load_templates_unified,settings['templates'],profile_id='optical')
        elapsed=time.perf_counter()-start
        for row in sorted(templates,key=lambda r:r['name']):
            arrays(row['name'],[row.get(k) for k in ('wave','flux','pre_computed_fft')])
        count=len(templates);galaxies=0
    else:
        root=Path(settings['root']).resolve()
        parameters=json.loads(Path(settings['parameters']).read_text())
        parameters.update(lower_lam=3800,upper_lam=9000,resolution=10,
                          mask_galaxy_lines=0,show_plot=0,
                          saving_results_path=str(output)+'/',object_to_fit='unused-no-spectrum')
        # Native params module reads argv; this is an isolated profiling process.
        sys.argv=['profile_loading',json.dumps(parameters)]
        sys.path.insert(0,str(root));os.chdir(root)
        import math
        import numpy as np
        np.math = math  # Same isolated compatibility alias as the production bridge.
        import NGSF.SF_functions as functions
        imports=time.perf_counter()-start
        class Loaded(BaseException): pass
        captured={}
        def stop_before_fit(*pos,**kw):
            captured.update(sn=pos[4],gal=pos[6],extinction=pos[7])
            raise Loaded()
        functions.core=stop_before_fit
        p=functions.parameters
        profile=cProfile.Profile();start=time.perf_counter()
        try:
            profile.runcall(functions.all_parameter_space,None,[0.0],[0.0],
                p.templates_sn_trunc,p.templates_gal_trunc,p.lam,10,p.iterations,save=str(output/'never-written'))
        except Loaded:
            pass
        else:
            raise RuntimeError('Native loading failed to reach the guarded fit boundary')
        elapsed=time.perf_counter()-start
        for key in ('sn','gal','extinction'):
            for name,value in sorted(captured[key].items()):
                arrays(key+':'+name,[value])
        count=len(captured['sn']);galaxies=len(captured['gal'])
    profile.dump_stats(str(output/'main.prof'))
    result={'engine':args.engine,'imports_seconds':imports,'loading_seconds':elapsed,
            'templates':count,'galaxies':galaxies,'arrays_sha256':digest.hexdigest(),
            'worker_times':sorted(timings,key=lambda r:r['file']),
            'peak_rss_native':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'rss_unit':'bytes' if sys.platform=='darwin' else 'KiB',
            'classifier_calls':0,'scope':'loading only; profiling overhead included; OS caches uncontrolled'}
    (output/'result.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
