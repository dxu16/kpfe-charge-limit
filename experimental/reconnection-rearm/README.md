# Experimental reconnection correction

This revision implements the repair sequence demonstrated by the isolated manual-bypass test. It is now included in the canonical patch under `patches/`; the superseded candidate is archived under `history/`. It has compiled and passed focused tests and the module ABI audit; the RAM-only reconnection/hold run passed, and expanded tracing shows the recovery helper executing on both attached holds. A later persistent trial failed its hold and was rolled back; see the main validation record.

The candidate allows five seconds for gauge readings to settle after inhibition. If positive current above 50 mA persists, it allows one recovery attempt during that hold: release OEM bypass, wait for firmware's normal-current setting acknowledgement, then re-enter bypass and verify again. The acknowledgement loop has a two-second software deadline, in addition to firmware request timeouts. Read failures after a confirmed release do not skip the stop attempt.

A persistent failure remains an error rather than causing a repeated release/re-enter loop. The recovery budget resets after normal charging resumes or the worker observes external power absent. A failed stop request can be retried without performing another release, with a new settling interval after that stop succeeds. Existing health guards and status/current reporting remain in place.

The incremental patch changes one driver file: 89 additions and one replacement relative to the previous candidate. Combined with the original patch, the Linux delta is 409 additions and one deletion. No new interface, daemon or device-tree change is introduced.

The November 10 RAM run reached a working hold after both attachments. The subsequent ten-minute hold had 121 samples, Good health throughout, unchanged 4380000 uV ceiling, and current between -9155 and +1220 uA. The initial request-wrapper probe missed compiler-inlined recovery writes. Expanded compiler-clone return tracing subsequently shows the recovery helper completing readback on both attached holds; direct transmitted-request tracing subsequently verified SET 1 -> SET 0 in 50.763 ms, followed by hardware enable clear and near-zero current. Stock boot and module hashes were verified after restoring 85%/70%. See [result](../../evidence/revised-automatic-hold-20261110.json).

## Files and checks

- `make_candidate.py`: reproducible generation from the unchanged tested source, with input hash and unique-anchor checks.
- `qcom_battmgr.c`: complete experimental driver source.
- `reconnection-rearm.patch`: incremental Linux patch; apply after the archived original candidate.
- `test_rearm.py`: compiles the actual helpers/worker with injected firmware failures. Covers acknowledgement, timeout, GET/SET errors, a failed stop, gauge lag, idempotence, one recovery per hold, unplug reset, real drain and health faults.
- `build-evidence/`: exact-config module audit, RAM-image identity and focused test output. Binaries remain in the private local build archive.

The existing 523,584 policy cases and status fixtures also passed against this source. All 14 external type layouts, exports, configuration and vermagic matched the running kernel. Checkpatch reported zero errors/warnings for the incremental patch; optional spelling/const tables were unavailable.

Remaining validation includes rapid cable changes, failure/restart races, weak power sources, continuous-connected start-threshold cycling and other sleep modes. The revised s2idle crossing and real unplug/discharge/recharge check passed. Five seconds and 50 mA are settling/detection bounds informed by the capture, not an independent measurement of electrical isolation. Do not make this candidate the default merely because compilation and unit tests passed.
