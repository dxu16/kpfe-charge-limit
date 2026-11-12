# Reconnection investigation

Attaching a charger could re-enable charging while OEM bypass was selected and the fast-charge current setting was zero. Releasing and re-entering bypass recovered the hold while awake, but RFC3 failed charger attachment during `s2idle` and was rolled back. The base charge-limit patch uses firmware command `0x06`, whose zero rate selects a stop condition in the firmware state machine. The later USB-PD investigation covers the separate question of negotiating higher USB input voltage while using that stop condition. [Firmware analysis](FIRMWARE_RECONNECTION_ROOT_CAUSE.md) · [Validation](VALIDATION.md) · [USB-PD investigation](USB_PD_INVESTIGATION.md)

## Observed hardware states

| State | Fast-current register | Charger-enable bit | Reported battery current |
| --- | --- | --- | --- |
| Working manual bypass | 0 | 0 | Approximately -1..-7 mA |
| Same bypass after reconnection | 0 | 1 | Approximately +289..+297 mA |
| After isolated release/acknowledgement/re-enter | 0 | 0 | Approximately -1..-7 mA |

The native limiter was disabled throughout the isolated comparison, with its end threshold held at 100%. Recovery changed only OEM property 29. SET 1 and SET 0 were 52.570 ms apart; normal-current acknowledgement was checked before re-entry. This isolates the repair from the earlier comparison that also changed native thresholds. Health stayed Good and the reported voltage ceiling stayed 4380000 uV. See [isolated result](../evidence/isolated-bypass-rearm-20261110.json).

## Firmware explanation and confidence

Property 29 GET returns a stored configured-state field, not a measurement that the charger is disabled. Bypass entry saves current, applies a zero-current vote and writes the fast-current setting to zero. Charger enable is a separate control; bypass exit restores current and pulses disable/enable. Register captures established that attachment can leave enable=1 while the bypass vote and current setting remain zero. Reasserting an unchanged cached flag is therefore insufficient.

The firmware also caches desired charger configuration before deciding whether to program hardware. That offers a plausible explanation for attachment/state desynchronization, but the exact responsible branch remains an inference. The contradictory hardware state and the supported repair sequence are directly observed.

The PMIC identity is subtype 0x56, PMIH0108. Several driver tables coexist in the firmware; a generic 300 mA minimum inferred from another subtype is not established. The reported +0.29 A was corroborated by charger state and gauge/counter movement; it was not merely a Steam icon issue. These observations do not establish physical overcharging.

## Historical bypass recovery tests

The RFC2 driver allowed five seconds for gauge settling before comparing actual current with 50 mA. Persistent positive current permits one release/acknowledgement/re-enter attempt per hold. It attempts stop even after acknowledgement/read errors, surfaces persistent failure and avoids repeated release cycles. Offline observation or legitimate normal charging resets the budget. The earlier capture showed approximately 3.6 seconds of gauge lag after a successful hardware stop, supporting a settling interval.

The automatic test reproduced enable=1/FCC=0 with reported current peaking at +296029 uA. Direct tracing at `pmic_glink_send` captured SET 1 followed by SET 0 after 50.763 ms. Hardware disable was observed 5.118 seconds after attachment. The resulting hold had enable=0/FCC=0 and near-zero current. See [wire recovery](../evidence/revised-wire-recovery-20261110.json) and [selected requests](../evidence/selected/revised-wire-recovery-excerpt.txt).

The initial request-wrapper probe missed SET operations inlined by the compiler into the recovery helper. Its apparent absence of a recovery pair was a tracing limitation. Expanded compiler-clone readback probes showed helper execution on two attachments; transmitted-request tracing then verified the actual SET values independently of inlining. Loaded module build identity matched the audited module.

The read-only register observer accesses five audited configuration/status addresses: 0x2606, 0x2646, 0x2650, 0x2654 and 0x2658. It never writes registers or reads interrupt-clear registers. Root tracing is temporary and isolated from existing trace instances.

RFC2 also passed reaching the limit in `s2idle` and an unplug, discharge and recharge cycle. Its installed image later failed an awake hold when an early near-zero sample gave way to positive current. RFC3 checked more frequently and passed the installed awake hold, then failed suspended attachment. Both images were rolled back. [RFC2 installed hold failure](../evidence/installed-hold-failure-20261110.json) · [RFC3 suspended attachment failure](../evidence/rfc3-suspended-attachment-20261110.json)
