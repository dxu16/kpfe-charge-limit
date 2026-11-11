# Historical OEM bypass design

RFC2 and RFC3 used OEM bypass (property `0x1d`). The firmware could re-enable charging after attachment while bypass was still active. The recovery sequence passed awake tests but failed during `s2idle` attachment. The final driver uses the firmware charge-rate command (`0x06`). [Current design](../experimental/charge-rate-policy/README.md) · [Why bypass failed](RECONNECTION_INVESTIGATION.md)

The RFC2 patch changed one file, `drivers/power/supply/qcom_battmgr.c`, with 409 additions and one deletion. It included the bounded reconnection recovery tested on one KPFE. RFC3 increased the frequency of hold checks.

Activation requires both the SM8550-class protocol variant and exact root compatible `konkr,pocket-fit-elite`. SM8750 uses that protocol fallback; matching the processor alone is insufficient. Odin 3 and other models retain the existing backend/status path in the same compiled kernel. Cross-model runtime testing remains desirable.

## Control

Retain existing firmware start/end preferences and sysfs setters. For KPFE, send the native command with enable=0. A serialized kernel worker reads live capacity, USB online, health and OEM bypass state. It inhibits at/above end, resumes at/below start, and retains the current state in between. Raising a target permits charging toward the new target. End=100 disables the host percentage limit. Invalid readings and firmware errors propagate/retry; an attached health fault must not cause a forced bypass release.

Property 29 is written only when desired state differs from readback, then read back for confirmation. The worker is driven by existing battery/USB GLINK notifications. A 60-second ordinary delayed retry runs while attached with an active partial limit or on error. It is not a wake-capable timer and must not be relied on to wake a suspended device.

## s2idle

Use `system_wq` with a soft wake hold rather than a freezable worker requiring a hard full-system wake. Existing NO_SUSPEND GLINK delivery allows the kernel to handle the notification while user processes remain frozen, then return to idle. The tested trace shows a successful inhibit request during the machine-suspend interval, before manual resume. No controller `pm_system_wakeup`, RTC alarm, or userspace re-suspend loop is used. Deep sleep and suspend-entry races have not been validated.

## Status and lifecycle

Fresh reads of raw status, health, native enable, OEM online, SOC, current and USB online prevent the stale native-enable cache seen in an earlier iteration. Only a confirmed, healthy, native-disabled, near-zero-current (+/-50 mA) hold may become Full at/above target, or Not charging in the hysteresis band. Unknown status, real charging/drain, faults and errors remain visible. This threshold is a tested heuristic, not an analog proof of zero battery current.

GLINK restart clears readiness and schedules reinitialization. Removal/shutdown synchronously disables policy/enable work, preventing late requeues. Healthy bypass is released on shutdown; native percentage limiting stays disabled. Consequently **there is no powered-off percentage limit**. Returning to the stock driver requires reapplying a native threshold to re-enable its persisted control; the test restoration did that while unplugged.

## Reconnection verification

A bypass flag readback is not proof that charging stopped. After five seconds of gauge settling, positive current above 50 mA permits one OEM release/normal-current acknowledgement/re-enter sequence per hold. The acknowledgement has a two-second software deadline in addition to request timeouts. Stop is attempted even after acknowledgement/read errors. A persistent failure remains visible without repeating the release sequence. Offline observation or normal charging resets the recovery budget.
