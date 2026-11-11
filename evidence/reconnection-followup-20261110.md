# Reconnection follow-up, 2026-11-10

Result: **default installation deferred; reconnection validation failed.** The unchanged tested candidate was booted into RAM. No persistent deployment or boot image replacement was performed.

- Stock starting state: 94%, Good, 85% end / 70% start, Linux 7.2.6.
- First PC-to-charger handoff reading: Full, Good, -11597 uA, ceiling 4380000 uV.
- After unplug/reconnect: Charging, Good, approximately +289000 to +296000 uA despite current-limit setting 0 and SOC 94 above end 85.
- Firmware capture confirms native `EnableChargeLimit = 0`, target 85, and current aggregator 1 result 0 with bypass client 9 as the active override. Thus the native limiter was not accidentally re-enabled, and the firmware bypass vote was not simply absent.
- Firmware gauge FIFO also reports approximately -290 mA in its internal sign convention; the exported charging current is positive. The readings originate below Steam/the Linux status presentation.
- Reported charge counter increased from 9554471 to 9562553 uAh and voltage rose during the observed interval. These are gauge readings, not an independent electrical measurement. Health remained Good and ceiling remained 4380000 uV; physical overcharging was not established.

The new read-only observer had two setup errors: it initially lowercased values, causing a false health assertion, then rejected the deliberately above-limit starting SOC. Both were corrected. The alleged Over voltage alarm was false: its actual saved reading was Good. These aborted observer runs must not be reported as completed ten-minute holds. The subsequent manual readings and firmware capture independently reproduce the positive-current anomaly.

The charger was unplugged after capture. A normal reboot restored the original installed driver and removed the firmware logger. Original image/module hashes were verified; native 85/70 and 8400000 uA were reapplied while offline, with Good health. No full hysteresis cycle or persistent-image build/deployment was attempted after the anomaly.

Next investigation: establish how attachment/charger initialization interacts with the OEM bypass path and why an active zero-current override can coexist with these readings. The capture does not establish that toggling/reasserting the property is a correct fix. Avoid a speculative retry loop or masking Charging as Full.

Raw captures remain in the private local archive `charge-investigation/transition-validation-20261110/`. The local image context is preparation only. See [installation instructions](../docs/LOCAL_INSTALLATION.md).
