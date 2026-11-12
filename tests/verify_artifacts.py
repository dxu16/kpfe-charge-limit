"""Verify patch reconstruction and public bundle integrity without a device."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAME = '0905-power-supply-qcom-battmgr-kpfe-oem-charge-limit.patch'
SUBMISSION_NAME = '0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch'
POLICY = ROOT / 'experimental/charge-rate-policy'
REL = Path('drivers/power/supply/qcom_battmgr.c')


def run(*args, cwd):
    if args[0] == 'git':
        args = ('git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', *args[1:])
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          capture_output=True).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


metadata = json.loads((ROOT / 'upstream/BASELINE.json').read_text())
assert digest(ROOT / 'src/patched' / REL) == metadata['tested_source_sha256']
for item in json.loads((ROOT / 'upstream/SNAPSHOT_BLOBS.json').read_text()):
    data = (ROOT / 'upstream' / item['path']).read_bytes()
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    assert blob == item['git_blob_sha1'], item['path']
kernel_patch = ROOT / 'patches' / NAME
with tempfile.TemporaryDirectory(prefix='kpfe-patch-check-') as tmp:
    tmp = Path(tmp)
    shutil.copytree(ROOT / 'src/base', tmp / 'kernel')
    run('git', 'apply', '--check', str(kernel_patch), cwd=tmp / 'kernel')
    run('git', 'apply', str(kernel_patch), cwd=tmp / 'kernel')
    assert (tmp / 'kernel' / REL).read_bytes() == (ROOT / 'src/patched' / REL).read_bytes()
    stats = run('git', 'apply', '--numstat', str(kernel_patch), cwd=tmp / 'kernel').strip()
    assert stats == f"{metadata['kernel_patch_additions']}\t{metadata['kernel_patch_deletions']}\t{REL.as_posix()}", stats
    shutil.copytree(ROOT / 'upstream', tmp / 'armada')
    submission = ROOT / 'submission/armada-kpfe-charge-limit.patch'
    run('git', 'apply', '--check', str(submission), cwd=tmp / 'armada')
    run('git', 'apply', str(submission), cwd=tmp / 'armada')
    outer_stats = run('git', 'apply', '--numstat', str(submission), cwd=tmp / 'armada')
    expected = {'packages/kernel/PATCHES.md', 'packages/kernel/patches/series',
                f'packages/kernel/patches/{SUBMISSION_NAME}'}
    assert {row.split('\t')[2] for row in outer_stats.strip().splitlines()} == expected
    for path in expected:
        assert (tmp / 'armada' / path).read_bytes() == (ROOT / 'submission/overlay' / path).read_bytes()
    assert (tmp / 'armada/packages/kernel/patches' / SUBMISSION_NAME).read_bytes() == (POLICY / 'charge-rate-policy.patch').read_bytes()
    series = (tmp / 'armada/packages/kernel/patches/series').read_text().splitlines()
    assert series.count(SUBMISSION_NAME) == 1 and NAME not in series
    assert series[series.index(SUBMISSION_NAME) - 1].startswith('0904-')
    assert SUBMISSION_NAME in (tmp / 'armada/packages/kernel/PATCHES.md').read_text()
    assert {p.relative_to(ROOT / 'submission/overlay').as_posix()
            for p in (ROOT / 'submission/overlay').rglob('*') if p.is_file()} == expected
    experiment = ROOT / 'experimental/reconnection-rearm'
    if experiment.exists():
        shutil.copytree(ROOT / 'src/base', tmp / 'historical')
        run('git', 'apply', str(ROOT / 'history/pre-reconnection-candidate/charge-limit.patch'), cwd=tmp / 'historical')
        run('git', 'apply', '--check', str(experiment / 'reconnection-rearm.patch'), cwd=tmp / 'historical')
        run('git', 'apply', str(experiment / 'reconnection-rearm.patch'), cwd=tmp / 'historical')
        assert (tmp / 'historical' / REL).read_bytes() == (experiment / 'qcom_battmgr.c').read_bytes()
        print('PASS: experimental recovery patch reconstructs the built revision')
    late = ROOT / 'experimental/late-gauge-verification'
    if late.exists():
        assert experiment.exists()
        run('git', 'apply', '--check', str(late / 'late-gauge.patch'), cwd=tmp / 'historical')
        run('git', 'apply', str(late / 'late-gauge.patch'), cwd=tmp / 'historical')
        assert (tmp / 'historical' / REL).read_bytes() == (late / 'qcom_battmgr.c').read_bytes()
        assert (tmp / 'kernel' / REL).read_bytes() == (late / 'qcom_battmgr.c').read_bytes()
        print('PASS: one-line late-gauge experiment reconstructs its audited source')
    rate = ROOT / 'experimental/charge-rate-stop'
    if rate.exists():
        rate_meta = json.loads((rate / 'metadata.json').read_text())
        build = json.loads((rate / 'build-evidence.json').read_text())
        assert digest(rate / 'qcom_battmgr.c') == rate_meta['source_sha256'] == build['source_sha256']
        shutil.copytree(ROOT / 'src/base', tmp / 'charge-rate')
        run('git', 'apply', str(rate / 'charge-rate-diagnostic.patch'), cwd=tmp / 'charge-rate')
        assert (tmp / 'charge-rate' / REL).read_bytes() == (rate / 'qcom_battmgr.c').read_bytes()
        hardware = json.loads((ROOT / 'evidence/charge-rate-first-test-20261110.json').read_text())
        assert build['hardware_tested'] and build['installed_or_loaded']
        assert not build['currently_loaded'] and not build['persistently_installed']
        assert hardware['source_sha256'] == build['source_sha256']
        assert hardware['stock_restored'] and hardware['stop_resume_stop_passed']
        assert build['config_identical'] and not build['missing_exports']
        assert all(build['external_layouts_match'].values())
        print('PASS: separate charge-rate diagnostic reconstructs its compiled source with short hardware-test evidence')
    policy = ROOT / 'experimental/charge-rate-policy'
    if policy.exists():
        build = json.loads((policy / 'build-evidence.json').read_text())
        shutil.copytree(ROOT / 'src/base', tmp / 'charge-rate-policy')
        patch = policy / 'charge-rate-policy.patch'
        run('git', 'apply', str(patch), cwd=tmp / 'charge-rate-policy')
        assert (tmp / 'charge-rate-policy' / REL).read_bytes() == (policy / 'qcom_battmgr.c').read_bytes()
        assert digest(policy / 'qcom_battmgr.c') == build['source_sha256']
        assert build['abi_checks_pass']
        if build['hardware_tested']:
            hardware = json.loads((policy / build['hardware_evidence']).read_text())
            assert hardware['source_sha256'] == build['source_sha256']
            assert hardware['stock_restored']
        print('PASS: automatic charge-rate patch reconstructs the audited RAM candidate')
        pd = ROOT / 'experimental/usb-pd-reconnect'
        pd_evidence = ROOT / 'evidence/usb-pd-20261112'
        pd_build = json.loads((pd / 'build-evidence.json').read_text())
        pd_audit = json.loads((pd_evidence / 'abi-audit.json').read_text())
        pd_boot = json.loads((pd_evidence / 'temporary-boot-report.json').read_text())
        pd_installed = json.loads((pd_evidence / 'installed-boot-r2.json').read_text())
        pd_hold = json.loads((pd_evidence / 'installed-hold-summary-r2.json').read_text())
        pd_tree = tmp / 'charge-rate-policy'
        run('git', 'apply', '--check', str(pd / 'pd-reconnect.patch'), cwd=pd_tree)
        run('git', 'apply', str(pd / 'pd-reconnect.patch'), cwd=pd_tree)
        assert (pd_tree / REL).read_bytes() == (pd / 'qcom_battmgr.c').read_bytes()
        assert digest(pd / 'qcom_battmgr.c') == pd_build['source_sha256']
        assert pd_audit['checks_pass'] and pd_audit['config_identical']
        module_path = REL.with_suffix('.ko').as_posix()
        assert pd_boot['changed_entries'] == [f'usr/lib/modules/{pd_build["kernel"]}/kernel/{module_path}']
        assert pd_boot['test_module_sha256'] == pd_build['module_sha256']
        assert pd_boot['temporary_boot_sha256'] == pd_build['candidate_boot_sha256']
        assert pd_installed['driver_build_id_sha256'] == pd_build['driver_build_id_note_sha256']
        assert pd_build['ram_boot_tested'] and pd_build['installed_image_tested']
        assert pd_hold['hold_seconds'] >= 600 and pd_hold['final']['usb']['voltage_max'] == '9000000'
        assert pd_hold['final']['battery']['health'] == 'Good'
        print('PASS: USB-PD follow-up reconstructs the audited and installed trial source')
        integration = policy / 'armada-charge-rate-policy.patch'
        if integration.exists():
            checkout = tmp / 'armada-charge-rate-policy'
            shutil.copytree(ROOT / 'upstream', checkout)
            name = '0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch'
            path = f'packages/kernel/patches/{name}'
            run('git', 'apply', '--check', str(integration), cwd=checkout)
            stats = run('git', 'apply', '--numstat', str(integration), cwd=checkout)
            assert {row.split('\t')[2] for row in stats.strip().splitlines()} == {
                path, 'packages/kernel/patches/series', 'packages/kernel/PATCHES.md'}
            run('git', 'apply', str(integration), cwd=checkout)
            assert (checkout / path).read_bytes() == patch.read_bytes()
            series = (checkout / 'packages/kernel/patches/series').read_text().splitlines()
            assert series.count(name) == 1 and series[series.index(name) - 1].startswith('0904-')
            assert name in (checkout / 'packages/kernel/PATCHES.md').read_text()
            print('PASS: Armada integration inserts the exact tested charge-rate patch')

manifest = ROOT / 'MANIFEST.sha256'
recorded = set()
for line in manifest.read_text().splitlines():
    expected_hash, relative = line.split('  ', 1)
    assert relative not in recorded
    recorded.add(relative)
    path = ROOT / relative
    assert path.is_file() and digest(path) == expected_hash, relative
actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()
          and '.git' not in p.relative_to(ROOT).parts
          and '__pycache__' not in p.relative_to(ROOT).parts and p != manifest}
assert actual == recorded, (actual - recorded, recorded - actual)
print(f"PASS: tested source hash; Linux patch reconstructs exact candidate ({metadata['kernel_patch_additions']}+/1-)")
print('PASS: public Armada snapshot Git blob identities match pinned tree')
print('PASS: Armada diff applies exactly to three files; overlay, series and provenance match')
print(f'PASS: {len(recorded)} manifest file hashes and complete inventory')
