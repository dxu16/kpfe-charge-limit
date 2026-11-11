"""Bounded charger-attachment-during-s2idle diagnostic; never writes controls.

A person connects the charger after suspend and provides a manual wake backup.
Request/reply probes observe existing traffic without polling during suspend.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--execute', action='store_true')
parser.add_argument('--human-wake-guard', action='store_true')
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
bat = Path('/sys/class/power_supply/battery')
usb = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
rtc = Path('/sys/class/rtc/rtc0/wakealarm')
started = time.clock_gettime(time.CLOCK_BOOTTIME)
group = 'kpfe_attach_sleep'
trace = None
probes = []


def now():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def emit(event, **fields):
    print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         elapsed=round(now() - started, 3), event=event, **fields)), flush=True)


def snapshot():
    v = {k.removeprefix('POWER_SUPPLY_').lower(): x for k, x in
         (line.split('=', 1) for line in (bat / 'uevent').read_text().splitlines()
          if line.startswith('POWER_SUPPLY_'))}
    v['usb_online'] = usb.read_text().strip()
    return v


def interrupts():
    result = {}
    for line in Path('/proc/interrupts').read_text().splitlines():
        if any(x in line for x in ('pmic_pwrkey', 'pm8xxx_rtc_alarm', 'glink-smem')):
            p = line.split()
            result[p[0].rstrip(':')] = dict(name=p[-1], count=sum(map(int, p[1:9])))
    return result


def dynamic_write(text):
    fd = os.open('/sys/kernel/tracing/dynamic_events', os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (text + '\n').encode())
    finally:
        os.close(fd)


def interrupted(signum, frame):
    raise InterruptedError(f'Signal {signum}')


initial = snapshot()
emit('plan', execute=args.execute, initial=initial, charging_control_writes=False,
     rtc_alarm_armed=False, requires_manual_connection_and_wake=True)
if not args.execute:
    raise SystemExit(0)
assert os.geteuid() == 0 and args.human_wake_guard
assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
assert 'qcom_battmgr_host_worker' in Path('/proc/kallsyms').read_text()
assert '[s2idle]' in Path('/sys/power/mem_sleep').read_text()
assert initial['usb_online'] == '0' and initial['health'] == 'Good'
assert initial['charge_control_start_threshold'] == '70'
assert initial['charge_control_end_threshold'] == '85'
assert 85 <= int(initial['capacity']) <= 95 and int(initial['temp']) <= 350
assert not rtc.read_text().strip()
args.output_dir.mkdir(exist_ok=False)
ceiling = int(initial['voltage_max'])
capacity_ceiling = int(initial['capacity']) + 1
baseline_irqs = interrupts()


def sample():
    v = snapshot()
    emit('sample', values=v)
    assert v['health'] == 'Good', 'Health warning; unplug charger'
    assert int(v['temp']) <= 400, 'Temperature above 40 C; unplug charger'
    assert int(v['voltage_max']) >= ceiling - 20000, 'Voltage ceiling dropped'
    assert int(v['voltage_now']) <= ceiling + 50000, 'Voltage above ceiling'
    assert int(v['capacity']) <= capacity_ceiling, 'Capacity increased beyond hold allowance'
    assert now() - started < 1200, 'Total test deadline after resume'
    assert v['charge_control_start_threshold'] == initial['charge_control_start_threshold']
    assert v['charge_control_end_threshold'] == initial['charge_control_end_threshold']
    return v


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
try:
    root = Path('/sys/kernel/tracing')
    assert not (root / 'events' / group).exists()
    assert not (root / 'instances/kpfe-attach-sleep').exists()
    for definition, name in (
        (f'p:{group}/wire pmic_glink_send length=$arg3:u64 owner=+0($arg2):u32 opcode=+8($arg2):u32 property=+16($arg2):u32 value=+20($arg2):u32', 'wire'),
        (f'p:{group}/reply qcom_battmgr_callback length=$arg2:u64 owner=+0($arg1):u32 opcode=+8($arg1):u32 property=+12($arg1):u32 value=+16($arg1):s32 result=+20($arg1):s32', 'reply'),
        (f'r:{group}/online_return qcom_battmgr_host_set_online result=$retval:s32', 'online_return')):
        dynamic_write(definition)
        probes.append(name)
    trace = root / 'instances/kpfe-attach-sleep'
    trace.mkdir(exist_ok=False)
    (trace / 'trace_clock').write_text('boot\n')
    (trace / 'buffer_size_kb').write_text('8192\n')
    (trace / 'set_ftrace_filter').write_text('qcom_battmgr_host_worker\npm_system_wakeup\n')
    (trace / 'current_tracer').write_text('function\n')
    events = trace / 'events' / group
    common = 'length == 24 && owner == 32778 && '
    (events / 'wire/filter').write_text(common + '((opcode == 49 && property == 29) || (opcode == 48 && (property == 9 || property == 10 || property == 29)) || (opcode == 50 && property == 0))\n')
    (events / 'reply/filter').write_text(common + '((opcode == 48 && (property == 9 || property == 10 || property == 29)) || (opcode == 50 && property == 0))\n')
    for name in probes:
        (events / name / 'enable').write_text('1\n')
    for event in ('suspend_resume', 'wakeup_source_activate', 'wakeup_source_deactivate'):
        (trace / 'events/power' / event / 'enable').write_text('1\n')
    (trace / 'events/irq/irq_handler_entry/filter').write_text(' || '.join('irq == ' + irq for irq in baseline_irqs) + '\n')
    (trace / 'events/irq/irq_handler_entry/enable').write_text('1\n')
    before_values = sample()
    assert before_values['usb_online'] == '0'
    (trace / 'trace_marker').write_text('KPFE suspend offline; connect only after asleep\n')
    emit('SUSPENDING', action='Connect after asleep; manually wake five minutes after connection if still asleep')
    time.sleep(2)
    before, mono_before = now(), time.monotonic()
    subprocess.run(['systemctl', 'suspend'], check=True, timeout=360)
    deadline = time.monotonic() + 20
    while now() - before - (time.monotonic() - mono_before) < 0.5 and time.monotonic() < deadline:
        time.sleep(0.2)
    slept = max(0, now() - before - (time.monotonic() - mono_before))
    (trace / 'trace_marker').write_text(f'KPFE resume suspended_seconds={slept:.3f}\n')
    (trace / 'tracing_on').write_text('0\n')
    with (trace / 'trace').open('rb') as src, (args.output_dir / 'resume-kernel-trace.txt').open('wb') as dst:
        shutil.copyfileobj(src, dst)
    after_irqs = interrupts()
    manual = any(x['name'] == 'pmic_pwrkey' and x['count'] > baseline_irqs[i]['count']
                 for i, x in after_irqs.items())
    emit('resumed', suspended_seconds=slept, manual_power_irq=manual, irqs=after_irqs)
    assert slept >= 1, 'No demonstrated suspend interval'
    values = sample()
    assert values['usb_online'] == '1', 'Charger not connected on resume'
    if manual:
        assert abs(int(values['current_now'])) <= 50000, 'Positive/draining current on manual resume'
    else:
        emit('automatic_resume', scope='Attachment resumed the system; sustained suspended hold not established')
        deadline = time.monotonic() + 35
        while abs(int(values['current_now'])) > 50000 and time.monotonic() < deadline:
            time.sleep(1)
            values = sample()
    assert abs(int(values['current_now'])) <= 50000, 'Current failed to settle'
    for i, x in after_irqs.items():
        if x['name'] == 'pm8xxx_rtc_alarm':
            assert x['count'] == baseline_irqs[i]['count'], 'RTC IRQ occurred'
    assert not rtc.read_text().strip()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        values = sample()
        assert values['usb_online'] == '1'
        assert abs(int(values['current_now'])) <= 50000, 'Hold current did not remain stable'
        assert values['status'] == 'Full', 'Unexpected hold status'
        time.sleep(5)
    emit('test_completed', manual_power_irq=manual, charging_controls_unchanged=True)
except BaseException as exc:
    emit('test_stopped', detail=str(exc), unplug_if_health_or_current_warning=True)
    raise
finally:
    if trace is not None:
        (trace / 'tracing_on').write_text('0\n')
        with (trace / 'trace').open('rb') as src, (args.output_dir / 'kernel-trace.txt').open('wb') as dst:
            shutil.copyfileobj(src, dst)
        for name in probes:
            (trace / 'events' / group / name / 'enable').write_text('0\n')
        (trace / 'current_tracer').write_text('nop\n')
        for event in ('suspend_resume', 'wakeup_source_activate', 'wakeup_source_deactivate'):
            (trace / 'events/power' / event / 'enable').write_text('0\n')
        (trace / 'events/irq/irq_handler_entry/enable').write_text('0\n')
        trace.rmdir()
    for name in reversed(probes):
        dynamic_write(f'-:{group}/{name}')
