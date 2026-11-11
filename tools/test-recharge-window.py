"""Bounded RAM-driver test of real discharge and recharge after reconnection.

Requires a person to unplug/reconnect when prompted. Does not establish
continuous-connected hysteresis. Restores original thresholds on exit.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--execute', action='store_true')
args = parser.parse_args()
bat = Path('/sys/class/power_supply/battery')
usb = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
started = time.monotonic()


def emit(event, **fields):
    print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         elapsed=round(time.monotonic() - started, 3),
                         event=event, **fields)), flush=True)


def snapshot():
    values = {key.removeprefix('POWER_SUPPLY_').lower(): value
              for key, value in (line.split('=', 1)
                                 for line in (bat / 'uevent').read_text().splitlines()
                                 if line.startswith('POWER_SUPPLY_'))}
    values['usb_online'] = usb.read_text().strip()
    return values


def write(name, value):
    emit('write', attribute=name, value=value)
    (bat / name).write_text(str(value) + '\n')


initial = snapshot()
emit('plan', execute=args.execute, initial=initial, start=91, end=92,
     requires_manual_cable_changes=True, continuous_connected_hysteresis=False)
if not args.execute:
    raise SystemExit(0)
assert os.geteuid() == 0
assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
assert 'qcom_battmgr_host_worker' in Path('/proc/kallsyms').read_text()
assert initial['health'] == 'Good' and initial['usb_online'] == '1'
assert initial['capacity'] == '92' and int(initial['temp']) <= 350
assert initial['charge_control_start_threshold'] == '70'
assert initial['charge_control_end_threshold'] == '85'
ceiling = int(initial['voltage_max'])


def interrupted(signum, frame):
    raise InterruptedError(f'Signal {signum}')


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)


def sample():
    values = snapshot()
    emit('sample', values=values)
    assert values['health'] == 'Good', 'Health warning; unplug charger'
    assert int(values['temp']) <= 400, 'Temperature above 40 C; unplug charger'
    assert int(values['voltage_max']) >= ceiling - 20000, 'Voltage ceiling dropped'
    assert int(values['voltage_now']) <= ceiling + 50000, 'Voltage above ceiling'
    assert int(values['capacity']) <= 93, 'Target overshoot'
    assert time.monotonic() - started < 1800, 'Total test deadline'
    return values


def wait_for(predicate, seconds, interval=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        values = sample()
        if predicate(values):
            return values
        time.sleep(interval)
    raise TimeoutError('Phase deadline')


try:
    write('charge_control_end_threshold', 92)
    write('charge_control_start_threshold', 91)
    emit('READY_UNPLUG')
    wait_for(lambda v: v['usb_online'] == '0', 180)
    emit('discharging')
    def discharged(values):
        assert values['usb_online'] == '0', 'Reconnected before discharge completed'
        return int(values['capacity']) <= 91
    wait_for(discharged, 1200)
    emit('READY_RECONNECT')
    wait_for(lambda v: v['usb_online'] == '1', 180)
    positive = 0
    def charging(values):
        global positive
        assert values['usb_online'] == '1', 'External power disconnected'
        positive = positive + 1 if int(values['current_now']) > 50000 else 0
        return positive >= 3
    wait_for(charging, 90, 1)
    emit('recharge_verified')
    def stopped(values):
        assert values['usb_online'] == '1', 'External power disconnected'
        return int(values['capacity']) >= 92 and abs(int(values['current_now'])) <= 50000 and values['status'] == 'Full'
    wait_for(stopped, 600)
    emit('automatic_stop_verified')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        assert stopped(sample()), 'Hold did not remain stable'
        time.sleep(5)
    emit('test_completed')
except BaseException as exc:
    emit('test_stopped', detail=str(exc))
    raise
finally:
    # Lower start first: setting end=85 while start=91 would be invalid.
    write('charge_control_start_threshold', initial['charge_control_start_threshold'])
    write('charge_control_end_threshold', initial['charge_control_end_threshold'])
    emit('controls_restored', values=snapshot())
