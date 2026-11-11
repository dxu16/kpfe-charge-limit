"""Passive, bounded capture for the manual RAM backend; default is plan only.

The logger module must already be loaded under separate approval. This script
never loads modules, changes charging controls, writes PMIC registers or boots.
It creates only a temporary trace instance/probe and files in the output folder.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

GROUP = 'kpfe_firmware_cause'
INSTANCE = 'kpfe_reconnect_audit'  # Matches the existing manual phase runner.
REGISTERS = (0x2606, 0x2646, 0x2650, 0x2654, 0x2658)


def interrupt(signum, frame):
    raise InterruptedError(signum)


def dynamic_write(value):
    fd = os.open('/sys/kernel/tracing/dynamic_events', os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (value + '\n').encode())
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--trace-suspend', action='store_true')
    parser.add_argument('--automatic-driver-note', help='SHA-256 of the approved automatic driver build ID note')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 660:
        parser.error('duration must be 1..660 seconds')
    print(json.dumps(dict(execute=args.execute, seconds=args.seconds,
                          firmware_log=True, actual_transmitted_requests=True,
                          trace_suspend=args.trace_suspend,
                          automatic_policy=bool(args.automatic_driver_note),
                          register_reads=[hex(x) for x in REGISTERS],
                          charging_control_writes=False, module_loads=False)), flush=True)
    if not args.execute:
        return
    assert os.geteuid() == 0
    assert b'konkr,pocket-fit-elite' in Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    assert Path('/sys/module/pmic_pdcharger_ulog').is_dir(), 'Logger must be separately approved and loaded'
    bat = Path('/sys/class/power_supply/battery')
    automatic = 'qcom_battmgr_host_worker' in Path('/proc/kallsyms').read_text()
    if args.automatic_driver_note:
        note = Path('/sys/module/qcom_battmgr/notes/.note.gnu.build-id')
        assert automatic and hashlib.sha256(note.read_bytes()).hexdigest() == args.automatic_driver_note
    else:
        assert not automatic and (bat / 'charge_behaviour').exists(), 'Manual diagnostic backend required'
    assert (bat / 'health').read_text().strip() == 'Good'
    root = Path('/sys/kernel/tracing')
    trace = root / 'instances' / INSTANCE
    assert not trace.exists() and not (root / 'events' / GROUP).exists()
    assert (root / 'events/pmic_pdcharger_ulog/enable').exists()
    regmap = Path('/sys/kernel/debug/regmap/0-07')
    assert (regmap / 'range').read_text().strip() == '0-ffff'
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    probe = False
    fd = None
    stream = None
    pipe = None
    try:
        dynamic_write(f'p:{GROUP}/wire pmic_glink_send length=$arg3:u64 owner=+0($arg2):u32 opcode=+8($arg2):u32 word3=+12($arg2):u32 word4=+16($arg2):u32 word5=+20($arg2):u32')
        probe = True
        trace.mkdir()
        (trace / 'tracing_on').write_text('0\n')
        (trace / 'buffer_size_kb').write_text('8192\n')
        (trace / 'trace_clock').write_text('boot\n')
        wire = trace / 'events' / GROUP / 'wire'
        (wire / 'filter').write_text('length == 24 && owner == 32778 && (opcode == 6 || opcode == 48 || opcode == 49 || opcode == 72)\n')
        (wire / 'enable').write_text('1\n')
        (trace / 'events/pmic_pdcharger_ulog/enable').write_text('1\n')
        if args.trace_suspend:
            (trace / 'events/power/suspend_resume/enable').write_text('1\n')
        stream = (args.output_dir / 'firmware-and-requests.txt').open('wb')
        pipe = subprocess.Popen(['cat', str(trace / 'trace_pipe')], stdout=stream)
        fd = os.open(regmap / 'registers', os.O_RDONLY)
        (trace / 'tracing_on').write_text('1\n')
        start = time.monotonic()
        with (args.output_dir / 'samples.jsonl').open('w') as samples:
            while time.monotonic() - start < args.seconds:
                values = dict(line.split('=', 1) for line in (bat / 'uevent').read_text().splitlines() if line.startswith('POWER_SUPPLY_'))
                registers = {}
                for address in REGISTERS:
                    raw = os.pread(fd, 9, address * 9)
                    match = re.fullmatch(rb'([0-9a-f]{4}): ([0-9a-f]{2})\n', raw)
                    assert match and int(match[1], 16) == address, repr(raw)
                    registers[hex(address)] = int(match[2], 16)
                online = Path('/sys/class/power_supply/qcom-battmgr-usb/online').read_text().strip()
                item = dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            boot_seconds=float(Path('/proc/uptime').read_text().split()[0]),
                            elapsed=round(time.monotonic() - start, 3),
                            values=values, usb_online=online, registers=registers)
                samples.write(json.dumps(item) + '\n')
                samples.flush()
                if (values['POWER_SUPPLY_HEALTH'] != 'Good' or
                        int(values['POWER_SUPPLY_TEMP']) > 400 or
                        int(values['POWER_SUPPLY_VOLTAGE_MAX']) < 4360000):
                    raise RuntimeError('Stop diagnostic and unplug: health/temperature/voltage-ceiling check failed')
                assert pipe.poll() is None, 'Trace stream unexpectedly stopped'
                time.sleep(0.25)
    finally:
        if trace.exists():
            (trace / 'tracing_on').write_text('0\n')
            # Allow the streaming reader to consume the final trace batch.
            time.sleep(0.2)
        if pipe is not None:
            if pipe.poll() is None:
                pipe.terminate()
            pipe.wait(timeout=5)
        if stream is not None:
            stream.close()
        if fd is not None:
            os.close(fd)
        if trace.exists():
            stats = {p.parent.name: p.read_text() for p in (trace / 'per_cpu').glob('cpu*/stats')}
            (args.output_dir / 'trace-stats.json').write_text(json.dumps(stats, indent=2) + '\n')
            if (trace / 'events/pmic_pdcharger_ulog/enable').exists():
                (trace / 'events/pmic_pdcharger_ulog/enable').write_text('0\n')
            if (trace / 'events' / GROUP / 'wire/enable').exists():
                (trace / 'events' / GROUP / 'wire/enable').write_text('0\n')
            if args.trace_suspend:
                (trace / 'events/power/suspend_resume/enable').write_text('0\n')
            trace.rmdir()
        if probe:
            dynamic_write(f'-:{GROUP}/wire')
    print('CAPTURE_COMPLETE; controls unchanged; logger remains loaded until reboot', flush=True)


if __name__ == '__main__':
    main()
