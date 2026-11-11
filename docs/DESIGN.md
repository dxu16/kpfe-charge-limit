# Historical OEM bypass design

This document describes the RFC2 and RFC3 approach. See the [automatic charge-rate candidate](../experimental/charge-rate-policy/README.md) for the current patch.

One `drivers/power/supply/qcom_battmgr.c` change, 409 additions and one deletion. This includes the bounded reconnection correction verified on the same handheld. No daemon, new sysfs ABI, device-tree edit or shared processor configuration change is required.

Activation requires both the SM8550-class protocol variant and exact root compatible `konkr,pocket-fit-elite`. SM8750 uses that protocol fallback; matching the processor alone is insufficient. Odin 3 and other models retain the existing backend/status path in the same compiled kernel. Cross-model runtime testing remains desirable.

## Control

Retain existing firmware start/end preferences and sysfs setters. For KPFE, send the native command with enable=0. A serialized kernel worker reads live capacity, USB online, health and OEM bypass state. It inhibits at/above end, resumes at/below start, and retains the current state in between. Raising a target permits charging toward the new target. End=100 disables the host percentage limit. Invalid readings and firmware errors propagate/retry; an attached health fault must not cause a forced bypass release.

Property 29 is written only when desired state differs from readback, then read back for confirmation. The worker is driven by existing battery/USB GLINK notifications. A 60-second ordinary delayed retry runs while attached with an active partial limit or on error. It is not a wake-capable timer and must not be relied on to wake a suspended device.

## s2idle

Use `system_wq` with a soft wake hold rather than a freezable worker requiring a hard full-system wake. Existing NO_SUSPEND GLINK delivery allows the kernel to handle the notification while user processes remain frozen, then return to idle. The tested trace shows a successful inhibit request during the machine-suspend interval, before manual resume. No controller `pm_system_wakeup`, RTC alarm, or userspace re-suspend loop is used. Deep sleep and suspend-entry races have not been validated.

## Status and lifecycle

Fresh reads of raw status, health, native enable, OEM online, SOC, current and USB online prevent the stale native-enable cache seen in an earlier iteration. Only a confirmed, healthy, native-disabled, near-zero-current (+/-50 mA) hold may become Full at/above target, or Not charging in the hysteresis band. Unknown status, real charging/drain, faults and errors remain visible. This threshold is a tested heuristic, not an analog proof of zero battery current.

GLINK restart clears readiness and schedules reinitialization. Removal/shutdown synchronously disables policy/enable work, preventing late requeues. Healthy bypass is released on shutdown; native percentage limiting stays disabled. Consequently **there is no powered-off percentage limit**. Returning to the stock driver requires reapplying a native threshold to re-enable its persisted control; the test restoration did that while unplugged.

## Why retain these lines

The policy helper alone would omit live readback, hysteresis, fault handling, s2idle notification processing, truthful status and teardown. Those parts were kept to address observed failures and lifecycle needs. Removing them solely to shorten the patch would discard tested behavior. Integration in Armada adds only the patch, its series entry and provenance. Further source changes should receive focused review and renewed tests.

## Reconnection verification

A bypass flag readback is not proof that charging stopped. After five seconds of gauge settling, positive current above 50 mA permits one OEM release/normal-current acknowledgement/re-enter sequence per hold. The acknowledgement has a two-second software deadline in addition to request timeouts. Stop is attempted even after acknowledgement/read errors. A persistent failure remains visible without repeating the release sequence. Offline observation or normal charging resets the recovery budget.
