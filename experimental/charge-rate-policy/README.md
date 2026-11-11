# KPFE automatic charge-rate fix

This is the driver used in the final Armada submission and the tested local installation. It uses firmware command `0x06` after OEM bypass proved unreliable on charger attachment. The zero-rate stop condition is handled by the firmware state machine. Apply `charge-rate-policy.patch` to `src/base` to reconstruct the tested source. [OEM bypass failure](../../docs/RECONNECTION_INVESTIGATION.md) · [Installed validation](../../docs/VALIDATION.md)

The driver matches the KPFE device-tree compatible and keeps the existing start and end threshold controls. It disables native percentage enforcement while retaining the threshold values in firmware. Battery and USB notifications trigger a fresh policy decision. At or above the upper threshold it selects rate 0 to stop charging. At or below the lower threshold it selects rate 100 to allow charging. Between thresholds it retains the previous decision, including across cable removal. A 100% end threshold allows normal charging. The driver is designed to read the thresholds and reapply the decision after a battery-service restart. That recovery path remains unverified on hardware.

The driver reports a hold only when the current service acknowledged the stop, USB is online, health is Good, and live current is close to zero. A successful acknowledgement alone does not establish physical charger state.

The module built with the stock 7.2.6 kernel configuration. Its vermagic, exported symbol availability and twelve external type layouts matched stock. Checkpatch reported zero errors and warnings with the file-path notice ignored. The temporary image replaces only the driver inside the initramfs. The stock kernel, device tree and boot arguments match the original image.

## First hardware test

1. RAM-boot the candidate and verify its loaded build ID note. Confirm the existing 85%/70% thresholds and Good health.
2. On the usual charger, capture physical enable, current and the firmware requests. Check that an upper limit below the current capacity holds charging. Raise the limit and check that rate 100 restores charging. Keep the test target at or below 95%.
3. Set the limit one point above the current capacity and suspend to `s2idle` while charging. Use a manual wake after five minutes. The trace must show rate 0 before the kernel exits `machine_suspend`. Check physical charger-enable and current as soon as sampling resumes. If capacity did not reach the threshold in the interval, the sleep crossing result is inconclusive.
4. Unplug, reboot normally to stock, restore 85%/70%, and verify the original boot and module hashes. Save the capture locally.

The first test verified physical stop, resume and stop while awake. At the 88% target during `s2idle`, the driver sent rate 0 about 196 seconds before the kernel left `machine_suspend`. The first sample after wake showed charger-enable clear and battery status Full. Register sampling paused during suspend. [First hardware test evidence](../../evidence/charge-rate-policy-first-test-20261110.json)

The follow-up verified awake reconnection above the limit, a ten-minute hold, and a fixed 86%/87% discharge and recharge cycle. After discharging to 86% unplugged, reconnecting sent one rate 100 request. At 87% the driver sent one rate 0 request and Steam displayed the full check mark. [Follow-up evidence](../../evidence/charge-rate-policy-followup-20261110.json)

After charger attachment during `s2idle`, the automatic driver kept the charger disabled across all 56 post-wake samples without another rate command. The capture cannot resolve a brief enable pulse while register sampling was suspended.

Battery service restart recovery remains unverified. Firmware rejected the targeted charger-domain restart as disabled. One approved ADSP stop/start made the handheld unresponsive. A power cycle restored stock at 85%/70% with Good health and the original hashes. [Final test evidence](../../evidence/charge-rate-policy-final-tests-20261110.json)
