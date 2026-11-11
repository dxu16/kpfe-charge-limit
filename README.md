# KPFE charge-limit investigation and Armada RFC

This repository investigates the KONKR Pocket FIT Elite (KPFE) charge-limit fault. The current candidate is a KPFE-only Armada driver patch that uses the existing firmware charge-rate command (`0x06`) for stop and resume. It keeps Steam's existing threshold interface and uses battery and USB notifications to apply the policy. [Current patch and design](experimental/charge-rate-policy/README.md)

The original `Over voltage` fault followed a delayed drop in the firmware’s float-voltage target after reaching a partial charge limit. An earlier fix used OEM bypass (property `0x1d`), but the firmware could re-enable charging on attachment even with bypass selected. The final patch uses the charge-rate command’s separate firmware stop condition. [Original fault](docs/INVESTIGATION.md) · [Why OEM bypass failed](docs/RECONNECTION_INVESTIGATION.md)

On one KPFE, the patch passed awake reconnect, a ten-minute hold, recharge between fixed thresholds, and reaching the limit during `s2idle`. With the charger attached during `s2idle`, it was disabled on the first reading after wake. Register sampling paused during sleep. Battery-service restart recovery remains unverified. [Validation and evidence](docs/VALIDATION.md)

The exact tested driver was subsequently installed in a local image derived from stock. It passed a normal reboot and ten-minute hold at 85%/70%. The standard local build includes an updater check that hides offers for the exact official base already installed. The battery-only image is the immediate rollback target on the test handheld, and stock remains pinned. [Installed battery validation](evidence/charge-rate-local-image-20261110.json) · [Updater verification](evidence/charge-rate-updater-install-20261110.json)

The Armada submission is [PR #881](https://github.com/armada-os/armada/pull/881).

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
