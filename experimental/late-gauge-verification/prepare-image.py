"""Prepare a version-locked local bootc image context; never deploy it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--original-boot', type=Path, required=True)
parser.add_argument('--tested-boot', type=Path, required=True)
parser.add_argument('--module', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_boot(path, expected):
    data = path.read_bytes()
    assert sha(data) == expected, f'Unexpected boot image: {path}'
    assert data[:8] == b'ANDROID!'
    assert struct.unpack_from('<I', data, 40)[0] == 0
    kernel_size, ramdisk_size = struct.unpack_from('<I4xI', data, 8)
    page = struct.unpack_from('<I', data, 36)[0]
    assert page == 2048
    offset = page + (kernel_size + page - 1) // page * page
    assert len(data) == offset + (ramdisk_size + page - 1) // page * page
    return data, data[page:page + kernel_size], data[offset:offset + ramdisk_size]


original, original_kernel, original_rd = read_boot(
    args.original_boot, '9d6d98417032f1b8768679e02c1441083825bfff8119af49605352f2e8d72544')
tested, tested_kernel, tested_rd = read_boot(
    args.tested_boot, '85c4442caa9bb4bee01bc484ea6a6e38a78e06d0462adbeacf469a716bec720e')
assert original_kernel == tested_kernel
assert original[64:576] == tested[64:576] and original[608:1632] == tested[608:1632]
module = args.module.read_bytes()
assert sha(module) == '5db1684eb32a2613d1b33a5954d9729254647b8dba65896814360e3d96906c87'
out = args.output_dir.resolve()
assert not out.exists(), 'Output directory must be new'
out.mkdir(parents=True)
shutil.copyfile(args.module, out / 'qcom_battmgr.ko')
(out / 'initramfs.img').write_bytes(tested_rd)
record = dict(
    base_image_digest='sha256:0f0c990818303ae621c7bcbd10979409aa1143a12e2457f3c0c0452652d35d73',
    kernel='7.2.6', version='20261109.dfed5d6-kpfe-charge-rfc3',
    source_sha256='2d382b01f26b8f865243e996e597001484af1bb045bb3476315293134d7ed5e7',
    module_sha256=sha(module), initramfs_sha256=sha(tested_rd),
    original_initramfs_sha256=sha(original_rd),
    candidate_boot_sha256=sha(tested), original_boot_sha256=sha(original),
    hardware_validated=False)
(out / 'build-record.json').write_text(json.dumps(record, indent=2) + '\n')
containerfile = f'''FROM localhost/kpfe-armada-base:20261110
RUN test "$(sha256sum /usr/lib/modules/7.2.6/kernel/drivers/power/supply/qcom_battmgr.ko | cut -d' ' -f1)" = "e1b3d59b667e8161a312ac5b8c20b4c8f8d3a275b6c171b1249dc07449b06308" && \\
    test "$(sha256sum /usr/lib/modules/7.2.6/initramfs.img | cut -d' ' -f1)" = "{sha(original_rd)}"
COPY qcom_battmgr.ko /usr/lib/modules/7.2.6/kernel/drivers/power/supply/qcom_battmgr.ko
COPY initramfs.img /usr/lib/modules/7.2.6/initramfs.img
COPY build-record.json /usr/share/armada/kpfe-charge-limit-build.json
RUN chmod 0644 /usr/lib/modules/7.2.6/kernel/drivers/power/supply/qcom_battmgr.ko && chmod 0600 /usr/lib/modules/7.2.6/initramfs.img && depmod -a 7.2.6 && bootc container lint
LABEL org.opencontainers.image.version="20261109.dfed5d6-kpfe-charge-rfc3"
'''
(out / 'Containerfile').write_text(containerfile)
print(json.dumps(record, indent=2))
