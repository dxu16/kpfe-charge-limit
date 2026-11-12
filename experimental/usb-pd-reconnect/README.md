# KPFE USB-PD reconnect trial

`pd-reconnect.patch` shows the Linux driver changes relative to the [base charge-limit patch](../charge-rate-policy/README.md). The [Armada submission](../../submission/README.md) incorporates both in `0905`. The exact tested source is `qcom_battmgr.c`. See the [USB-PD investigation](../../docs/USB_PD_INVESTIGATION.md) for the stock comparison and firmware findings.

The follow-up runs automatically on KPFE when included in a build. It makes one attempt after a new awake attachment with battery charging already held, a 5 V contract, Good battery health, and USB-PD detected. A known 5 V-only source is skipped. If UCSI identifies PD but cannot report the advertised voltage, the driver can try once and time out. Attachments observed during `s2idle` are skipped.

The driver briefly sends rate 100 and reapplies rate zero after two consecutive USB readings at or above 8 V, cable removal, or the 2.5-second polling deadline. Firmware I/O timeouts can extend the time needed to confirm the stop. The driver retries a failed stop while the service is available. After a failed release it requires two successful replies, since one could be a late reply to the release. A rate request error also prevents further negotiation attempts during that firmware service lifetime.

## Validation

| Test | Result |
| --- | --- |
| Awake reconnect and hold | The installed driver charged from 82% to the 85% cap. After reconnection, USB reached 9 V with a 0.75-second charger-enable window. Charging stayed stopped across 2,316 samples over ten minutes, with battery health Good and a 4.38 V ceiling. [Enable events](../../evidence/usb-pd-20261112/installed-enable-events.jsonl) · [Installed hold](../../evidence/usb-pd-20261112/installed-hold-summary-r2.json) |
| 5 V / 2 A non-PD source | On the RAM image, the source stayed at 5 V and charger-enable stayed clear after a reconnect above the temporary cap. [RAM excerpts](../../evidence/usb-pd-20261112/ram-reconnect-excerpts.jsonl) |
| Suspend | Attachment during `s2idle` gave 5 V and charger-enable clear on the first reading after wake. Register sampling paused during sleep. When suspend was requested during negotiation, firmware acknowledged the stop 13 ms before `s2idle` entry. [Kernel events](../../evidence/usb-pd-20261112/kernel-r2.log) |
| Cable removal | Unplugging during negotiation ended the window after about 0.50 seconds. Firmware acknowledged the stop and USB went offline. [Kernel events](../../evidence/usb-pd-20261112/kernel-r2.log) |
| Normal charging | Charging resumed below the temporary resume threshold and with the cap disabled. Restoring the cap stopped it both times. [Samples](../../evidence/usb-pd-20261112/normal-r2.jsonl) |
| Timeout and reply failures | The 5 V-only PD case with unavailable source profiles, known 5 V-only PD gating, and missing or late firmware replies passed in simulation. The earlier revision failed the late-reply regression. |

Linux 7.2.6 configuration, exported symbols, version magic and type layouts passed the [ABI audit](../../evidence/usb-pd-20261112/abi-audit.json). The [temporary boot report](../../evidence/usb-pd-20261112/temporary-boot-report.json) records the one changed initramfs entry. Checkpatch reported zero errors and two formatting warnings. The [installed image](../../evidence/usb-pd-20261112/installed-boot-r2.json) booted the same module, kept 85% stop and 70% resume, and retained the same-base updater. It was kept as the default on the test device with the previous working deployment and stock pinned.

The real 5 V-only USB-PD timeout remains unverified. The tested charger matrix supports a local trial. See [local installation](../../docs/LOCAL_INSTALLATION.md#build-a-matching-armada-image) and [offline testing](../../docs/TESTING.md#offline-tests).

To undo the local trial, follow the [stock Armada rollback instructions](../../docs/LOCAL_INSTALLATION.md#roll-back-to-stock-armada).
