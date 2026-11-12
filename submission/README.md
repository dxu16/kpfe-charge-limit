# Armada submission

The `0905` kernel patch restores charge limiting on KPFE and allows USB-PD to renegotiate higher input voltage after an eligible awake reconnect. The overlay contains the combined driver patch, its series entry and its provenance.

## Update PR #881

Use `armada-kpfe-usb-pd-follow-up.patch` on `dxu16/armada:fix/kpfe-charge-limit` at the original PR commit `83642b06f35c0c49578a0a20f42921e445bf45c7`. It updates `0905` in place and revises its provenance. [Armada PR #881](https://github.com/armada-os/armada/pull/881)

```sh
git apply --check /absolute/path/to/armada-kpfe-usb-pd-follow-up.patch
git apply /absolute/path/to/armada-kpfe-usb-pd-follow-up.patch
```

Suggested follow-up commit title **`fix(kernel): recover USB-PD voltage on KPFE charge-limit reconnect`**. The [updated PR description](PR_DESCRIPTION.md) covers both changes.

## Apply the full submission to a fresh checkout

`armada-kpfe-charge-limit.patch` applies the complete overlay to the pinned Armada snapshot at `066ecdc0d26edf7ba228cec26cbd2054810e92f8`. It also applies to the parent of the original PR commit, `b031deef99a095104ef234c5a0705850152dffe1`. Check for series changes on other revisions.

```sh
git apply --check /absolute/path/to/armada-kpfe-charge-limit.patch
git apply /absolute/path/to/armada-kpfe-charge-limit.patch
just check
just package kernel
```

The combined `0905` reconstructs the exact driver used in the [installed trial](../experimental/usb-pd-reconnect/README.md#validation) on one KPFE. The 5 V-only USB-PD timeout was tested in simulation. Battery-service restart recovery and a full Armada kernel package build remain unverified. See the [contribution review](../docs/CONTRIBUTING_REVIEW.md) and the [local installation guide](../docs/LOCAL_INSTALLATION.md) for deployment and the same-base updater check.
