import json
import re
import subprocess
from pathlib import Path


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout


exports = {line.split()[-1].removeprefix('__ksymtab_')
           for line in Path('/inputs/running-exports.txt').read_text().splitlines()}
candidate = set(re.findall(r'\bU\s+(\S+)', run('nm', '-u', '/output/qcom_battmgr.ko')))
original = set(re.findall(r'\bU\s+(\S+)', run('nm', '-u', '/inputs/qcom_battmgr.original.ko')))
report = {
    'missing_exports': sorted(candidate - exports),
    'added_imports': sorted(candidate - original),
    'removed_imports': sorted(original - candidate),
    'candidate_vermagic': run('modinfo', '-F', 'vermagic', '/output/qcom_battmgr.ko').strip(),
    'original_vermagic': run('modinfo', '-F', 'vermagic', '/inputs/qcom_battmgr.original.ko').strip(),
    'config_identical': not Path('/output/config-diff.txt').read_text(),
    'layouts': {},
}

layout_dir = Path('/output/layouts')
layout_dir.mkdir(exist_ok=True)
types = ('module', 'device', 'device_driver', 'auxiliary_device', 'auxiliary_driver',
         'power_supply_desc', 'power_supply_config', 'mutex', 'completion',
         'swait_queue_head', 'work_struct', 'of_device_id')
if '--automatic' in __import__('sys').argv:
    types += ('delayed_work', 'timer_list')
for name in types:
    texts = []
    for label, fmt, path in (('running', 'btf', '/inputs/running-vmlinux.btf'),
                             ('candidate', 'dwarf', '/output/qcom_battmgr.ko')):
        result = run('pahole', '-F', fmt, '-C', name, path)
        if not result.strip():
            raise RuntimeError(f'No layout for {name} ({label})')
        (layout_dir / f'{name}-{label}.txt').write_text(result)
        # Compare every emitted field offset/size, including bitfield positions,
        # plus aggregate sizes. DWARF can print explicit alignment annotations
        # omitted by BTF; the original text is retained for manual review.
        offsets = re.findall(r'/\*\s*(\d+)(?:\s*:\s*(\d+))?\s+(\d+)\s*\*/', result)
        sizes = re.findall(r'/\*\s*size:\s*(\d+)', result)
        texts.append({'offsets': offsets, 'sizes': sizes})
    report['layouts'][name] = {'match': texts[0] == texts[1],
                               'running': texts[0], 'candidate': texts[1]}

report['checks_pass'] = (not report['missing_exports'] and report['config_identical']
                         and report['candidate_vermagic'] == report['original_vermagic']
                         and all(x['match'] for x in report['layouts'].values()))
Path('/output/abi-audit.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != 'layouts'}, indent=2))
print('Layout matches:', {k: v['match'] for k, v in report['layouts'].items()})
if not report['checks_pass']:
    raise SystemExit('ABI review checks did not all pass; do not load module.')
