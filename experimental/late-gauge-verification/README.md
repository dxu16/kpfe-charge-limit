# Late current verification experiment

The installed RFC2 OEM bypass driver first reported near-zero current and then approximately +0.29 A. Its worker can return to a 60-second cadence after a near-zero check. This experiment uses five-second verification while inhibition is selected; ordinary charging keeps the existing cadence and unplugged policy stops periodic work. The change is one line and introduces no new interface or wake source.

The worker regression models a gauge reading that turns positive after the first check. The installed worker’s schedule was not traced in that failed hold. The faster check became RFC3, which passed an installed awake hold but failed charger attachment during `s2idle`. The final driver uses firmware command `0x06` and does not use this polling change. [RFC3 results](../../docs/VALIDATION.md#historical-oem-bypass-tests) · [Final design](../charge-rate-policy/README.md)
