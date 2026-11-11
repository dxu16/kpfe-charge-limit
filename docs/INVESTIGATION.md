# Findings and confidence

## What reproduced

Native charge limiting reproduced a delayed `Good` to `Over voltage` health transition after reaching the selected percentage. Connecting while already above the threshold did not demonstrate the same failure in the observed sessions; that does not validate every reconnect path.

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

## OEM Android lead

Static analysis of the stock AYAWindow APK identifies percentage policy driven by `BATTERY_CHANGED`. The device implementation writes `0` to battery `online` for bypass and `1` to release it. The stock driver maps that property to battery firmware property 29 (0x1d), separate from native threshold opcode 0x48 and native enable property 24.

Firmware property 29 enters a separate bypass/current-vote path. Static analysis and the bounded mechanism test identify current aggregator 1's bypass override; this is not equivalent to merely writing the exposed current limit to zero. Repeated enter writes can overwrite saved state, motivating idempotent writes and readback. The app's >=95% exception and low-battery behavior are vendor policy, not copied wholesale into this candidate. Static code does not prove a full Android runtime test or all sleep behavior.

## What the candidate fixes

The Linux change integrates the OEM mechanism with Armada's existing threshold interface on this exact model. It avoids the problematic native percentage-limiter path without changing firmware, voltage targets or protection configuration. A firmware change would still be required to repair the native BHM implementation itself.

The label correction matters: 4100 mAh rated / 4200 mAh nominal cells make the reported 8400 mAh design value plausible in the vendor's single-cell-equivalent convention. Elevated learned capacities remain unexplained, including on Android. They are not established as the cause.

See [selected evidence](../evidence/README.md). Historical reports contain earlier uncertainties; the protection capture and final report supersede those specific statements. Captured readings do not establish physical overcharging, and do not exclude fast analog transients.
