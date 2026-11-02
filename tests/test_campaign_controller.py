import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

from spectypus.io import read_json
from spectypus.pipeline import output_lock, make_plan, save_plan, current_record


@pytest.fixture(autouse=True)
def available_disk_space(monkeypatch):
    """Keep controller tests independent of host capacity; guard tests override."""
    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))


def controller():
    path = Path(__file__).resolve().parents[1] / "scripts/run_saved_campaign.py"
    spec = importlib.util.spec_from_file_location("campaign_controller", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_controller_stops_repeated_failures_preserves_remaining_queue(
        tmp_path, source_factory, manifest_factory, config_factory, fake_engine, monkeypatch):
    rows = [source_factory(f"s{i}", z=".1", flux=i+1) for i in range(7)]
    manifest_factory(rows).rename(tmp_path / "spectra.csv")
    config_factory()
    fake_engine.write_text("raise SystemExit(2)\n")
    monkeypatch.setattr(sys, "argv", ["controller", str(tmp_path)])
    handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with pytest.raises(RuntimeError, match="six consecutive"):
            controller().main()
    finally:
        for s, handler in handlers.items():
            signal.signal(s, handler)
    status = read_json(tmp_path / "campaign_status.json")
    assert status["status"] == "stopped"
    assert status["completed_this_invocation"] == 6
    assert status["runs"] == {"failed": 6, "pending": 1}


def test_second_controller_does_not_overwrite_active_status(tmp_path, monkeypatch):
    status = tmp_path / "campaign_status.json"
    status.write_text('{"status":"running","pid":1234}')
    monkeypatch.setattr(sys, "argv", ["controller", str(tmp_path)])
    handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        with output_lock(tmp_path / "run"), pytest.raises(ValueError, match="another writer"):
            controller().main()
    finally:
        for s, handler in handlers.items():
            signal.signal(s, handler)
    assert read_json(status) == {"status": "running", "pid": 1234}


@pytest.fixture
def parallel_controller(fake_engine, monkeypatch):
    """Real worker/engine processes, with only the external classifier faked."""
    module = controller()
    script = Path(module.__file__).resolve()
    source = script.parent.parent / "src"

    def start(run, plan, output, launch_dir):
        setup = (
            "import importlib.util,sys\n"
            "from pathlib import Path\n"
            "from spectypus.adapters import engines\n"
            "engines.fingerprint=lambda name,cfg: {'source_sha256':'fake-v1','bank_sha256':'bank-v1'}\n"
            "def build(run,config,directory):\n"
            " result=directory/'candidates.json'\n"
            f" return [sys.executable,{str(fake_engine)!r},str(result),run['spectrum_id']],directory,result\n"
            "engines.build_command=build\n"
            f"spec=importlib.util.spec_from_file_location('controller',{str(script)!r})\n"
            "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
            f"sys.argv=['controller',{str(output.parent)!r},'--worker-run',{run['execution_id']!r}]\n"
            "module.main()\n"
        )
        with (launch_dir / f"{run['execution_id']}.log").open('w') as log:
            return subprocess.Popen([sys.executable, '-c', setup],
                env={**os.environ, 'PYTHONPATH': str(source)},
                stdout=log, stderr=log, start_new_session=True)

    monkeypatch.setattr(module, "start_worker", start)
    return module


def invoke(module, monkeypatch, root, *args):
    monkeypatch.setattr(sys, 'argv', ['controller', str(root), *args])
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        module.main()
    finally:
        for s, handler in handlers.items():
            signal.signal(s, handler)


def test_parallel_results_equal_serial_and_resume_without_repeats(
        tmp_path, source_factory, manifest_factory, config_factory,
        fake_engine, parallel_controller, monkeypatch):
    root = tmp_path / 'parallel'
    root.mkdir()
    manifest = manifest_factory([source_factory(f's{i}', z='.1', flux=i+1) for i in range(4)])
    config = config_factory()
    shutil.copy2(manifest, tmp_path / 'spectra.csv')
    shutil.copy2(manifest, root / 'spectra.csv')
    shutil.copy2(config, root / 'config.json')
    invoke(controller(), monkeypatch, tmp_path)
    summaries = []
    summarize = parallel_controller._summarize
    monkeypatch.setattr(parallel_controller, '_summarize',
                        lambda *a: (summaries.append(True), summarize(*a))[1])
    invoke(parallel_controller, monkeypatch, root, '--workers', '2')
    plan = read_json(root / 'run/plan.json')
    for run in plan['runs']:
        serial = current_record(tmp_path / 'run', run)
        parallel = current_record(root / 'run', run)
        assert serial['status'] == parallel['status'] == 'completed'
        assert serial['candidates'] == parallel['candidates']
    assert len(summaries) == 2  # startup and exit, rather than every fit
    before = sorted((root / 'run/attempts').glob('*/*/record.json'))
    invoke(parallel_controller, monkeypatch, root, '--workers', '2')
    assert before == sorted((root / 'run/attempts').glob('*/*/record.json'))
    assert read_json(root / 'campaign_status.json')['completed_this_invocation'] == 0


def test_parallel_bound_and_max_runs(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, parallel_controller, monkeypatch):
    manifest_factory([source_factory(f's{i}', z='.1', flux=i+1) for i in range(6)]).rename(tmp_path / 'spectra.csv')
    config_factory()
    fake_engine.write_text('import time\ntime.sleep(.3)\n' + fake_engine.read_text())
    observed = []
    original = parallel_controller.write_json
    def checkpoint(path, value):
        if path.name == 'campaign_status.json':
            observed.append(value.get('active_runs', []).copy())
        original(path, value)
    monkeypatch.setattr(parallel_controller, 'write_json', checkpoint)
    invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2', '--max-runs', '3')
    assert max(map(len, observed)) == 2
    assert all(len({r['execution_id'] for r in active}) == len(active) for active in observed)
    status = read_json(tmp_path / 'campaign_status.json')
    assert status['status'] == 'limited'
    assert status['runs'] == {'completed': 3, 'pending': 3}
    assert status['active_runs'] == []


def test_closing_pool_terminates_active_engine_group(tmp_path, source_factory,
        manifest_factory, config_factory, fake_engine, parallel_controller):
    rows = [source_factory('fast', z='.1'), source_factory('slow', z='.1', flux=2)]
    plan = make_plan(manifest_factory(rows), config_factory())
    output = tmp_path / 'run'
    save_plan(plan, output)
    launch_dir = tmp_path / 'workers'
    launch_dir.mkdir()
    fake_engine.write_text(
        "import os,time,sys\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).with_suffix('.pid').write_text(str(os.getpid()))\n"
        "time.sleep(.5 if sys.argv[2]=='fast' else 60)\n" + fake_engine.read_text())
    jobs = parallel_controller.execute_queue(plan['runs'], plan, output, 2,
                                             launch_dir, lambda _: None, lambda: None)
    first, record = next(jobs)
    assert first['spectrum_id'] == 'fast'
    assert record['status'] == 'completed'
    pidfiles = list(output.glob('attempts/*/*/candidates.pid'))
    assert len(pidfiles) == 2
    jobs.close()
    for path in pidfiles:
        with pytest.raises(ProcessLookupError):
            os.kill(int(path.read_text()), 0)
    assert sum(current_record(output, r) is not None for r in plan['runs']) == 1


def test_resume_refuses_changed_plan(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, monkeypatch):
    manifest_factory([source_factory(z='.1')]).rename(tmp_path / 'spectra.csv')
    config_factory()
    invoke(controller(), monkeypatch, tmp_path)
    config_factory(top_n=5)
    with pytest.raises(ValueError, match='frozen plan changed'):
        invoke(controller(), monkeypatch, tmp_path)
    assert len(list((tmp_path / 'run/attempts').glob('*/*/record.json'))) == 1


def test_parallel_disk_guard_prevents_launch(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, parallel_controller, monkeypatch):
    manifest_factory([source_factory(z='.1')]).rename(tmp_path / 'spectra.csv')
    config_factory()
    monkeypatch.setattr(parallel_controller.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    with pytest.raises(RuntimeError, match='20 GiB'):
        invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2')
    assert not list((tmp_path / 'run/attempts').glob('*/*/record.json'))
    assert read_json(tmp_path / 'campaign_status.json')['runs'] == {'pending': 1}


def test_parallel_failure_guard_stops_dispatch(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, parallel_controller, monkeypatch):
    manifest_factory([source_factory(f's{i}', z='.1', flux=i+1) for i in range(12)]).rename(tmp_path / 'spectra.csv')
    config_factory()
    fake_engine.write_text('raise SystemExit(2)\n')
    with pytest.raises(RuntimeError, match='six consecutive'):
        invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2')
    status = read_json(tmp_path / 'campaign_status.json')
    assert status['status'] == 'stopped'
    assert status['completed_this_invocation'] == 6
    # One already dispatched worker may finish before shutdown; no further work
    # is submitted once the guard fires and every saved result stays accounted.
    assert 6 <= status['runs']['failed'] <= 7
    assert sum(status['runs'].values()) == 12
    assert status['active_runs'] == []


def test_worker_crash_fails_closed(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, parallel_controller, monkeypatch):
    manifest_factory([source_factory(z='.1')]).rename(tmp_path / 'spectra.csv')
    config_factory()
    monkeypatch.setattr(parallel_controller, 'start_worker',
        lambda *args: subprocess.Popen([sys.executable, '-c', 'raise SystemExit(9)']))
    with pytest.raises(RuntimeError, match='worker exited 9'):
        invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2')
    status = read_json(tmp_path / 'campaign_status.json')
    assert status['status'] == 'stopped'
    assert status['runs'] == {'pending': 1}


def test_corrupt_saved_result_is_not_reused(tmp_path, source_factory, manifest_factory,
        config_factory, fake_engine, parallel_controller, monkeypatch):
    manifest_factory([source_factory(z='.1')]).rename(tmp_path / 'spectra.csv')
    config_factory()
    invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2')
    artifact = next((tmp_path / 'run/attempts').glob('*/*/candidates.json'))
    artifact.write_text('{}')
    invoke(parallel_controller, monkeypatch, tmp_path, '--workers', '2')
    status = read_json(tmp_path / 'campaign_status.json')
    assert status['completed_this_invocation'] == 1
    assert len(list((tmp_path / 'run/attempts').glob('*/*/record.json'))) == 2
