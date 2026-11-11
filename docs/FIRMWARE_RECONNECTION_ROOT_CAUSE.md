# Firmware handling of unwanted charging after attachment

This report covers the firmware investigation that followed the RFC3 charger-attachment failure during `s2idle`. Its findings led to the current charge-rate candidate. [Current validation](VALIDATION.md)

## Findings

The firmware has separate owners of current and charger enable. OEM bypass requests a zero-current override. Its current-aggregator callback disables charging when that effective current becomes zero, but the ordinary charging-state policy can independently enable charging. The ordinary enable policy does not consult the OEM bypass field or effective FCC in the decoded function. Repeating a zero-current vote can skip the disable callback because the aggregator result is unchanged.

This is a concrete code-level mechanism capable of producing the observed contradiction: bypass selected, FCC register zero, charger-enable set, and approximately +0.29 A battery current. It is stronger evidence than the earlier generic configuration-cache hypothesis. The new bounded capture records this ordinary enable-policy decision during reconnection while the effective OEM current override remains zero, together with the physical enable transition. It does not instruction-trace the SPMI write or exclude additional enable writers. See the completed diagnostic below.

## Decoded paths

Addresses below refer only to ADSP SHA256 `03db3d3f68258b23c8026b02c2a77590cb29f4a0152abd95a8f454e3dd0aad3a`. Armada and the extracted Android ADSP images match. These are addresses and paraphrases, not vendor source symbols invented from disassembly.

| Path | Code evidence | Consequence |
| --- | --- | --- |
| OEM property 29 entry | `0x601bed9c..0x601bedf0`: save FCC, call bypass action, program FCC zero | Requested bypass and hardware enable are different state |
| Bypass action | Registered callback `0x6005ca10`: aggregator 1, OEM client, override zero | Uses the ordinary current-vote machinery |
| Current callback | Registered at `0x6004621c`; callback `0x60058f20` disables through `0x60178ea0` when current is zero and charger-mode field is zero | Zero current can stop charging by clearing enable, rather than relying on the numeric FCC code alone |
| Unchanged vote | `0x60073648..0x60073668` compares new result with cached result at aggregator offset `0x11c`; equal skips to `0x60073aac`, past callback dispatch | Repeating the effective zero vote need not clear an independently re-enabled charger |
| Ordinary enable policy | `battmngr_plat_scpqchg_qbg_r1_en_charger`, `0x6004c620`: states 2/3/5 enable; state 4 enables unless BHM stop conditions apply | This decision is independent of the OEM stop request in this decoded function |
| Initialization | `battmngr_plat_scpqchg_qbg_r1_stateinit_action`, call at `0x6004a950` | Initialization can reach the ordinary enable policy after configuration |
| Physical enable write | `0x60089bc0` -> `0x60178ea0` -> context callback `0x6017b0c0`; for the 0x2646 branch, writes mask 1 via `0x6003b170` | This is an actual charger-enable register operation, not merely reported status |
| Enable cache | `0x6004ccf4..0x6004ce4c`, cached value `0x602abaac` and valid flag `0x602abaad` | The enable policy maintains its own cache; the zero-current callback does not update these fields |

The callback's charger-mode condition matters: the firmware selects modes from hardware configuration. The observed PMIC subtype 0x56 alone does not establish every runtime context field. The current callback and enable-register branches must therefore be correlated with firmware runtime logs before declaring the exact executed sequence proven.

A possible failing ordering is:

1. Host bypass applies an effective zero-current vote and its callback clears enable.
2. Firmware initialization/state handling independently selects enable=true and writes it.
3. Bypass readback still returns the requested flag and FCC remains zero.
4. A repeated zero vote leaves the effective result unchanged, so the disable callback is skipped.

The successful release/re-enter comparison fits this mechanism: removing and re-applying the vote can make the effective result change, causing the disable callback to run again. This explains why that sequence can repair the state, but does not make it a fundamental fix.

## What the delayed current reading does not prove

Near-zero current immediately after attachment does not prove the charger stayed disabled for those first seconds. Earlier tests measured gauge settling after an actual hardware stop. A later positive reading could reflect an earlier enable write becoming visible through the gauge, a later firmware write, or both. The current samples alone cannot timestamp the enable transition.

