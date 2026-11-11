# KPFE charge-limit investigation and Armada RFC

This repository investigates the KONKR Pocket FIT Elite (KPFE) charge-limit fault. The current candidate is a KPFE-only Armada driver patch that uses the existing firmware charge-rate command (`0x06`) for stop and resume. It keeps Steam's existing threshold interface and uses battery and USB notifications to apply the policy. [Current patch and design](experimental/charge-rate-policy/README.md)

The candidate passed an awake reconnect above the limit, a ten-minute hold, a fixed 86%/87% discharge and recharge cycle, and threshold crossing during `s2idle`. After attachment during `s2idle`, the charger was disabled at the first post-wake sample and through all 56 samples. The host sent no new stop request. Register sampling paused during sleep. [Validation and evidence](docs/VALIDATION.md)

The candidate is packaged locally for Armada review. Battery-service restart recovery remains unverified. Firmware rejected a charger-only restart, and one approved full ADSP stop/start left the device unresponsive. A power cycle restored stock Armada at 85%/70%, with Good health and matching original boot and driver hashes. [Final hardware checks](evidence/charge-rate-policy-final-tests-20261110.json)

The exact tested driver was subsequently installed in a local image derived from stock. It passed a normal reboot and ten-minute hold at 85%/70%. The standard local build includes an updater check that hides offers for the exact official base already installed. The battery-only image is the immediate rollback target on the test handheld, and stock remains pinned. [Installed battery validation](evidence/charge-rate-local-image-20261110.json) · [Updater verification](evidence/charge-rate-updater-install-20261110.json)

The original fault followed a delayed float-voltage reduction after the native limiter reached a partial target. The reported health changed to `Over voltage`. Physical overcharging remains unconfirmed. The candidate disables native percentage enforcement and uses the firmware's separate stop condition. RFC3 used OEM bypass, which left the charger-enable path free to turn charging back on after attachment. [Firmware investigation](docs/FIRMWARE_RECONNECTION_ROOT_CAUSE.md) · [Charge-rate audit](docs/CHARGE_RATE_INTERFACE_AUDIT.md)

## Start here

- [Investigation and confidence](docs/INVESTIGATION.md): observed fault, static-code evidence, unresolved protection trigger.
- [Current candidate](experimental/charge-rate-policy/README.md): KPFE gate, firmware stop/resume, threshold policy and build evidence.
- [Validation and remaining work](docs/VALIDATION.md): hardware results and review gaps.
- [Local installation guide](docs/LOCAL_INSTALLATION.md): source build, recovery, verification, and official updates.
- [Contribution review](docs/CONTRIBUTING_REVIEW.md): rules/conventions checked against pinned Armada sources.
- [Evidence index](evidence/README.md): selected captures, test output and provenance.
- [Armada submission](submission/README.md): integration diff, reviewable overlay, and PR description.

## Layout

| Path | Purpose |
| --- | --- |
| `experimental/charge-rate-policy/` | Current Linux patch and exact RAM-tested source, 381 additions / 6 deletions |
| `src/base/` | Exact stock driver source used as the patch base |
| `submission/` | Current Armada integration diff, overlay, and PR description |
| `patches/`, `src/patched/` | Historical RFC3 Linux patch and source |
| `tests/` | Patch reconstruction and artifact verification, plus historical C policy and status fixtures |
| `tools/` | Packaging/verification tools and historical diagnostic/build tools |
| `upstream/` | Selected public Armada source snapshots, not a full checkout |
| `evidence/` | Selected text evidence; no firmware, APKs, boot images or modules |

Armada hardware-test base: `dfed5d61e344c473c6e3c654f4090d7f618f3a5a`, Linux 7.2.6. The charge-rate source, boot image and compatibility audit are recorded in the [current build evidence](experimental/charge-rate-policy/build-evidence.json). The [base metadata](upstream/BASELINE.json) also records the historical RFC3 submission base.

## Offline checks

Python 3 and Git verify the manifest, reconstruct the current patch, and check the Armada integration diff.

```sh
python3 tests/verify_artifacts.py
```

The C fixtures `tests/test_policy.py` and `tests/test_status.py` cover the historical OEM bypass patch. See the [testing instructions](docs/TESTING.md) for the scope of the available tools.

## Licensing

The Linux source snapshots and modifications retain the source's `GPL-2.0-only` SPDX license. Armada snapshots retain their original license; see `upstream/LICENSE.md`. Original repository documentation and helper scripts are offered under GPL-2.0-or-later; see [LICENSE.md](LICENSE.md). Vendor binaries and decompiled application source are excluded. No personal author identity or legal sign-off has been invented.
