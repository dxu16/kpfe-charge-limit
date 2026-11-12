# KPFE charge-limit investigation and Armada RFC

This repository investigates charge limiting and USB-PD reconnection on the KONKR Pocket FIT Elite (KPFE).

- **Base charge-limit patch.** The original `Over voltage` fault followed a delayed drop in the firmware’s float-voltage target. OEM bypass also proved unreliable on reconnection. The base patch keeps Steam’s thresholds and uses the firmware charge-rate command (`0x06`) for stop and resume. [Original fault](docs/INVESTIGATION.md) · [Patch and design](experimental/charge-rate-policy/README.md)

- **USB-PD reconnect follow-up, local trial.** With charging already held by the base patch, a fresh attachment could stay at 5 V. The follow-up makes one bounded attempt on an eligible awake USB-PD attachment. The installed trial negotiated 9 V after a 0.75-second charge window and held at 85% for ten minutes with charging disabled and Good health. The real 5 V-only PD timeout still needs hardware testing. [Investigation](docs/USB_PD_INVESTIGATION.md) · [Follow-up patch and validation](experimental/usb-pd-reconnect/README.md)

Armada review is tracked in [PR #881](https://github.com/armada-os/armada/pull/881).

The local installation guide includes the same-base Steam update check. The USB-PD trial is the default on the test KPFE, with stock Armada pinned for recovery. [Local installation](docs/LOCAL_INSTALLATION.md) · [Roll back to stock Armada](docs/LOCAL_INSTALLATION.md#roll-back-to-stock-armada)

## Start here

- [Validation and remaining work](docs/VALIDATION.md)
- [Local installation guide](docs/LOCAL_INSTALLATION.md)
- [Evidence index](evidence/README.md)
- [Armada submission](submission/README.md) and [contribution review](docs/CONTRIBUTING_REVIEW.md)

## Layout

| Path | Purpose |
| --- | --- |
| `experimental/charge-rate-policy/` | Base charge-limit patch and exact tested source |
| `experimental/usb-pd-reconnect/` | Follow-up Linux patch, exact tested source, and fault-injection tests |
| `src/base/` | Exact stock driver source used as the patch base |
| `submission/` | Current Armada integration diff, overlay, and PR description |
| `patches/`, `src/patched/` | Historical RFC3 Linux patch and source |
| `tests/` | Patch reconstruction and artifact verification, plus historical C policy and status fixtures |
| `tools/` | Packaging/verification tools and historical diagnostic/build tools |
| `upstream/` | Selected public Armada source snapshots, not a full checkout |
| `evidence/` | Selected text evidence; no firmware, APKs, boot images or modules |

Armada hardware-test base: `dfed5d61e344c473c6e3c654f4090d7f618f3a5a`, Linux 7.2.6. The charge-rate source, boot image and compatibility audit are recorded in the [current build evidence](experimental/charge-rate-policy/build-evidence.json). The [base metadata](upstream/BASELINE.json) also records the historical RFC3 submission base.

## Offline checks

Python 3 and Git verify the manifest, reconstruct both patches, and check the Armada integration diff.

```sh
python3 tests/verify_artifacts.py
```

The C fixtures `tests/test_policy.py` and `tests/test_status.py` cover the historical OEM bypass patch. See the [testing instructions](docs/TESTING.md) for the scope of the available tools.

## Licensing

The Linux source snapshots and modifications retain the source's `GPL-2.0-only` SPDX license. Armada snapshots retain their original license; see `upstream/LICENSE.md`. Original repository documentation and helper scripts are offered under GPL-2.0-or-later; see [LICENSE.md](LICENSE.md). Vendor binaries and decompiled application source are excluded. No personal author identity or legal sign-off has been invented.
