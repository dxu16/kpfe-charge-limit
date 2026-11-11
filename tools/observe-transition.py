"""Read-only, bounded charging observation. Does not change device controls."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--mode', choices=('observe', 'hold', 'charge', 'discharge'), default='observe')
parser.add_argument('--physical-enable', action='store_true',
                    help='Read the audited KPFE charger-enable bit during a hold')
args = parser.parse_args()
if args.physical_enable and args.mode != 'hold':
    parser.error('--physical-enable requires --mode hold')
assert 1 <= args.seconds <= 1800
bat = Path('/sys/class/power_supply/battery')
usb = Path('/sys/class/power_supply/qcom-battmgr-usb/online')
assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
start = time.monotonic()
charging = 0
positive_hold = 0
samples = 0
ceiling = int((bat / 'voltage_max').read_text())
capacity_ceiling = max(int((bat / 'capacity').read_text()),
                       int((bat / 'charge_control_end_threshold').read_text())) + 1


def emit(event, **fields):
    print(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          elapsed=round(time.monotonic() - start, 3),
                          label=args.label, event=event, **fields)), flush=True)


registers = None
try:
    if args.physical_enable:
        regmap = Path('/sys/kernel/debug/regmap/0-07')
        assert (regmap / 'range').read_text().strip() == '0-ffff'
        registers = os.open(regmap / 'registers', os.O_RDONLY)
    while True:
        values = {key.removeprefix('POWER_SUPPLY_').lower(): value
                  for key, value in (line.split('=', 1)
                                     for line in (bat / 'uevent').read_text().splitlines()
                                     if line.startswith('POWER_SUPPLY_'))}
        values['usb_online'] = usb.read_text().strip()
        if registers is not None:
            raw = os.pread(registers, 9, 0x2646 * 9)
            match = re.fullmatch(rb'2646: ([0-9a-f]{2})\n', raw)
            assert match, f'Unexpected charger-enable read: {raw!r}'
            values['charger_enable'] = int(match[1], 16) & 1
        samples += 1
        emit('sample', values=values)
        assert values['health'] == 'Good', 'Health fault; unplug charger'
        assert int(values['temp']) <= 400, 'Temperature above 40 C; unplug charger'
        assert int(values['voltage_max']) >= ceiling - 20000, 'Voltage ceiling dropped; unplug charger'
        assert int(values['voltage_now']) <= ceiling + 50000, 'Voltage exceeds expected ceiling; unplug charger'
        current = int(values['current_now'])
        charging += current > 50000
        if args.mode in ('hold', 'charge'):
            assert values['usb_online'] == '1', 'External power disconnected'
        if args.mode == 'hold':
            assert not values.get('charger_enable', 0), 'Charger enabled during hold; unplug charger'
            positive_hold = positive_hold + 1 if current > 50000 else 0
            assert positive_hold < 7, 'Persistent reported charging during limit hold'
            assert int(values['capacity']) <= capacity_ceiling, 'SOC increased beyond hold allowance'
        if args.mode == 'discharge':
            assert values['usb_online'] == '0', 'Disconnect charger for discharge observation'
        if time.monotonic() - start >= args.seconds:
            break
        time.sleep(min(5, args.seconds - (time.monotonic() - start)))
    if args.mode == 'charge':
        assert charging >= 3, 'No sustained positive charging current observed'
    emit('completed', samples=samples, charging_samples=charging)
except BaseException as exc:
    emit('stopped', reason=str(exc), controls_modified=False)
    raise
finally:
    if registers is not None:
        os.close(registers)
