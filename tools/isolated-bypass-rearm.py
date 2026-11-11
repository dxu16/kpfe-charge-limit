"""Approved diagnostic phases for the manual RAM backend; default is plan only.

Keeps native limiting disabled at 100 during the comparison so only OEM
property 29 changes. Never run against the automatic backend or unattended.
"""
import argparse
import datetime
import json
from pathlib import Path
import signal
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--phase', choices=('setup', 'rearm', 'restore'), required=True)
    args = parser.parse_args()
    print(json.dumps(dict(execute=args.execute, phase=args.phase,
                          normal_charge_bound_seconds=15 if args.phase == 'setup' else 2)), flush=True)
    if not args.execute:
        return
    bat = Path('/sys/class/power_supply/battery')
    end, behaviour = bat / 'charge_control_end_threshold', bat / 'charge_behaviour'
    assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    assert behaviour.exists() and 'qcom_battmgr_host_worker' not in Path('/proc/kallsyms').read_text()
    usb = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
    marker = Path('/sys/kernel/tracing/instances/kpfe_reconnect_audit/trace_marker')

    def emit(phase):
        values = {k.removeprefix('POWER_SUPPLY_').lower(): v
                  for k, v in (line.split('=', 1) for line in (bat / 'uevent').read_text().splitlines()
                               if line.startswith('POWER_SUPPLY_'))}
        print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                              phase=phase, values=values)), flush=True)
        return values

    def healthy():
        values = emit(args.phase)
        assert values['health'] == 'Good' and int(values['temp']) <= 400
        assert int(values['voltage_max']) >= 4360000

    def interrupted(signum, frame):
        raise InterruptedError(signum)

    signal.signal(signal.SIGTERM, interrupted)
    healthy()
    if args.phase == 'restore':
        assert usb.read_text().strip() == '0'
        behaviour.write_text('auto')
        end.write_text('85')
        (bat / 'charge_control_start_threshold').write_text('70')
        emit('restored')
        return
    assert usb.read_text().strip() == '1'
    marker.write_text(f'ISOLATED_OEM phase={args.phase}\n')
    if args.phase == 'setup':
        assert end.read_text().strip() == '85'
        end.write_text('100')
    else:
        assert end.read_text().strip() == '100'
    try:
        behaviour.write_text('auto')
        deadline = time.monotonic() + (15 if args.phase == 'setup' else 2)
        if args.phase == 'setup':
            while time.monotonic() < deadline:
                healthy()
                time.sleep(0.5)
        else:
            while (bat / 'constant_charge_current').read_text().strip() == '0':
                healthy()
                if time.monotonic() >= deadline:
                    raise TimeoutError('Normal firmware current setting was not acknowledged')
                time.sleep(0.05)
    finally:
        behaviour.write_text('inhibit-charge')
        marker.write_text(f'ISOLATED_OEM phase={args.phase} inhibit-restored\n')
    assert end.read_text().strip() == '100'
    emit('inhibit-restored-native-end-still-100')


if __name__ == '__main__':
    main()
