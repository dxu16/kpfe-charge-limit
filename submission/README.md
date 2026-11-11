# Armada submission

PR title **`fix(kernel): restore charge limiting on KONKR Pocket FIT Elite`**

`armada-kpfe-charge-limit.patch` is a unified diff against Armada commit `066ecdc0d26edf7ba228cec26cbd2054810e92f8`. It contains exactly:

1. `packages/kernel/patches/0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch`
2. `packages/kernel/patches/series` adds 0905 immediately after 0904.
3. `packages/kernel/PATCHES.md` records patch provenance.

The Linux patch changes one driver file, with 381 insertions and six deletions. It reconstructs the exact source tested on the handheld. `overlay/` contains the three resulting Armada files.

In a clean full Armada checkout at the stated base:

```sh
git apply --check /absolute/path/to/armada-kpfe-charge-limit.patch
git apply /absolute/path/to/armada-kpfe-charge-limit.patch
just check
just package kernel
```

Check for base/series changes before applying to a newer revision. See the [contribution review](../docs/CONTRIBUTING_REVIEW.md), [draft PR description](PR_DESCRIPTION.md), and [validation status](../docs/VALIDATION.md).

This is the local bundle for a normal GitHub PR. The patched driver passed hardware tests on one KPFE, including the installed hold. Battery-service restart recovery and the full Armada source build remain unverified. The separate local updater change is outside this PR.
