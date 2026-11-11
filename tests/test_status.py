"""Exercise actual candidate status getter with firmware-response fixtures."""
from pathlib import Path
import re
import subprocess

import argparse
import os
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] /
                    'src/patched/drivers/power/supply/qcom_battmgr.c')
args = parser.parse_args()
scratch = tempfile.TemporaryDirectory(prefix='kpfe-charge-test-')
output = Path(scratch.name)
source = args.source.read_text()
functions = source[source.index('static int qcom_battmgr_host_get('):
                   source.index('static int qcom_battmgr_bat_sm8350_update(')]
names = ('BATTMGR_BAT_PROPERTY_GET', 'BATTMGR_USB_PROPERTY_GET', 'BATT_STATUS',
         'BATT_HEALTH', 'BATT_CHG_CTRL_EN', 'BATT_OEM_CHARGE_ONLINE', 'BATT_CAPACITY', 'BATT_CURR_NOW',
         'USB_ONLINE', 'CHARGE_CTRL_END_THR_MAX')
defines = '\n'.join(re.search(r'^#define ' + name + r'\s+.*$', source, re.M).group()
                    for name in names)
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
enum { POWER_SUPPLY_STATUS_UNKNOWN, POWER_SUPPLY_STATUS_CHARGING,
       POWER_SUPPLY_STATUS_DISCHARGING, POWER_SUPPLY_STATUS_NOT_CHARGING,
       POWER_SUPPLY_STATUS_FULL };
#define POWER_SUPPLY_HEALTH_GOOD 1
union power_supply_propval { int intval; };
struct qcom_battmgr {
    int lock;
    bool host_ready, native_limit_enabled, oem_charge_online;
    struct { bool online; } usb;
    struct { unsigned int status, health, percent; int current_now; } status;
    struct { unsigned int charge_ctrl_end; } info;
};
static int lock_depth, calls, fail_call, fail_code;
static struct { unsigned int raw, health, soc; int current; bool online, charging, native; } fw;
static void mutex_lock(int *lock) { (void)lock; assert(!lock_depth); lock_depth++; }
static void mutex_unlock(int *lock) { (void)lock; assert(lock_depth == 1); lock_depth--; }
'''
stub = r'''
static int qcom_battmgr_request_property(struct qcom_battmgr *b, int op, int prop, unsigned int value)
{
    (void)value;
    assert(lock_depth == 1);
    if (++calls == fail_call)
        return fail_code;
    if (op == BATTMGR_USB_PROPERTY_GET && prop == USB_ONLINE) {
        b->usb.online = fw.online;
        return 0;
    }
    assert(op == BATTMGR_BAT_PROPERTY_GET);
    switch (prop) {
    case BATT_STATUS: b->status.status = fw.raw; break;
    case BATT_HEALTH: b->status.health = fw.health; break;
    case BATT_CHG_CTRL_EN: b->native_limit_enabled = fw.native; break;
    case BATT_OEM_CHARGE_ONLINE: b->oem_charge_online = fw.charging; break;
    case BATT_CAPACITY: b->status.percent = fw.soc; break;
    case BATT_CURR_NOW: b->status.current_now = fw.current; break;
    default: assert(0);
    }
    return 0;
}
'''
tests = r'''
static struct qcom_battmgr baseline(void)
{
    /* Reproduce boot: cache still says enabled after firmware was disabled. */
    struct qcom_battmgr b = { .host_ready = true, .native_limit_enabled = true };
    b.info.charge_ctrl_end = 85;
    fw.raw = POWER_SUPPLY_STATUS_DISCHARGING;
    fw.health = POWER_SUPPLY_HEALTH_GOOD;
    fw.soc = 85; fw.current = -5000; fw.online = true; fw.charging = false; fw.native = false;
    calls = fail_call = 0; fail_code = -ETIMEDOUT;
    return b;
}
static void expect(struct qcom_battmgr *b, int expected)
{
    union power_supply_propval v = { .intval = 777 };
    calls = 0;
    assert(qcom_battmgr_host_read_status(b, &v) == 0);
    assert(v.intval == expected && !lock_depth && calls == 7);
}
int main(void)
{
    struct qcom_battmgr b = baseline();
    expect(&b, POWER_SUPPLY_STATUS_FULL);
    assert(!b.native_limit_enabled);
    fw.soc = 84; expect(&b, POWER_SUPPLY_STATUS_NOT_CHARGING);
    fw.soc = 70; expect(&b, POWER_SUPPLY_STATUS_NOT_CHARGING);
    b = baseline(); fw.charging = true; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); fw.health = 2; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); b.usb.online = true; fw.online = false;
    expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); b.host_ready = false; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); fw.native = true; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); b.info.charge_ctrl_end = 100; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); fw.soc = 101; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); fw.current = -50001; expect(&b, POWER_SUPPLY_STATUS_DISCHARGING);
    b = baseline(); fw.raw = POWER_SUPPLY_STATUS_CHARGING; fw.current = 50001;
    expect(&b, POWER_SUPPLY_STATUS_CHARGING);
    b = baseline(); fw.current = -50000; expect(&b, POWER_SUPPLY_STATUS_FULL);
    b = baseline(); fw.current = 50000; expect(&b, POWER_SUPPLY_STATUS_FULL);
    b = baseline(); fw.raw = POWER_SUPPLY_STATUS_UNKNOWN;
    expect(&b, POWER_SUPPLY_STATUS_UNKNOWN);
    for (int failure = 1; failure <= 7; failure++) {
        b = baseline(); fail_call = failure;
        union power_supply_propval v = { .intval = 777 };
        assert(qcom_battmgr_host_read_status(&b, &v) == -ETIMEDOUT);
        assert(v.intval == 777 && !lock_depth);
    }
    b = baseline(); fail_call = 1; fail_code = 13;
    union power_supply_propval v = { .intval = 777 };
    assert(qcom_battmgr_host_read_status(&b, &v) == -EIO && v.intval == 777);
    puts("PASS: live status getter: stale native cache, limit, hysteresis, unplug, weak supply, ongoing charge, faults, disabled/unready/native modes, bounds and all seven read failures");
    return 0;
}
'''
(output / 'test-gap-status.c').write_text(harness + defines + '\n' + stub + functions + tests)
subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                str(output / 'test-gap-status.c'), '-o', str(output / 'test-gap-status')], check=True)
result = subprocess.run([str(output / 'test-gap-status')], text=True, capture_output=True, check=True)
(output / 'status-tests.txt').write_text(result.stdout)
print(result.stdout)
