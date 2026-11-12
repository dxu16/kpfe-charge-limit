# Install the KPFE charge-limit patch locally

This guide builds a local image with the combined KPFE charge-limit and USB-PD reconnect patch and the same-base update check. Steam hides the offer for the exact official image used as the build's base. A newer image or channel change still appears. The driver was tested on Armada `20261109.dfed5d6` with Linux `7.2.6`. Recovery after a battery-service restart remains unverified. [Hardware results](VALIDATION.md) · [Updater verification](../evidence/charge-rate-updater-install-20261110.json)

## Build a matching Armada image

Use an ARM64 Linux builder with Git, Just, Podman, Buildah, Skopeo and Python 3. Copy this investigation repo to the builder so the image tool can find its updater patch. Start from the source revision reported by the official channel you intend to build. Keep the channel and registry digest from that same inspection for the final image. [Armada development instructions](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/README.md#development)

In Bash on the builder, set `kpfe_repo` to the absolute path of this repo and choose the official channel:

~~~sh
set -euo pipefail
kpfe_repo=/absolute/path/to/kpfe-charge-limit
base_ref=ghcr.io/armada-os/armada:stable
base_info=$(skopeo inspect --no-tags --format '{{.Digest}} {{index .Labels "org.opencontainers.image.version"}}' "docker://$base_ref")
read -r base_digest base_version <<< "$base_info"
[[ "$base_digest" =~ ^sha256:[0-9a-f]{64}$ && "$base_version" =~ ^[0-9]{8}\.[0-9a-f]{7,40}$ ]]
git clone https://github.com/armada-os/armada.git
cd armada
git switch --detach "${base_version##*.}"
git switch -c kpfe-charge-rate
patch="$kpfe_repo/submission/armada-kpfe-charge-limit.patch"
git apply --check "$patch"
git apply "$patch"
just check
just package kernel
just build localhost/armada-kpfe "battery-$base_version"
image="localhost/armada-kpfe:charge-rate-$base_version"
python3 "$kpfe_repo/tools/build-local-update-image.py" \
    --input-image "localhost/armada-kpfe:battery-$base_version" \
    --output-image "$image" --base-ref "$base_ref" --base-digest "$base_digest"
podman save --format oci-archive -o armada-kpfe-charge-rate.oci.tar "$image"
~~~

The single `git apply` command installs `0905`, which includes the charge-limit fix and USB-PD reconnect. If you are starting from the original PR #881 branch, use the [follow-up diff](../submission/README.md#update-pr-881) to update its existing `0905` before building.

The `battery-` tag is the intermediate image. The `charge-rate-` tag is the installation image and contains the update check. The image tool stops if the updater patch does not apply. If the kernel integration or updater has changed in the selected release, reconcile the source changes and retest the final image. Use a new output tag if rebuilding an existing version. [Armada package build](https://github.com/armada-os/armada/blob/066ecdc0d26edf7ba228cec26cbd2054810e92f8/packages/README.md) · [Updater patch](../experimental/local-image-update/README.md)

For the exact tested release, you can derive an image from the stock base. This requires the matching stock boot image, RAM-tested boot image and ABI-audited module. The [image context tool](../tools/prepare-local-image.py) verifies them against the [build evidence](../experimental/charge-rate-policy/build-evidence.json) and records the official base. After building that context as an intermediate image, run `build-local-update-image.py` with that tag as `--input-image` and a new `--output-image`. It reads the channel and digest from the build record. Use the same Podman store for both steps. Export the final image as shown above. [bootc initramfs guidance](https://bootc.dev/bootc/bootc-initramfs.7.html)

The derived image passed a normal boot and ten-minute installed hold on the test handheld. The guide's final image step reproduced the installed updater, driver and initramfs byte for byte and passed container lint. The kernel integration diff was checked against the pinned snapshot. A complete Armada source build remains pending. [Installed build record](../evidence/charge-rate-local-image-20261110.json)

The version-locked image tool above expects the exact artifacts from the base charge-limit build. The USB-PD trial on the test KPFE derived a local image from the existing updater-enabled deployment using the exact RAM-tested module and initramfs. The combined source build remains unverified. [Trial build and results](../experimental/usb-pd-reconnect/README.md)

## Keep a stock recovery path

On the handheld, confirm the device, save the current deployment details, and save the native battery settings.

~~~sh
tr '\0' '\n' </sys/firmware/devicetree/base/compatible | grep -x 'konkr,pocket-fit-elite'
mkdir -p "$HOME/kpfe-stock-recovery"
sudo bootc status --json | tee "$HOME/kpfe-stock-recovery/bootc-status.json"
sudo ostree admin status | tee "$HOME/kpfe-stock-recovery/ostree-status.txt"
for attr in charge_control_end_threshold charge_control_start_threshold constant_charge_current; do
    cat "/sys/class/power_supply/battery/$attr" > "$HOME/kpfe-stock-recovery/$attr"
done
sudo install -m 0644 /boot/efi/KERNEL "$HOME/kpfe-stock-recovery/KERNEL.stock"
sudo ostree admin pin booted
df -h /boot /boot/efi /var
~~~

Copy the recovery folder to another computer. Verify that your PC can see the handheld with `fastboot devices` in OpenABL and can return it to the stock boot. Keep the pinned stock deployment available, since the saved boot image references its deployment path. On this Armada setup OpenABL uses a generated boot image, so a second deployment alone does not guarantee a boot menu entry.

## Stage and verify the local image

Copy the OCI archive to the handheld and import it into the root container store.

~~~sh
image=localhost/armada-kpfe:charge-rate-20261109.dfed5d6 # Use the final tag from your build.
sudo podman load -i /absolute/path/to/armada-kpfe-charge-rate.oci.tar
sudo podman image inspect "$image"
sudo bootc status
sudo bootc switch --transport containers-storage "$image"
sudo bootc status --json
~~~

Before switching, confirm the booted deployment is the working image you pinned and that there is no unrelated staged deployment. If upgrading a local image, keep the pinned stock deployment too. After switching, confirm the staged image matches the local image you built. Unplug the charger and reboot normally with `sudo systemctl reboot`. Armada's normal reboot runs the hooks that generate the boot image for the new deployment.

After boot, confirm the new image is running and the stock deployment is still pinned. Check the kernel, driver and battery settings:

~~~sh
sudo bootc status
uname -r
modinfo -F filename qcom_battmgr
cat /sys/class/power_supply/battery/health
cat /sys/class/power_supply/battery/charge_control_end_threshold
cat /sys/class/power_supply/battery/charge_control_start_threshold
~~~

If you built from the recorded RAM artifacts, compare the loaded driver's build ID note and installed module hashes with the build record. For a source build, compare the loaded note to that build's module, since the build ID can differ from the RAM-tested artifact.

In Steam's System settings, check for updates. If the selected channel still points to the recorded base digest, the same-release offer should be gone. A different digest or channel remains eligible for an update.

Test with the usual charger while the awake handheld is already above the selected limit. Leave it connected for ten minutes. The battery should stop charging, health should stay Good, and the reported voltage ceiling should stay steady. Steam should show the full check mark when battery current is near zero. The observer saves samples without changing charge settings:

~~~sh
python3 /absolute/path/to/tools/observe-transition.py --label local-install --mode hold --seconds 600 > local-hold.jsonl
~~~

On the exact tested KPFE build, run the observer with `sudo` and add `--physical-enable` to verify that the audited charger-enable bit stays clear. A brief negative current indicates discharge. Sustained positive current or an unexpected health or voltage change is grounds to unplug and roll back.

For the USB-PD trial, expect a brief enable window on eligible awake attachments. Use the same charger and cable, verify the stop after negotiation, then start the ten-minute hold. On the tested charger, `qcom-battmgr-usb` reported 9 V while charger-enable stayed clear and battery health stayed Good. An attachment during `s2idle` can stay at 5 V. [Trial validation](../experimental/usb-pd-reconnect/README.md#validation)

## Roll back to stock Armada

Unplug the charger. Run `sudo ostree admin status` and match the pinned stock deployment to the checksum and deployment serial saved in `ostree-status.txt` before installation. Count deployment entries from the top, starting at zero. Replace `INDEX` with the current index of that exact stock entry. The default `bootc rollback` command selects the immediate rollback slot, which can contain an earlier local build. [OSTree deployment selection](https://github.com/ostreedev/ostree/blob/main/man/ostree-admin-set-default.xml) · [bootc rollback](https://bootc.dev/bootc/man/bootc-rollback.8.html)

~~~sh
sudo ostree admin set-default INDEX
sudo ostree admin status
~~~

Confirm the stock deployment is first in the list, then run `sudo systemctl reboot`. Armada's shutdown hooks regenerate the boot image for the selected deployment. After reboot, verify that the booted checksum and serial match the stock entry you saved.

If the local deployment cannot boot, use the verified PC connection to temporarily boot the saved stock image with `fastboot boot KERNEL.stock`. The referenced deployment must still exist. From that stock session, use the same selection and verification steps to make stock the default before rebooting normally.

After booting stock, keep the charger unplugged while restoring the saved native settings. The automatic driver disables native percentage enforcement in firmware, so the stock driver needs its settings reapplied.

~~~sh
bat=/sys/class/power_supply/battery
for attr in charge_control_end_threshold charge_control_start_threshold constant_charge_current; do
    sudo tee "$bat/$attr" < "$HOME/kpfe-stock-recovery/$attr" >/dev/null
done
cat "$bat/health" "$bat/charge_control_end_threshold" "$bat/charge_control_start_threshold"
~~~

## Return to official updates

A local image is a separate bootc source. Raw `bootc upgrade` follows that reference. The tested Armada Steam updater resolved a local image to the official repository and selected channel. An actual official update from the local image has yet to be tested. You can also explicitly switch back to your chosen official tag, for example `sudo bootc switch ghcr.io/armada-os/armada:stable`, then reboot and verify the native charge controls. An official update replaces the local patch unless that release includes it. [Updater check](../evidence/updater-target-20261110.json)

To keep the charge fix or the USB-PD follow-up on a newer release, check which changes that release already includes, then rebuild any remaining patches against its source and recorded base digest. The update check will then suppress the equivalent official offer for that new local image.
