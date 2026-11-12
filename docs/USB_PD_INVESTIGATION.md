# USB-PD voltage during a charge-limit hold

The [base charge-limit driver](../experimental/charge-rate-policy/README.md) keeps the battery charger stopped across a cable reconnect. On the tested KPFE, this can leave USB input at 5 V on a fresh attachment. The separate [USB-PD reconnect patch](../experimental/usb-pd-reconnect/README.md) briefly allows normal charging on an eligible awake attachment so the firmware can negotiate higher USB input voltage. It then reapplies the battery stop.

## Measurements on one KPFE

| Scenario | Result |
| --- | --- |
| Charge from 81% to an 85% cap with the base charge-limit patch | USB stayed at 9 V after the battery stopped. Reconnecting at the cap brought USB back at 5 V. [Capture](../evidence/usb-pd-20261112/kpfe-usb-voltage-comparison-20261112-080045.log) |
| Fresh attach at 84% battery with an 83% cap, same charger and cable | The base charge-limit driver stayed at 5 V. Stock Armada switched to 9 V by the next sample. Both settled near zero battery current and reported Good health in the short runs. [Base patch](../evidence/usb-pd-20261112/kpfe-usb-above-cap-patched-20261112-083510.log) · [Stock](../evidence/usb-pd-20261112/kpfe-usb-above-cap-stock-20261112-083906.log) |
| Stock fresh attach at 84% with an 84% cap | USB reached 9 V. About 61 seconds after attachment, the battery-side ceiling dropped from 4.38 V to 4.165 V and health changed to `Over voltage`. [Capture](../evidence/usb-pd-20261112/kpfe-usb-stock-reconnect-20261112-082955.log) |
| Performance-mode gameplay on 5 V | The battery supplied some of the load for about half a minute, peaking at 1.61 A of discharge. Displayed capacity stayed at 85%. [Capture](../evidence/usb-pd-20261112/kpfe-usb-5v-load-20261112-082113.log) |

The USB supply readings describe power at the USB port. The battery supply reports its own voltage and ceiling. The patched handheld held 9 V USB input while the battery charger was disabled.

## Why USB stays at 5 V

Earlier firmware traces with the same charger showed fixed 5 V and 9 V source profiles. With rate zero already active, the firmware selected 5 V and stayed in charger state 2 during the observed interval. In a lower-threshold reconnect, the driver sent rate 100, the firmware progressed through states 2, 3 and 5, and requested fixed 9 V at 3 A. These traces and the matched USB readings support the explanation that rate zero prevents the charging-state transition that leads to a higher-voltage request. The exact condition that connects the transition to the request remains unverified. [Charge-rate firmware audit](CHARGE_RATE_INTERFACE_AUDIT.md)

The reviewed UCSI dispatcher does not implement `SET_POWER_LEVEL`, and the battery-manager voltage setter paths inspected target PPS or UFCS. No verified Armada interface independently requests the fixed 9 V profile while retaining rate zero. Firmware could negotiate an input profile independently of the battery charger state, given a firmware change or a supported interface for that policy.

## Approaches tested

- The OEM bypass and standard `constant_charge_current=0` paths both showed charger-enable set after reconnection while their zero setting remained visible. The standard-current test stopped at the first enabled sample. It did not establish whether the charger would have negotiated 9 V or supplied sustained battery current. [OEM bypass results](RECONNECTION_INVESTIGATION.md) · [Standard-current capture](../evidence/usb-pd-20261112/kpfe-usb-current-handoff-reconnect-20261112.jsonl)
- Briefly changing the cap from 85% to 100% brought up 9 V in about 0.82 seconds on the usual charger. Restoring 85% stopped the charger again and retained 9 V for the rest of the short test. This confirmed that a temporary release could trigger the normal firmware negotiation. [Manual test](../evidence/usb-pd-20261112/kpfe-usb-manual-toggle-20261112.jsonl)
- The automatic follow-up uses the same firmware charge-rate command to release and stop, leaving the saved thresholds in place. It negotiated 9 V after a 0.75-second charger-enable window on the installed trial, followed by a healthy ten-minute hold. [Implementation and validation](../experimental/usb-pd-reconnect/README.md)
