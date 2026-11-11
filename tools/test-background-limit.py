"""Stage-only background-s2idle test; explicit approval needed before execution.

The user intentionally wakes after five minutes. Trace probes establish whether
the firmware stop request succeeded BEFORE full resume. No RTC alarm is used.
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

BAT = Path('/sys/class/power_supply/battery')
USB = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
RTC = Path('/sys/class/rtc/rtc0/wakealarm')
parser = argparse.ArgumentParser()
parser.add_argument('--execute', action='store_true')
parser.add_argument('--human-wake-guard', action='store_true')
parser.add_argument('--output-dir', required=True)
args = parser.parse_args()
out = Path(args.output_dir)
started = time.clock_gettime(time.CLOCK_BOOTTIME)
phase = 'preflight'
trace = None
probes = []
modified = False


def now():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def emit(event, **kwargs):
    print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         elapsed=round(now() - started, 3), phase=phase,
                         event=event, **kwargs)), flush=True)


def dynamic_event_write(text):
    # Python append-mode FileIO seeks to EOF; tracefs rejects that seek.
    # Raw writes append a definition without truncating existing probes.
    fd = os.open('/sys/kernel/tracing/dynamic_events', os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (text + '\n').encode())
    finally:
        os.close(fd)


def snapshot():
    values = {}
    for line in (BAT / 'uevent').read_text().splitlines():
        key, _, value = line.partition('=')
        if key.startswith('POWER_SUPPLY_'):
            values[key.removeprefix('POWER_SUPPLY_').lower()] = value
    values['usb_online'] = USB.read_text().strip()
    return values


def interrupts():
    result = {}
    for line in Path('/proc/interrupts').read_text().splitlines():
        if any(name in line for name in ('pmic_pwrkey', 'pm8xxx_rtc_alarm', 'glink-smem')):
            parts = line.split()
            result[parts[0].rstrip(':')] = dict(name=parts[-1], count=sum(map(int, parts[1:9])))
    return result


def write(name, value):
    global modified
    modified = True
    emit('write', attribute=name, value=str(value))
    (BAT / name).write_text(str(value) + '\n')


initial = snapshot()
target = int(initial['capacity']) + 1
emit('plan', execute=args.execute, target=target, initial=initial,
     human_wake_guard=args.human_wake_guard, rtc_alarm_armed=False)
if not args.execute:
    raise SystemExit(0)
assert args.human_wake_guard, 'A human must wake the device after five minutes'
assert os.geteuid() == 0
assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
assert any('qcom_battmgr_host_worker' in line and '[qcom_battmgr]' in line
           for line in Path('/proc/kallsyms').read_text().splitlines())
assert '[s2idle]' in Path('/sys/power/mem_sleep').read_text()
assert not RTC.read_text().strip(), 'An existing RTC alarm would confound this test'
assert initial['health'] == 'Good' and initial['usb_online'] == '1'
assert 55 <= target <= 95 and int(initial['temp']) <= 350
assert int(initial['capacity']) < target, 'Insufficient percentage headroom'
assert initial['charge_control_end_threshold'] == '85'
assert initial['charge_control_start_threshold'] == '70'
out.mkdir(exist_ok=False)
(out / 'original-controls.json').write_text(json.dumps(initial, indent=2))
baseline_irqs = interrupts()
ceiling = int(initial['voltage_max'])


def sample():
    values = snapshot()
    emit('sample', values=values)
    assert values['health'] == 'Good', 'Health warning: ' + values['health']
    assert values['usb_online'] == '1', 'Charger disconnected'
    assert int(values['temp']) <= 400, 'Temperature exceeded 40C'
    assert int(values['voltage_max']) >= ceiling - 20000, 'Voltage ceiling dropped'
    assert int(values['voltage_now']) <= ceiling + 50000, 'Voltage exceeded ceiling'
    assert int(values['capacity']) <= target + 1, 'Target overshoot'
    assert now() - started < 1200, 'Exceeded total elapsed-time bound after resume'
    return values


def restore():
    global phase
    phase = 'restore'
    write('charge_control_end_threshold', initial['charge_control_end_threshold'])
    if (BAT / 'charge_control_start_threshold').read_text().strip() != initial['charge_control_start_threshold']:
        write('charge_control_start_threshold', initial['charge_control_start_threshold'])
    values = snapshot()
    assert values['charge_control_end_threshold'] == initial['charge_control_end_threshold']
    assert values['charge_control_start_threshold'] == initial['charge_control_start_threshold']
    emit('controls_restored', values=values, native_policy_still_disabled=True)
    (out / 'restored-controls.json').write_text(json.dumps(values, indent=2))


def interrupted(signum, frame):
    raise InterruptedError(f'Signal {signum}')


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
try:
    root = Path('/sys/kernel/tracing')
    assert not (root / 'events/kpfe_gap_test').exists(), 'Trace probe group already exists'
    for definition, name in (
        ('p:kpfe_gap_test/kpfe_property qcom_battmgr_request_property opcode=$arg2:s32 property=$arg3:s32 value=$arg4:u32', 'kpfe_property'),
        ('r:kpfe_gap_test/kpfe_property_return qcom_battmgr_request_property result=$retval:s32', 'kpfe_property_return'),
        ('p:kpfe_gap_test/kpfe_wire pmic_glink_send length=$arg3:u64 owner=+0($arg2):u32 opcode=+8($arg2):u32 property=+16($arg2):u32 value=+20($arg2):u32', 'kpfe_wire'),
        ('r:kpfe_gap_test/kpfe_online_return qcom_battmgr_host_set_online result=$retval:s32', 'kpfe_online_return'),
    ):
        dynamic_event_write(definition)
        probes.append(name)
    trace = root / 'instances/kpfe-background-limit-test'
    trace.mkdir(exist_ok=False)
    (trace / 'buffer_size_kb').write_text('4096\n')
    (trace / 'trace_clock').write_text('boot\n')
    (trace / 'set_ftrace_filter').write_text('qcom_battmgr_callback\nqcom_battmgr_host_worker\npm_system_wakeup\n')
    (trace / 'current_tracer').write_text('function\n')
    (trace / 'events/kpfe_gap_test/kpfe_property/filter').write_text('opcode == 49 && property == 29\n')
    (trace / 'events/kpfe_gap_test/kpfe_wire/filter').write_text('length == 24 && owner == 32778 && opcode == 49 && property == 29\n')
    for name in probes:
        (trace / 'events/kpfe_gap_test' / name / 'enable').write_text('1\n')
    for event in ('suspend_resume', 'wakeup_source_activate', 'wakeup_source_deactivate'):
        (trace / 'events/power' / event / 'enable').write_text('1\n')
    irqs = interrupts()
    (trace / 'events/irq/irq_handler_entry/filter').write_text(' || '.join('irq == ' + irq for irq in irqs) + '\n')
    (trace / 'events/irq/irq_handler_entry/enable').write_text('1\n')
    emit('trace_started', rtc_alarm_armed=False, irqs=irqs)
    phase = 'verify_charging'
    write('charge_control_end_threshold', target)
    deadline = now() + 90
    charging_samples = 0
    while now() < deadline:
        values = sample()
        charging_samples = charging_samples + 1 if int(values['current_now']) > 50000 else 0
        if charging_samples >= 3:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Charging failed to resume')
    emit('charging_verified')
    phase = 'suspend_crossing'
    values = sample()
    assert int(values['capacity']) < target, 'Target reached before sleep; retry later'
    assert not RTC.read_text().strip()
    (trace / 'trace_marker').write_text(f'KPFE background suspend soc={values["capacity"]} target={target}\n')
    emit('SUSPENDING', capacity=values['capacity'], target=target,
         action='Manually wake with power after five minutes')
    time.sleep(2)  # drain log traffic and ACKs before entering suspend
    before = now()
    mono_before = time.monotonic()
    subprocess.run(['systemctl', 'suspend'], check=True, timeout=360)
    awake_deadline = time.monotonic() + 20
    while (now() - before - (time.monotonic() - mono_before) < 0.5 and
           time.monotonic() < awake_deadline):
        time.sleep(0.2)
    slept = max(0, now() - before - (time.monotonic() - mono_before))
    (trace / 'trace_marker').write_text(f'KPFE manual resume suspended_seconds={slept:.3f}\n')
    # Preserve suspend evidence before the ten-minute observer can overwrite
    # the per-CPU ring buffers with ordinary userspace property reads.
    (trace / 'tracing_on').write_text('0\n')
    with (trace / 'trace').open('rb') as src, (out / 'resume-kernel-trace.txt').open('wb') as dst:
        shutil.copyfileobj(src, dst)
    after_irqs = interrupts()
    emit('resumed', suspended_seconds=slept, irqs=after_irqs)
    assert slept >= 30, 'Insufficient actual suspend time'
    assert any(entry['name'] == 'pmic_pwrkey' and entry['count'] > baseline_irqs[irq]['count']
               for irq, entry in after_irqs.items()), 'Unexpected automatic full resume'
    for _ in range(6):
        values = sample()
        time.sleep(1)
    assert int(values['capacity']) >= target, 'Target not reached before manual wake'
    assert abs(int(values['current_now'])) <= 50000, 'Battery current not settled'
    assert values['status'] == 'Full', 'Limit-held status was not Full'
    for irq, entry in interrupts().items():
        if entry['name'] == 'pm8xxx_rtc_alarm':
            assert entry['count'] == baseline_irqs[irq]['count'], 'RTC IRQ occurred during test'
    assert not RTC.read_text().strip()
    emit('background_test_observed', suspended_seconds=slept,
         stop_before_resume_requires_probe_trace_review=True)
    phase = 'post_resume_hold'
    deadline = now() + 600
    positive = 0
    upower_full = False
    while now() < deadline:
        values = sample()
        positive = positive + 1 if int(values['current_now']) > 50000 else 0
        assert positive < 8, 'Charging continued after stop'
        expected = 'Full' if int(values['capacity']) >= target else 'Not charging'
        assert values['status'] == expected, 'Unexpected limit-held status'
        if not upower_full:
            result = subprocess.run(['busctl', 'get-property', '--system',
                                     'org.freedesktop.UPower',
                                     '/org/freedesktop/UPower/devices/battery_battery',
                                     'org.freedesktop.UPower.Device', 'State'],
                                    text=True, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip() == 'u 4':
                upower_full = True
                emit('upower_fully_charged_verified')
        time.sleep(1)
    assert upower_full, 'UPower did not report fully charged at configured limit'
    restore()
    emit('test_completed', stop_before_resume_requires_probe_trace_review=True,
         steam_icon_requires_user_observation=True)
except BaseException as exc:
    emit('test_stopped', detail=str(exc), unplug_if_health_or_voltage_warning=True)
    if modified:
        try:
            restore()
        except Exception as restore_error:
            emit('RESTORATION_FAILED', detail=str(restore_error))
    raise SystemExit(1)
finally:
    if trace is not None:
        try:
            (trace / 'tracing_on').write_text('0\n')
            with (trace / 'trace').open('rb') as src, (out / 'kernel-trace.txt').open('wb') as dst:
                shutil.copyfileobj(src, dst)
            (trace / 'current_tracer').write_text('nop\n')
            for event in ('suspend_resume', 'wakeup_source_activate', 'wakeup_source_deactivate'):
                (trace / 'events/power' / event / 'enable').write_text('0\n')
            (trace / 'events/irq/irq_handler_entry/enable').write_text('0\n')
            for name in probes:
                (trace / 'events/kpfe_gap_test' / name / 'enable').write_text('0\n')
            trace.rmdir()
            emit('trace_saved')
        except Exception as exc:
            emit('trace_cleanup_error', detail=str(exc))
    for name in reversed(probes):
        try:
            dynamic_event_write('-:kpfe_gap_test/' + name)
        except Exception as exc:
            emit('probe_cleanup_error', detail=str(exc))
