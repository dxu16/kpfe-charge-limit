# Charge-rate stop diagnostic

**Compiled, audited and tested in RAM for manual stop/resume and one short awake reconnect; stock restored.** This is separate from the canonical RFC and has no automatic percentage policy.

Uses the firmware's existing opcode 0x06: rate 0 requests stop, rate 100 requests normal charging. The decoded zero-rate path changes firmware charging state rather than merely voting current to zero. See the [interface audit](../../docs/CHARGE_RATE_INTERFACE_AUDIT.md) for code addresses, packet layout, upstream citation and unresolved behavior.

- `qcom_battmgr.c`: exact diagnostic source.
- `charge-rate-diagnostic.patch`: apply to `src/base`, 148 additions / 2 deletions. This count is for the manual diagnostic harness, not a proposed final charge-limit patch.
- `input-manual.patch` and `prepare.py`: reproducible transformation from the earlier manual harness; no binary/vendor inputs required.
- `test_protocol.py`: actual C helpers tested with a mock transport, using Python, Git and GCC on a build host.
- `build-evidence.json`: matching kernel config, exports, vermagic and twelve external layouts; prepared image hashes. Firmware and modules are not included in this repository.
- `TEST_PLAN.md` and `run_diagnostic.py`: bounded, attended first hardware test; defaults to plan only and verifies the loaded driver before changing controls.

`charge_behaviour` readback records the last acknowledged request only. Validate physical enable/current and firmware logs; do not infer success from that attribute. The diagnostic rejects stop while native percentage limiting is enabled. Other models retain their original descriptors and behavior.

No protection, voltage, raw-register or installed-image changes are included. Testing this new image requires approval. Do not treat the prepared image as ready for default installation.

The [first hardware result](../../evidence/charge-rate-first-test-20261110.json) kept physical charger-enable clear throughout the ten-second reconnect without another stop command. This does not validate long holds, sleep or an automatic percentage policy. The firmware reports Discharging during this stop; status presentation remains unresolved.
