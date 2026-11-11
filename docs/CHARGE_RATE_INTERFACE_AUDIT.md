# Charge-rate command audit

Status: promising firmware-managed stop path; compiled diagnostic only. No device command was sent, and no new module or image was loaded in this investigation. The current stock driver and native 85%/70% controls remain in use. The canonical RFC is still blocked.

## Result

The KPFE firmware implements owner 0x800a/opcode 0x06, `BattMngrSetChargeRate`. Rate zero is treated as a stop condition in the state machine before normal charging-state selection. This differs from OEM property 29, whose zero-current vote was overridden by an attachment enable decision in the captured failure.

This is a candidate for a clean Armada integration using an existing firmware command. Its hardware behavior is not yet validated. In particular, it must stop battery charging while keeping the system supplied externally, survive attachment and sleep transitions, resume correctly, and hold Good health without the delayed voltage-ceiling reduction.

## Code chain in this exact firmware

ADSP SHA256: `03db3d3f68258b23c8026b02c2a77590cb29f4a0152abd95a8f454e3dd0aad3a`.

| Stage | Evidence |
| --- | --- |
| Request dispatch | Opcode 0x06 branch `0x600ab194`; reads rate at request offset 0x10 and calls `0x601be930` at `0x600ab204` |
| Accepted range | `0x601be940..0x601be960` rejects rates above 100 |
| Stored intent | `0x601be970` writes primary-context offset 0x2b4, then signals the battery thread with event 0x20 at `0x601be978` |
| Default | Primary initialization at `0x6001ef9c..0x6001efa0` sets this field to 100 |
| Stop decision | `0x60051f14..0x60051f80`: rate zero sets next state to 7 if current state is 0 or 7, otherwise 0, and sets bit 0 of the stop-condition flags |
| Priority | `0x60052024` stores the flags at context offset 0x548; caller `0x60050c00..0x60050cd0` skips ordinary charging-state selection while flags are nonzero |
| Enable consequence | Decoded `en_charger` starts desired enable at zero; states 0 and 7 do not take an enabling case. They leave input suspend unset in this function |
| Resume | Rate 100 removes this particular stop condition on the next successful check; ordinary state selection can resume. Manual resume and stop passed the first short hardware test; broader behavior remains unvalidated |
| Response | Firmware sends a 16-byte response: 12-byte header plus status at offset 0x0c |

Simplified ordering, preserving the distinction from a direct register write:

```text
SET_CHARGE_RATE(0) -> store requested rate -> wake firmware state machine
zero requested rate -> stop-condition flag -> non-charging state
non-charging state -> desired charger-enable false
```

The relevant normal charging/BHM state-change routine is bypassed while the stop-condition flag is set. With native percentage limiting disabled separately, this offers a route that does not request the native partial-limit/BHM stop. The sender does not alter float-voltage or protection settings, and the decoded setter has no direct nonvolatile-storage write.

No attachment reset of the primary rate field was found in the decoded path. This is static evidence, not a runtime persistence test. A firmware restart initializes it again, so a production Linux implementation would need service-restart handling. It would also need existing host percentage policy and sleep/notification handling; the diagnostic does not implement those.

## Packet and independent upstream reference

The proposed request is 24 bytes, little endian:

| Offset | Value |
| --- | --- |
| 0x00 | Owner 32778 (0x800a) |
| 0x04 | Request/response type 1 |
| 0x08 | Opcode 6 |
| 0x0c | Battery ID 0 |
| 0x10 | Charge rate: 0 stop / 100 normal |
| 0x14 | Charging path 0 |

The KPFE decoder uses the rate at 0x10; the reviewed branch does not consume the final charging-path word. The full request layout is independently described by Konrad Dybcio in his [October 21, 2026 kernel mailing-list reply](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2610.2/13151.html) about charge control on Kodiak phones. He suggests opcode 0x06 as a possible interface, not a tested KPFE solution. Our KPFE-specific conclusions come from this device's firmware code, not that suggestion.

## Other reviewed interfaces

- Battery property SET 0x31: current limit (10), native percentage enable/thresholds (24/25/26), OEM bypass (29). These are the previously investigated mechanisms.
- USB property SET 0x33: input-current, moisture-detection and adapter-voltage controls in the reviewed handler. No independent persistent battery-inhibit control was identified there.
- Wireless SET 0x35: boost control; not a wired battery-inhibit path.
- Debug 0x45/0x46: parameter getter/setter. The active getter is largely a stub; setters include configuration overrides. These have not been established as a production battery-inhibit ABI and are unnecessary for the charge-rate candidate.
- Operational-mode 0x03: selects factory/normal mode; not an appropriate replacement for ordinary charge control.
- Firmware logging SET 0x19: writes logging parameters to SDAM; excluded, as previously documented.

The extracted Android module exposes the known battery property setter and `charge_control_en` switch. The inspected OEM app uses property 29. Neither observation establishes Android use of opcode 0x06; this candidate is a different existing firmware interface.

## Prepared diagnostic

[Experimental source and patch](../experimental/charge-rate-stop/README.md) expose only manual stop/resume on exact `konkr,pocket-fit-elite`, with native percentage limiting required to be disabled before stop. There is no automatic percentage worker, OEM property-29 command, release/re-enter repair or recovery timer. Sysfs readback is explicitly the last acknowledged request, not proof that hardware stopped.

The separate 16-byte ACK is validated before completing the request. Offline tests compile the actual C helper and check 24-byte packets, native-policy exclusion, repeated stop requests, timeout/error handling and malformed replies. The module builds with the exact runtime kernel configuration, matching exports/vermagic and twelve external layouts. Checkpatch reports zero errors/warnings. The prepared RAM image changes only the driver module; it was RAM-booted for the short diagnostic, and stock was restored without persistent installation.

The approved [first hardware test](../evidence/charge-rate-first-test-20261110.json) passed manual stop/resume and one short awake reconnect. Across forty stable connected samples over ten seconds, physical charger-enable stayed clear without another stop or recovery request; health stayed Good and the voltage ceiling stayed 4.38 V. Current settled near zero with USB online, supporting continued external system power, although input power was not independently measured. The firmware reported Discharging during stop. Stock hashes and 85%/70% controls were verified after reboot.

The separate [ten-minute awake hold](../evidence/charge-rate-hold-20261110.json) recorded charger-enable clear and battery health Good across 2,272 samples. The reported voltage ceiling stayed at 4.38 V and battery current ranged from −8.5 to +3.1 mA. The host sent a single stop request before the hold.

In a [separate s2idle attachment test](../evidence/charge-rate-sleep-attach-20261110.json), the operator connected the charger while asleep and manually woke it about 30 seconds later. Firmware logged the attachment. The physical charger-enable bit was clear on the first read after wake and throughout 55 samples, with no additional charge-rate request after the original stop. Host register reads pause during suspend, so the capture cannot exclude a brief enable pulse during that interval.

The automatic driver subsequently sent rate 0 before wake at the upper threshold during `s2idle`, and Steam showed its full check mark after the awake recharge cycle. Charger-service restart recovery remains unverified. [Automatic policy validation](VALIDATION.md)
