#!/bin/bash
set -euo pipefail
cd /work/linux-7.2.6
# Host-tool compatibility only: system arm64 ptrace.h now needs these types.
# This does not edit any kernel/driver header used by target compilation.
python3 - <<'PY'
from pathlib import Path
p = Path('tools/include/uapi/linux/types.h')
s = p.read_text()
if 'typedef unsigned __int128 __u128' not in s:
    marker = '#ifndef __ASSEMBLER__\n'
    assert s.count(marker) == 1
    s = s.replace(marker, marker + '''
#ifdef __SIZEOF_INT128__
typedef __signed__ __int128 __s128 __attribute__((aligned(16)));
typedef unsigned __int128 __u128 __attribute__((aligned(16)));
#endif
''')
    p.write_text(s)
PY
cp /inputs/running-kernel.config .config
cp /inputs/running-kernel.config /output/running-kernel.config
make ARCH=arm64 olddefconfig
cp .config /output/build-kernel.config
diff -u /output/running-kernel.config /output/build-kernel.config > /output/config-diff.txt || test "$?" = 1
if [ -s /output/config-diff.txt ]; then
  cat /output/config-diff.txt
  echo 'Configuration must match running kernel exactly.' >&2
  exit 1
fi
cat > /work/host-u128-compat.h <<'EOF'
#ifdef __SIZEOF_INT128__
typedef __signed__ __int128 __s128 __attribute__((aligned(16)));
typedef unsigned __int128 __u128 __attribute__((aligned(16)));
#endif
EOF
make ARCH=arm64 HOSTCC='gcc -include /work/host-u128-compat.h' -j2 prepare modules_prepare
python3 - <<'PY'
from pathlib import Path
for name in ('.module-common.o',
             'drivers/power/supply/qcom_battmgr.o',
             'drivers/power/supply/qcom_battmgr.mod.o',
             'drivers/power/supply/qcom_battmgr.ko'):
    Path(name).unlink(missing_ok=True)
PY
make ARCH=arm64 HOSTCC='gcc -include /work/host-u128-compat.h' -j2 KBUILD_BUILTIN= KBUILD_MODPOST_WARN=1 drivers/power/supply/qcom_battmgr.ko
cp drivers/power/supply/qcom_battmgr.ko /output/qcom_battmgr.ko
cp drivers/power/supply/qcom_battmgr.c /output/qcom_battmgr.c
modinfo /output/qcom_battmgr.ko > /output/module-info.txt
nm -u /output/qcom_battmgr.ko > /output/undefined-symbols.txt
gcc --version > /output/compiler-version.txt
sha256sum /output/qcom_battmgr.ko > /output/module.sha256
printf '\nBuild complete with exact runtime configuration. NOT installed or loaded.\n'
printf 'Export/type ABI verification is still required.\n'
