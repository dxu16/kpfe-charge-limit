# Findings and confidence

## What reproduced

Native charge limiting reproduced a delayed `Good` to `Over voltage` health transition after reaching the selected percentage. Earlier above-threshold attachment sessions did not reproduce the fault. A later stock test reproduced it about 61 seconds after attaching at exactly 84% with an 84% cap. [USB-PD comparison](USB_PD_INVESTIGATION.md#measurements-on-one-kpfe)

The strongest synchronized protection capture selected 92% at 91%:

| Time after selection | Observation |
| --- | --- |
| 73.8 s | First Full sample at 92% |
| 226.8 s | PMIC configured/readback FV code changed from 156 to 130; reported ceiling 4,251,000 uV, gauge 4,246,437 uV |
| 229.2 s | Reported discharge exceeded 100 mA |
| 235.4 s | First Over voltage sample; original threshold immediately restored |

Code 130 represents 4250 mV in the verified active normalized 5 mV-step path. Configured and readback codes agreed throughout. The reported target was only a few mV above the contemporaneous gauge reading. This is not an independent measurement of comparator margin, total pack voltage, or individual cell voltages.

## Firmware localization

Disassembly identifies a delayed BHM branch that tracks the lowest observed integer-mV VBATT. When a later reading stops falling, it votes `VBATT + 5 mV` into the float-voltage aggregator. A captured sequence ending in 4250, 4250 produced a 4255 mV vote and preceded the fault. Subsequent decoded runtime evidence identifies battery-OV state-machine event 512. The firmware latches health after that event, explaining why unplugging restores the voltage ceiling but does not necessarily clear health.

The protection capture did **not** sample the expected OV status bit set; a different undecoded bit was observed. A short event could be missed or cleared by firmware. Exact comparator conditions, interrupt mapping on this PMIC revision, sensing differences, transient behavior and ordering remain unresolved. Quantization contributed 1 mV in the 4251 mV run but cannot explain the exactly representable 4255 mV case by itself. No arbitrary margin change, protection masking or latch-clearing patch is justified by these captures.

## Why OEM bypass was dropped

Static analysis of the stock AYAWindow APK identifies percentage policy driven by `BATTERY_CHANGED`. The device implementation writes `0` to battery `online` for bypass and `1` to release it. The stock driver maps that property to battery firmware property 29 (0x1d), separate from native threshold opcode 0x48 and native enable property 24.

Property 29 requests a zero-current override. On Armada, reconnecting the charger could set the charger-enable bit while that override and the fast-charge current setting both stayed at zero. The gauge subsequently reported about +0.29 A. Releasing and re-entering bypass recovered the hold in awake tests, but RFC3 still failed when the charger was attached during `s2idle`. The Android analysis establishes which interface the app calls. Its behavior on Android hardware was not tested. [Reconnection results](RECONNECTION_INVESTIGATION.md)

## What the charge-limit patch does

The KPFE driver keeps Steam’s existing thresholds and evaluates them on battery and USB notifications. It disables native percentage enforcement and uses firmware command `0x06`. Rate 0 selects a stop condition in the firmware state machine, and rate 100 lets normal charging resume. The patch avoids the native float-voltage reduction path and the OEM zero-current override. It leaves the firmware and protection settings intact. [Charge-rate interface](CHARGE_RATE_INTERFACE_AUDIT.md) · [Hardware validation](VALIDATION.md)

On a fresh attachment with rate zero already active, USB can stay at 5 V. The separate local trial briefly allows the firmware to negotiate higher input voltage and reapplies the stop. [USB-PD investigation](USB_PD_INVESTIGATION.md)

The label correction matters: 4100 mAh rated / 4200 mAh nominal cells make the reported 8400 mAh design value plausible in the vendor's single-cell-equivalent convention. Elevated learned capacities remain unexplained, including on Android. They are not established as the cause.

See [selected evidence](../evidence/README.md). Historical reports contain earlier uncertainties; the protection capture and final report supersede those specific statements. Captured readings do not establish physical overcharging, and do not exclude fast analog transients.
