# Hide an official update that is already the local image's base

The standard local install image includes a check that suppresses an offer only when a local `containers-storage` deployment records the same official channel reference and the exact digest returned by that channel. Newer images, explicit channel changes, and staged updates follow the normal Armada check. Missing or invalid metadata also falls through to the normal check. [Local installation guide](../../docs/LOCAL_INSTALLATION.md)

For each local build, include these fields in `/usr/share/armada/kpfe-charge-limit-build.json` inside the image:

```json
{
  "base_image_ref": "ghcr.io/armada-os/armada:stable",
  "base_image_digest": "sha256:0f0c990818303ae621c7bcbd10979409aa1143a12e2457f3c0c0452652d35d73"
}
```

Use the registry digest and channel of the official image used for that build. The local image has its own digest. The [local image builder](../../tools/build-local-update-image.py) applies the [updater change](suppress-recorded-base-update.patch) to the image's installed script, writes the build record and creates the final tag. The [version-locked image context tool](../../tools/prepare-local-image.py) writes the provenance fields for the tested stable base.

The current draft passed fixture checks for the same stable base, a different stable digest, a later beta base, channel selection, staged updates, registry boots, and missing or invalid metadata. A live preview against the current stable registry returned no update for the recorded base, while the installed check still offered that version. The preview did not alter the installed updater.

The November 10 updater image was installed and verified. Its live check returned no update, and Steam stopped showing the old offer after a refresh. Its battery module passed a two-minute hold after reboot. The November 12 USB-PD trial inherited the updater and official base record. On the test KPFE, the updater-enabled November 10 image is now the immediate rollback target and stock remains pinned. [Updater verification](../../evidence/charge-rate-updater-install-20261110.json) · [USB-PD trial](../usb-pd-reconnect/README.md)

This check travels with a rebuilt local image. To retain the charge fix after a new Armada release, rebuild both local changes against that release. Installing an official image restores that release's updater and battery driver.
