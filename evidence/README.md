# Evidence index

Selected from the original local `charge-investigation/` archive on 2026-11-10. Large binaries, firmware, APKs, full network/device inventories and obsolete candidate modules/images are deliberately excluded. No private keys, passwords, network addresses or device serials are needed for this review. `MANIFEST.sha256` records included file contents.

## Current charge-rate candidate

- Awake threshold changes and the pre-wake stop request during `s2idle`. [First automatic test](charge-rate-policy-first-test-20261110.json)
- Above-limit reconnect, ten-minute hold, fixed-threshold recharge, and the Steam check mark. [Automatic follow-up](charge-rate-policy-followup-20261110.json)
- Charger attachment during `s2idle`, the unsuccessful service restart attempts, and verified restoration to stock. [Final hardware checks](charge-rate-policy-final-tests-20261110.json)
- Verified local image build, normal boot, ten-minute installed hold, and official update offer. [Installed validation](charge-rate-local-image-20261110.json)
- Installed updater check, Steam refresh, and two-minute battery hold with the same driver. [Updater verification](charge-rate-updater-install-20261110.json)
- Firmware interface and manual hardware checks that preceded the automatic patch. [Interface audit](../docs/CHARGE_RATE_INTERFACE_AUDIT.md)

## Historical OEM bypass evidence

| File | Meaning |
| --- | --- |
| `final-hardware-results.txt` | Final narrative, source/module/image hashes, exact trace times, limitations and restoration |
| `final-hardware-summary.json` | Machine-readable final bounded test metrics |
| `selected/final-trace-excerpt.txt` | Filtered trace: suspend markers, property writes/returns and wake events; not the full trace |
| `module-abi-audit.json` | Original exact-config/vermagic/exports/type-layout audit |
| `policy-tests.txt`, `status-tests.txt` | Original successful C harness output |
| `stock-restoration.txt` | Original stock boot/module hashes, final uevent/control readback |
| `packaging-verification.txt` | Local packaging checks and distinction from prior hardware/C test results |
| `reconnection-followup-20261110.md` | Reproduced reconnection anomaly, observer corrections and stock restoration |
| `selected/protection-trigger-results.txt` | Synchronized PMIC/sysfs fault reproduction and measurement limits |
| `selected/native-firmware-events.txt`, `decoded-ov-event-sequence.txt` | Delayed native FV vote and decoded state-machine event |
| `selected/firmware-phase2-historical.txt` | Earlier disassembly report; read its follow-up note and newer protection report |
| `selected/android-oem-static-analysis.txt` | Decompiled-app -> stock driver -> property-29 chain; historical callback uncertainty subsequently narrowed |
| `selected/oem-bypass-vote-and-pmic.txt` | Focused callback/vote/PMIC disassembly |
| `selected/existing-background-battery-path.txt` | Existing Linux power-supply notification/work path reference |

The text reports retain historical chronology and references to original archive paths. Those paths are provenance references, not missing runtime dependencies. Final docs distinguish current conclusions from earlier uncertainty. Complete raw captures remain in the original workspace archive and have not been uploaded.

## Revised candidate, November 10

- [Automatic awake hold](revised-automatic-hold-20261110.json): 121 samples over ten minutes.
- [Expanded reconnection trace](revised-detailed-reconnect-20261110.json): recovery-helper readbacks on both attachments.
- [Transmitted recovery commands](revised-wire-recovery-20261110.json) and [selected trace](selected/revised-wire-recovery-excerpt.txt): compiler-inlined SET writes verified at `pmic_glink_send`; hardware enable clears.
- [Sleep result](revised-sleep-20261110.json): 91% to 92%, manual wake, ten-minute hold; includes the final-trace overrun limitation.

The earlier `final-hardware-results.txt` and packaging record describe the superseded 321-addition candidate; current source identities are in `upstream/BASELINE.json`.

- [Real recharge](revised-real-recharge-20261110.json): actual discharge to the temporary start threshold, reconnection, recharge and stop; continuous-connected hysteresis remains untested.

- [Stock restoration](revised-stock-restoration-20261110.json): original hashes, native controls and healthy unplugged state.
- [Local installation image](local-image-build-20261110.json): matching module/initramfs, successful lint, no staged deployment.

The OEM bypass investigation concluded with the [RFC3 suspended attachment failure](rfc3-suspended-attachment-20261110.json) and [static firmware enable-path anchors](firmware-enable-paths-20261110.json). The later charge-rate results are indexed above.

[Completed firmware-cause capture](firmware-reconnect-cause-20261110.json): ordinary firmware enable decision observed with zero OEM override; hardware enable precedes the delayed positive gauge report. Stock restored.

[Charge-rate interface audit](charge-rate-interface-audit-20261110.json): opcode 0x06 stop-state path and a separately compiled, hardware-untested diagnostic.
