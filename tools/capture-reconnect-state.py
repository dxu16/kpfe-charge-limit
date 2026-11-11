"""Bounded diagnostic: read charger registers and trace firmware requests.

Default prints the plan only. Execution changes temporary tracing, never
charging controls or PMIC registers. A patched RAM boot needs prior approval.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import signal
import time

REGISTERS = {0x2606: 'charger status', 0x2646: 'charger enable command',
             0x2650: 'precharge current configuration',
             0x2654: 'fast-charge current configuration',
             0x2658: 'float-voltage configuration'}
GROUP = 'kpfe_reconnect_audit'


def parse_uevent(text):
    return {key.removeprefix('POWER_SUPPLY_').lower(): value
            for key, value in (line.split('=', 1) for line in text.splitlines()
                               if line.startswith('POWER_SUPPLY_'))}


def decode_register(raw, address):
    match = re.fullmatch(rb'([0-9a-f]{4}): ([0-9a-f]{2}|XX)\n', raw)
    if not match or int(match[1], 16) != address:
        raise RuntimeError(f'Unexpected regmap output at {address:#x}: {raw!r}')
    if match[2] == b'XX':
        raise RuntimeError(f'Unreadable register at {address:#x}')
    return int(match[2], 16)


def dynamic_write(text):
    fd = os.open('/sys/kernel/tracing/dynamic_events', os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (text + '\n').encode())
    finally:
        os.close(fd)


def interrupted(signum, frame):
    raise InterruptedError(f'Signal {signum}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--manual-backend', action='store_true',
                        help='Capture the previously tested manual bypass backend')
    parser.add_argument('--detailed-trace', action='store_true',
                        help='Also trace current/acknowledgement reads and worker execution')
    parser.add_argument('--trace-only', action='store_true',
                        help='Record requests without polling battery or registers; use a separate safety observer')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    assert 1 <= args.seconds <= 900
    assert not args.trace_only or args.detailed_trace
    print(json.dumps(dict(execute=args.execute, seconds=args.seconds,
                          registers={hex(k): v for k, v in REGISTERS.items()},
                          charging_control_writes=False,
                          register_reads=not args.trace_only)), flush=True)
    if not args.execute:
        return
    assert os.geteuid() == 0
    assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    bat = Path('/sys/class/power_supply/battery')
    if args.manual_backend:
        assert (bat / 'charge_behaviour').exists()
    else:
        assert 'qcom_battmgr_host_worker' in Path('/proc/kallsyms').read_text()
    assert (bat / 'health').read_text().strip() == 'Good'
    regmap = Path('/sys/kernel/debug/regmap/0-07')
    if not args.trace_only:
        assert (regmap / 'range').read_text().strip() == '0-ffff'
    trace_root = Path('/sys/kernel/tracing')
    trace = trace_root / 'instances' / GROUP
    assert not trace.exists() and not (trace_root / 'events' / GROUP).exists()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    probes = []
    fd = None
    start = time.monotonic()
    try:
        for definition, name in (
            (f'p:{GROUP}/property qcom_battmgr_request_property opcode=$arg2:s32 property=$arg3:s32 value=$arg4:u32', 'property'),
            (f'r:{GROUP}/result qcom_battmgr_request_property result=$retval:s32', 'result')):
            dynamic_write(definition)
            probes.append(name)
        if args.detailed_trace:
            # This exact-build clone fixes opcode=48/value=0 and takes property
            # as its second argument; verified against module disassembly.
            symbol = 'qcom_battmgr_request_property.constprop.0'
            assert symbol in Path('/proc/kallsyms').read_text()
            for definition, name in (
                (f'p:{GROUP}/get {symbol} property=$arg2:s32', 'get'),
                (f'r:{GROUP}/get_result {symbol} result=$retval:s32', 'get_result'),
                (f'p:{GROUP}/wire pmic_glink_send length=$arg3:u64 owner=+0($arg2):u32 opcode=+8($arg2):u32 property=+16($arg2):u32 value=+20($arg2):u32', 'wire')):
                dynamic_write(definition)
                probes.append(name)
        trace.mkdir()
        (trace / 'buffer_size_kb').write_text('8192\n')
        (trace / 'trace_clock').write_text('boot\n')
        events = trace / 'events' / GROUP
        request_filter = 'opcode == 49 && property == 29'
        if args.detailed_trace:
            request_filter += ' || (opcode == 48 && (property == 9 || property == 10 || property == 29))'
            (trace / 'set_ftrace_filter').write_text('qcom_battmgr_host_worker\n')
            (trace / 'current_tracer').write_text('function\n')
        (events / 'property/filter').write_text(request_filter + '\n')
        if args.detailed_trace:
            (events / 'get/filter').write_text('property == 9 || property == 10 || property == 29\n')
            # Trace the transmitted 24-byte property request as well, covering
            # calls GCC may inline into helpers instead of the named wrapper.
            (events / 'wire/filter').write_text('length == 24 && owner == 32778 && ((opcode == 49 && property == 29) || (opcode == 48 && (property == 9 || property == 10 || property == 29)))\n')
        for name in probes:
            (events / name / 'enable').write_text('1\n')
        if not args.trace_only:
            fd = os.open(regmap / 'registers', os.O_RDONLY)
        with (args.output_dir / 'samples.jsonl').open('w') as log:
            while time.monotonic() - start <= args.seconds:
                if args.trace_only:
                    time.sleep(0.5)
                    continue
                values = parse_uevent((bat / 'uevent').read_text())
                values['usb_online'] = Path('/sys/class/power_supply/qcom-battmgr-usb/online').read_text().strip()
                regs = {hex(address): decode_register(os.pread(fd, 9, address * 9), address)
                        for address in REGISTERS}
                log.write(json.dumps(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                           elapsed=round(time.monotonic() - start, 3),
                                           values=values, registers=regs)) + '\n')
                log.flush()
                if (values['health'] != 'Good' or int(values['temp']) > 400 or
                        int(values['voltage_max']) < 4360000 or
                        int(values['voltage_now']) > int(values['voltage_max']) + 50000):
                    raise RuntimeError('Stop test and unplug: health/temperature/voltage-ceiling check failed')
                time.sleep(0.5)
    finally:
        if fd is not None:
            os.close(fd)
        if trace.exists():
            (trace / 'tracing_on').write_text('0\n')
            (args.output_dir / 'requests-trace.txt').write_text((trace / 'trace').read_text())
            for name in probes:
                (trace / 'events' / GROUP / name / 'enable').write_text('0\n')
            trace.rmdir()
        for name in reversed(probes):
            dynamic_write(f'-:{GROUP}/{name}')


if __name__ == '__main__':
    main()
