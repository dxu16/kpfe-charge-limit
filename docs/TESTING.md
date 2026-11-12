# Reproduction and test boundaries

## Read-only observation

Read the battery uevent every five seconds, saving timestamps. The reporter's intended field filter is below with shell-safe extended regular expression spelling corrected. This reads controls and does not change them.

```sh
watch -t -c -n 5 'grep -E "^POWER_SUPPLY_(MODEL_NAME|CAPACITY|STATUS|HEALTH|CYCLE_COUNT|TEMP|VOLTAGE_NOW|VOLTAGE_MAX|CURRENT_NOW|POWER_NOW|CONSTANT_CHARGE_CURRENT|CONSTANT_CHARGE_CURRENT_MAX|CHARGE_FULL|CHARGE_FULL_DESIGN|CHARGE_NOW|CHARGE_CONTROL_START_THRESHOLD|CHARGE_CONTROL_END_THRESHOLD)=" /sys/class/power_supply/battery/uevent'
```

For an already planned charge, observe from below the limit through crossing and at least ten minutes of hold. Record USB online and firmware/kernel versions too. Stop the diagnostic on a health fault; unplug and use the previously verified recovery procedure. Do not repeatedly reproduce the protection event just to collect more identical samples.

## Offline tests

Run `python3 tests/verify_artifacts.py` from the repository root. It checks recorded hashes and verifies that the full submission and PR follow-up produce the same `0905`, which reconstructs the exact tested driver. The historical C fixtures cover the earlier OEM bypass policy and status logic. They require a compiler and write outputs into temporary directories. The base driver's hardware procedure is in the [charge-rate patch notes](../experimental/charge-rate-policy/README.md).

Run `python3 experimental/usb-pd-reconnect/test-pd-reconnect.py` with a C compiler (`CC` defaults to `cc`). The harness compiles functions from the tested driver and simulates the 5 V timeout, early 9 V, cable removal, suspend gating, and late or missing firmware replies. See the [USB-PD test matrix](../experimental/usb-pd-reconnect/README.md#validation) for the hardware results and remaining gaps.

`tools/prepare-submission.ps1` recreates the overlay, the full Armada diff and the PR follow-up from the pinned snapshots and tested driver source. Run verification after regenerating.

## Historical OEM bypass hardware runner

`tools/test-background-limit.py` is the bounded diagnostic retained from OEM bypass testing. The final `0x06` driver has its own linked procedure above. It is **not** part of the Armada submission or an unattended test service. It reads KPFE-specific paths, requires root for temporary tracing/control writes, and requires explicit `--execute --human-wake-guard` plus output directory to run the active test. Inspect it and obtain approval before any future device execution. Never point it at another model merely because the CPU matches.

It saves controls, chooses a target one point above SOC (at most 95%), verifies charging, enters s2idle without an RTC alarm, relies on an agreed manual wake backup, checks a ten-minute hold and restores saved settings. Exceptions cannot guarantee recovery from power loss or a failed kernel. Preserve a verified stock image and working recovery connection. No future device test or installed-system modification is authorized by this repository.

## Build provenance

The historical isolated build used a Fedora 44 container, GCC 16.2.1 and the complete Armada-patched Linux 7.2.6 tree. `build-kpfe-module-exact-config.sh` expects `/work/linux-7.2.6`, `/inputs` runtime config/module data and `/output`. `audit-kpfe-module.py` additionally requires the captured running exports, BTF/type data and analysis tools described in its code. These inputs are not bundled: the scripts document the original audit, not a complete standalone kernel build system.

For a maintainer build, apply the Armada submission to a full checkout and use `just package kernel`, followed by the project's normal image/recovery workflow. This packaging task did not repeat a full image build or deploy anything. The previous hardware tests used RAM-only `fastboot boot`; no flash/erase/unlock or voltage/protection writes were performed.