FCC=0 also does not establish electrical zero current while enable remains set. The firmware contains several PMIC conversion tables, precharge settings and state machines. The captured approximately 0.29 A has not been tied to a verified PMIH0108 minimum-current or precharge rule. In particular, register 0x2650 is a precharge setting, not FCC; its numerical resemblance to the measured current is insufficient proof. No new physical-overcharge claim follows from this analysis.

## Fundamental correction

The firmware should preserve one invariant across initialization, cable changes and charger-state changes: an active charge-stop request must prevent every ordinary path from enabling charging. A coherent enable decision should combine the existing safety/state conditions with the persistent stop request (or effective zero-current result), and all writers should share or invalidate the same enable state. Re-applying an already active stop request should be able to reconcile hardware state without temporarily releasing the stop.

This describes the required behavior, not a ready firmware patch: vendor source and a runtime trace identifying the responsible writer are still missing. The correction must preserve thermal/protection decisions and legitimate recharge behavior.

For an Armada-only correction, first establish a supported firmware command that provides this persistent inhibit behavior. The reviewed OEM property handler supports FCC control, native percentage control and OEM bypass; it has not revealed an independent persistent inhibit that is proven to dominate the ordinary enable policy. A raw register clear would compete with that policy and is not a substitute for this investigation. Increasing polling or adding more release/re-enter cycles treats the consequence and remains incomplete during suspend.

## Decisive remaining evidence

Capture the existing firmware log messages for charging-state initialization, the enable decision (`ChargerState`/`SetChargerState`), current-aggregator result and OEM SET requests during one bounded attachment. Correlate the first contradictory hardware enable state with those messages. That distinguishes ordinary initialization from another firmware enable writer and distinguishes a delayed gauge reading from a delayed enable write. If existing log coverage cannot identify the writer, instruction-level firmware tracing or vendor instrumentation is needed; Linux request tracing alone cannot prove which internal branch ran.

No new driver was loaded, charging control changed or register written for this static investigation. The existing RFC remains blocked. See [suspended-attachment failure](../evidence/rfc3-suspended-attachment-20261110.json).

## Follow-up static findings

A second enable owner exists in the charger power-path state machine. Its `icm_mcp_pt_susp_exit` routine (`0x60195480`) calls wrapper `0x6003e190` at `0x60195644`. The main-charger driver initializer registers `0x601b1b20` at callback offset `0xcc` (`0x601af554`). That implementation clears register 0x2646 bit 0, reconfigures the path, then unconditionally sets the same bit at `0x601b1bc4`. Neither the leaf function nor the decoded exit routine consults the OEM bypass flag or FCC before that enable write. This is an additional candidate writer, not evidence it executed during the failed attachment. The firmware's internal `susp` charger state must not be equated with Linux s2idle.

The old reconnection firmware capture already records firmware state 3, charger status 4, `EnableChargeLimit=0`, battery current +294198 uA in its normalized charging-current log, and effective current aggregator 1 result zero with OEM client 9 active. It starts after the transition, so it corroborates the disagreement but cannot timestamp its origin. Raw gauge log current uses the opposite sign; the normalized `POWER_SUPPLY_CURRENT_NOW` message is positive in this capture.

The independent `icm_pre_chg_init` path can also enable charging, but its firmware text identifies it as battery UV/OC protection recovery. Its presence in the image does not show that recovery was active in our tests. No generic precharge/minimum-current explanation has been promoted to a finding.

The stock Linux logger polls firmware opcode 0x18 for up to 8192 bytes once per response plus one second. It neither configures verbosity nor changes charging. Firmware timestamps are preserved as raw values; their conversion to Linux boot time has not been established. Linux trace delivery time may lag the original firmware event. Absence of a log message or zero Linux trace overruns does not prove the firmware log was complete.

