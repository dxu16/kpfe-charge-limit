# Late current verification experiment

The installed candidate first reported near-zero current and then approximately +0.29 A. Its worker can return to a 60-second cadence after a near-zero check. This experiment uses five-second verification while inhibition is selected; ordinary charging keeps the existing cadence and unplugged policy stops periodic work. The change is one line and introduces no new interface or wake source.

The new actual-worker regression models a gauge that first reports near-zero and becomes positive after the first check. This is a timing counterexample, not proof of the untraced installed worker schedule. Hardware validation and a new build are required before any installation. The prior candidate remains canonical for reproducibility, with its failed hold documented.
