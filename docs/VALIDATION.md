# Validation and release gaps

The current charge-rate candidate was tested on one KPFE using temporary boots. Its exact source and image hashes, kernel compatibility audit, and patch are in the [candidate folder](../experimental/charge-rate-policy/README.md).

| Check | Result |
| --- | --- |
| Awake stop and resume | Changing the upper threshold stopped, resumed, and stopped charging again. [First test](../evidence/charge-rate-policy-first-test-20261110.json) |
| Above-limit awake reconnect and hold | Charger-enable stayed clear through reconnection and 2,271 samples over ten minutes. Health stayed Good and the reported voltage ceiling held at 4.38 V. [Follow-up](../evidence/charge-rate-policy-followup-20261110.json) |
| Fixed lower and upper thresholds | The battery discharged to 86% unplugged. Reconnecting resumed charging and it stopped at 87% without a settings change. Steam showed the full check mark. [Follow-up](../evidence/charge-rate-policy-followup-20261110.json) |
| Reaching the limit in `s2idle` | The driver sent rate 0 at the 88% target 196 seconds before the kernel left `machine_suspend`. Charger-enable was clear on the first read after wake. [First test](../evidence/charge-rate-policy-first-test-20261110.json) |
| Charger attachment in `s2idle` | At 88% with an 85% limit, charger-enable was clear on the first read after wake and through all 56 samples. The host sent no new rate command. Register sampling paused during sleep, leaving brief transitions unmeasured. [Final checks](../evidence/charge-rate-policy-final-tests-20261110.json) |
| Battery-service restart | Unverified. Firmware rejected the targeted restart with `QMI_ERR_DISABLED`. A single approved ADSP stop/start made the device unresponsive. The logs leave the failure point unknown. [Final checks](../evidence/charge-rate-policy-final-tests-20261110.json) |

After the temporary boots, stock Armada booted with matching original hashes, Good health, and native 85%/70% settings. The same tested module and initramfs were then installed in a local image derived from the exact stock release. A normal reboot loaded the expected driver. With the usual charger attached, all 121 samples over ten minutes showed charger-enable clear, Good health and the unchanged 4.38 V ceiling. The local image was kept as default with stock pinned for rollback. [Installed build and hold](../evidence/charge-rate-local-image-20261110.json)

The charge-rate patch was submitted for review in [Armada PR #881](https://github.com/armada-os/armada/pull/881). Remaining release checks include service recovery, reaching the lower threshold while continuously plugged in, and the full Armada source build.

## Historical OEM bypass tests

RFC3 passed its installed awake hold and threshold crossing during `s2idle`. It failed charger attachment while already suspended and was rolled back. This failure prompted the switch from OEM bypass to the charge-rate command. [RFC3 failure](../evidence/rfc3-suspended-attachment-20261110.json) · [Firmware analysis](FIRMWARE_RECONNECTION_ROOT_CAUSE.md)

RFC3's installed awake hold had 121 healthy Full samples over ten minutes, current -8545..0 uA and an unchanged 4380000 uV ceiling. The sleep-crossing inhibit completed 321.431 seconds before full resume. In the suspended-attachment failure, the initial inhibit and early negative current replies were followed by a 320.598-second worker gap; first resume current was +291146 uA. Physical current was not sampled continuously in suspend. No Over voltage flag occurred in that case.

The historical validation below covers the unchanged policy and RFC2 recovery sequence. It does not override the RFC3 failure.

### RFC2 recovery tests

- Exact runtime configuration, vermagic, imported exports and 14 external type layouts matched. Source and tested binary identities are recorded in `upstream/BASELINE.json`.
- Actual C policy (523,584 cases), status getters and fault-injected recovery helpers/worker passed. Final combined patch passed `checkpatch.pl --no-tree --no-signoff` with zero errors/warnings. This RFC has no fabricated author identity or sign-off.
- Awake above-limit ten-minute hold: 121 samples, Good health, unchanged 4380000 uV ceiling, current -9155..+1220 uA.
- Reconnection recovery: the fault reproduced with enable=1, fast-current setting=0 and up to +296029 uA reported current. Transmitted commands verified the driver's SET 1 -> SET 0 recovery in 50.763 ms. Hardware disable was observed 5.118 seconds after attachment; the resulting hold had near-zero current. Expanded tracing also recorded recovery-helper readbacks on two earlier attachments.
- Sleep: charged from 91% to the 92% limit during s2idle, remaining suspended until manual wake (295.629 seconds). A live trace read recorded the inhibit request 268.001 seconds before full resume. The post-resume ten-minute hold stayed Full/Good at the unchanged voltage ceiling, current -8545..0 uA, temperature 26 C. UPower reported Full.
- Real recharge: unplugged battery dropped from 92% to the temporary 91% start threshold. Reconnection resumed charging, followed by automatic stopping at 92% and a healthy two-minute hold. Original 85%/70% settings were restored.

The sleep trace's final per-CPU buffer overwrote part of the early history during the hold; the live-observed inhibit entry remains recorded in the result, but a saved pre-resume SET return is unavailable for this run. The runner now freezes/saves trace immediately after resume for future tests. Physical current was sampled after resume, not continuously during suspend. The earlier superseded candidate's sleep trace provides separate command-completion evidence for the unchanged stop path.

See the [awake hold](../evidence/revised-automatic-hold-20261110.json), [wire recovery](../evidence/revised-wire-recovery-20261110.json), [sleep](../evidence/revised-sleep-20261110.json), and [real recharge](../evidence/revised-real-recharge-20261110.json) records. Earlier failed reconnection evidence is historical, not a result of the revised recovery branch.

### Historical release checklist

| Gap | Needed evidence |
| --- | --- |
| Continuous-connected hysteresis | A held battery crosses the start threshold and resumes without detach; the unplug/reconnect check does not establish this |
| Cable/power matrix | Rapid cable changes, weak sources and power negotiation changes across all policy states |
| Lifecycle and races | GLINK restart, removal/shutdown, failed requests and suspend-entry/exit races on hardware |
| Sleep configurations | Other supported sleep modes; deep sleep remains untested |
| Other models | Confirm unchanged behavior on Odin 3 and other shared-kernel devices |
| Project build | Full `just check` and `just package kernel` in Armada's supported environment |
| Deployment | RFC2 failed its installed awake hold; RFC3 passed awake hold but failed suspended attachment; both were rolled back successfully |

These are single-device results. They do not establish physical overcharging in the original incident or broad release safety.

### Firmware-cause capture after rollback

An unchanged manual-bypass RAM image reproduced one awake reconnection with native limiting disabled. Firmware recorded an enable decision while effective current override remained zero. Hardware enable was already set at the first connected sample; positive current appeared 3.88 seconds later, peaking at +295419 uA. No host bypass-release command occurred. All 57 connected samples showed enable=1/FCC=0, health remained Good, and Linux trace loss counters were zero. Observation ended with unplug after 14.93 seconds of measured USB-online time; stock boot/module identities and native 85%/70% were restored. This capture documents the OEM bypass failure. The charge-rate results are listed above. See [evidence](../evidence/firmware-reconnect-cause-20261110.json).
