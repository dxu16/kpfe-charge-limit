"""Attended charge-rate diagnostic phases; no hardware access without --execute.

Requires the separately approved RAM image and passive capture. Deadlines bound
polling, not blocking firmware I/O. On an alert, unplug; never retry automatically.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time


NOTE_SHA256 = '2a1a2a89ed051c24faa1656fcffe6465ffcb9a2cc0b2e4f3ee8bd4f56504d8cd'
BAT = Path('/sys/class/power_supply/battery')
USB = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
MARKER = Path('/sys/kernel/tracing/instances/kpfe_reconnect_audit/trace_marker')


def read(name):
    return (BAT / name).read_text().strip()


def write(name, value):
    (BAT / name).write_text(str(value))


def stop_selected():
    # power_supply sysfs may list all choices with the selected one bracketed.
    return read('charge_behaviour') in ('inhibit-charge', 'auto [inhibit-charge]')


def sample(fd, phase):
    values = dict(line.split('=', 1) for line in (BAT / 'uevent').read_text().splitlines()
                  if line.startswith('POWER_SUPPLY_'))
    raw = os.pread(fd, 9, 0x2646 * 9)
    match = re.fullmatch(rb'2646: ([0-9a-f]{2})\n', raw)
    if not match:
        raise RuntimeError(f'Invalid charger-enable read: {raw!r}')
    item = dict(phase=phase, monotonic=time.monotonic(), values=values,
                usb_online=USB.read_text().strip(), charger_enable=int(match[1], 16) & 1)
    print(json.dumps(item), flush=True)
    if (values['POWER_SUPPLY_HEALTH'] != 'Good' or
            not 100 <= int(values['POWER_SUPPLY_TEMP']) <= 400 or
            int(values['POWER_SUPPLY_VOLTAGE_MAX']) < 4360000):
        raise RuntimeError('UNPLUG: health, temperature or voltage-ceiling alert')
    return item


def interrupted(signum, frame):
    raise InterruptedError(signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--phase', choices=('setup', 'resume', 'observe', 'restore'), required=True)
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    max_seconds = 600 if args.phase == 'observe' else 20
    if not 1 <= args.seconds <= max_seconds:
        parser.error(f'{args.phase} duration must be 1..{max_seconds} seconds')
    print(json.dumps(dict(execute=args.execute, phase=args.phase,
                          normal_charge_polling_bound_seconds=5,
                          stop_settle_seconds=5, observation_seconds=args.seconds,
                          firmware_io_may_extend_deadlines=True)), flush=True)
    if not args.execute:
        return
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    if b'konkr,pocket-fit-elite' not in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0'):
        raise RuntimeError('KPFE required')
    note = Path('/sys/module/qcom_battmgr/notes/.note.gnu.build-id')
    if hashlib.sha256(note.read_bytes()).hexdigest() != NOTE_SHA256:
        raise RuntimeError('Wrong loaded driver; no controls changed')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    if args.phase == 'restore':
        if USB.read_text().strip() != '0':
            raise RuntimeError('Unplug before restoring')
        write('charge_behaviour', 'auto')
        write('charge_control_end_threshold', 85)
        write('charge_control_start_threshold', 70)
        print('CONTROLS_RESTORED; reboot normally and verify stock', flush=True)
        return
    if not MARKER.exists():
        raise RuntimeError('Start approved passive firmware capture first')
    regmap = Path('/sys/kernel/debug/regmap/0-07')
    if (regmap / 'range').read_text().strip() != '0-ffff':
        raise RuntimeError('Unexpected register map')
    fd = os.open(regmap / 'registers', os.O_RDONLY)
    try:
        first = sample(fd, 'preflight')
        if first['usb_online'] != '1':
            raise RuntimeError('External power required')
        if args.phase == 'setup':
            if read('charge_control_end_threshold') != '85':
                raise RuntimeError('Expected original 85% limit')
        elif read('charge_control_end_threshold') != '100':
            raise RuntimeError('Native limiter must remain disabled at 100%')
        MARKER.write_text(f'CHARGE_RATE phase={args.phase}\n')
        if args.phase in ('setup', 'resume'):
            try:
                if args.phase == 'setup':
                    write('charge_control_end_threshold', 100)
                write('charge_behaviour', 'auto')
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    sample(fd, 'normal-charge-window')
                    time.sleep(0.25)
            finally:
                # A failed stop is an unplug alert, not grounds for a retry.
                write('charge_behaviour', 'inhibit-charge')
                MARKER.write_text('CHARGE_RATE stop-acknowledged\n')
            settle = time.monotonic() + 5
        else:
            if not stop_selected():
                raise RuntimeError('STOP must already be selected; observe writes no controls')
            settle = time.monotonic()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            item = sample(fd, 'stop-observation')
            if item['usb_online'] != '1':
                raise RuntimeError('External power disconnected; observation ended')
            if time.monotonic() >= settle and (item['charger_enable'] or
                    int(item['values']['POWER_SUPPLY_CURRENT_NOW']) > 100000):
                raise RuntimeError('UNPLUG: physical stop not established; no automatic recovery')
            time.sleep(0.25)
        print('OBSERVATION_COMPLETE; STOP remains selected; inspect capture', flush=True)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