The separate logging setter, owner 0x800a/opcode 0x19 at `0x600a8894`, accepts a category mask at offset 0x10 and verbosity at 0x18. It calls `battmngr_platform_set_logging_level_to_sdam` (`0x60041a70`) and `battmngr_platform_set_logging_categories_to_sdam` (`0x60041b60`). It is therefore excluded from the proposed passive capture: reboot alone cannot be assumed to restore persistent logging settings. No such command has been sent.

### Prepared bounded diagnostic

The existing manual-bypass RAM image is unchanged, SHA256 `abd8cba40045a6a65a4adddbfce82937465b1372939a8da1b09713f19a7a6516`. The new [passive collector](../tools/capture-firmware-cause.py) starts before attachment and records transmitted property/threshold requests, existing firmware logs, and five already audited charger status/configuration registers. It streams trace output to prevent the earlier late snapshot from losing the transition, and saves per-CPU trace statistics. Plan mode and syntax were checked locally; the authorized run is recorded below.

If approved, temporarily boot that image, load the existing firmware log reader, establish manual bypass with native limiting disabled at 100% (initial normal charging bounded to 15 seconds), and capture one unplug/reconnect. Stop the abnormal-state observation within 20 seconds and unplug; do not run a release/re-enter recovery experiment in this capture. Return to stock and native 85%/70% unplugged. No installed-image, raw-register, voltage/protection or persistent logging changes are included. This is an awake attachment diagnostic, not another suspend or ten-minute hold test. The user must approve loading system components before execution.

## Completed diagnostic: attachment enable decision captured

The approved unchanged manual RAM image reproduced the contradiction in one awake reconnection. The user unplugged after the short observation; measured USB-online time was 14.93 seconds, below the 20-second observation bound. Stock was then rebooted and native 85%/70% restored. Original boot/module hashes match, health is Good, and the logger and temporary probes are absent.

| Observation | Result |
| --- | --- |
| Before detach | OEM bypass active, physical enable 0, FCC code 0, near-zero current |
| First connected sample, boot 322.14 s | Physical enable 1, FCC code 0, reported current -65919 uA |
| Firmware decision delivered at boot 324.033357 s | `en_charger` requests enable 1; previous cached enable 0 |
| Firmware effective current immediately before that decision | Aggregator 1 result 0; active override client 9 |
| First positive reading, boot 326.02 s | +289925 uA, 3.88 seconds after the first enabled sample |
| Connected interval | All 57 samples have enable 1/FCC code 0; peak current +295419 uA |
| Host requests during capture | Native disable/target100 once; OEM SET29=0 once; no SET29=1 release |
| Safety and trace checks | Good health, ceiling 4380000 uV, no Linux trace overruns or dropped events |

The firmware log labels are easy to misread: at `0x6004cd6c..0x6004cd80`, the first printed value (`ChargerState`) is the newly desired enable value and the second (`SetChargerState`) is the previous cached value. Thus `ChargerState = 1, SetChargerState = 0` is a decision to enable from a cached disabled state. The actual hardware setter follows at `0x6004cdfc`. Firmware messages are buffered, so the Linux delivery timestamp is later than the underlying decision; it is not the exact hardware write time.

The reconnection log also reports firmware battery state 2 and the ICM `scp_inov` subsystem with `fcc1_ma=0,fcc2_ma=0`. The ordinary enable decision is now directly observed, rather than merely a possible static path. The other ICM writer remains an audited additional risk, not a proven necessary cause in this run.

This closes the delayed-reading question for this reproduction: enable was already set while the gauge still reported near-zero current. The later positive report was not accompanied by a new 0->1 enable transition. It does not establish the exact electrical current between gauge updates or explain the approximately 0.29 A floor.

The root correction should preserve the active inhibit across detach/attach and make it dominate normal enable decisions. It must also reconcile the independent enable cache and preserve legitimate resume when bypass is released. Adding a single bypass check without handling cache and other enable writers is not yet a complete firmware patch. No new polling revision or binary firmware patch was made.

See [structured evidence](../evidence/firmware-reconnect-cause-20261110.json) and the [selected sequence](../evidence/selected/firmware-cause-sequence-20261110.txt). Raw capture hashes are recorded in the evidence; proprietary binaries and full disassembly remain outside this repository.
