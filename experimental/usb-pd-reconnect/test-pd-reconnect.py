"""Compile selected driver functions with scripted firmware and UCSI replies."""

import os
from pathlib import Path
import re
import subprocess
import tempfile


SOURCE = Path(__file__).with_name('qcom_battmgr.c')
FUNCTIONS = (
    'qcom_battmgr_host_set_rate',
    'qcom_battmgr_host_pd_connection',
    'qcom_battmgr_host_pd_source',
    'qcom_battmgr_host_pd_reapply_stop',
    'qcom_battmgr_host_pd_upgrade',
    'qcom_battmgr_pd_suspend_prepare',
    'qcom_battmgr_pd_suspend_complete',
)

STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#define HZ 1000
#define time_after_eq(a, b) ((a) >= (b))
#define time_before(a, b) ((a) < (b))
#define msecs_to_jiffies(ms) (ms)
#define cpu_to_le32(n) (n)
#define READ_ONCE(n) (n)
#define atomic_read(p) (*(p))
#define system_wq NULL
#define PMIC_GLINK_OWNER_BATTMGR 0x800a
#define PMIC_GLINK_REQ_RESP 1
#define BATTMGR_SET_CHARGE_RATE 6
#define BATTMGR_USB_PROPERTY_GET 0x32
#define BATTMGR_BAT_PROPERTY_GET 0x30
#define POWER_SUPPLY_HEALTH_GOOD 1
#define dev_info(...) ((void)0)
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define dev_get_drvdata(dev) ((dev)->data)

enum { USB_VOLT_MAX, USB_ONLINE, USB_VOLT_NOW, BATT_HEALTH };
enum { POWER_SUPPLY_PROP_ONLINE, POWER_SUPPLY_PROP_USB_TYPE,
       POWER_SUPPLY_PROP_VOLTAGE_MAX, POWER_SUPPLY_USB_TYPE_PD,
       POWER_SUPPLY_USB_TYPE_PD_PPS };

struct qcom_battmgr_charge_rate_request {
    struct { int owner, type, opcode; } hdr;
    int battery_id, charge_rate, charging_path;
};
struct power_supply { int unused; };
union power_supply_propval { int intval; };
struct qcom_battmgr;
struct device { struct qcom_battmgr *data; };
struct qcom_battmgr {
    struct device *dev;
    struct { int online, voltage_now, voltage_max; } usb;
    struct { int health; } status;
    int lock, host_work, host_epoch, host_rate_epoch;
    int host_pd_epoch, host_pd_rate_error_epoch;
    bool host_charge_limit, host_inhibited, host_rate_valid, service_up;
    bool host_pd_pending, host_pd_restop, host_pd_confirm_twice;
    bool host_pd_online, host_pd_offline_seen, host_pd_suspended;
    unsigned long host_pd_offline_at, host_pd_check_until;
};

static unsigned long jiffies;
static int queued, source_voltage, source_type, online, upgrade_after, detach_after;
static int requests, rates[10], replies[10];
static struct power_supply source;

static struct power_supply *power_supply_get_by_name(const char *name)
{
    assert(name != NULL);
    return &source;
}
static void power_supply_put(struct power_supply *p) { assert(p == &source); }
static int power_supply_get_property(struct power_supply *p, int prop,
                                     union power_supply_propval *value)
{
    assert(p == &source);
    value->intval = prop == POWER_SUPPLY_PROP_ONLINE ? online :
                    prop == POWER_SUPPLY_PROP_USB_TYPE ? source_type : source_voltage;
    return 0;
}
static void queue_delayed_work(void *wq, int *work, int delay)
{
    assert(!wq && work && delay == 250);
    queued++;
}
static void pm_wakeup_event(struct device *dev, int delay) { assert(dev && delay == 6000); }
static void msleep(int ms) { jiffies += ms; }
static int qcom_battmgr_request(struct qcom_battmgr *b, void *buf, size_t size)
{
    struct qcom_battmgr_charge_rate_request *req = buf;
    assert(b->service_up && size == 24 && req->hdr.opcode == 6 && requests < 10);
    rates[requests] = req->charge_rate;
    return replies[requests++];
}
static int qcom_battmgr_host_get(struct qcom_battmgr *b, int op, int prop)
{
    assert(op == BATTMGR_USB_PROPERTY_GET || op == BATTMGR_BAT_PROPERTY_GET);
    switch (prop) {
    case USB_VOLT_MAX: b->usb.voltage_max = 5000000; break;
    case USB_VOLT_NOW:
        b->usb.voltage_now = (int)jiffies >= upgrade_after ? 9000000 : 5000000;
        break;
    case USB_ONLINE: b->usb.online = online && (int)jiffies < detach_after; break;
    case BATT_HEALTH: b->status.health = POWER_SUPPLY_HEALTH_GOOD; break;
    default: assert(false);
    }
    return 0;
}
'''

TESTS = r'''
static struct device dev;

static struct qcom_battmgr setup(void)
{
    jiffies = queued = requests = 0;
    source_voltage = 0;
    source_type = POWER_SUPPLY_USB_TYPE_PD;
    online = 1;
    upgrade_after = detach_after = 10000;
    for (int i = 0; i < 10; i++) replies[i] = 0;
    return (struct qcom_battmgr) {
        .dev = &dev, .service_up = true, .host_inhibited = true,
        .host_charge_limit = true, .host_pd_rate_error_epoch = -1,
        .host_pd_pending = true, .host_pd_check_until = 4000,
    };
}

int main(void)
{
    struct qcom_battmgr b = setup();
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0);
    assert(jiffies == 2500 && requests == 2 && rates[0] == 100 && rates[1] == 0);
    assert(!b.host_pd_pending && !b.host_pd_restop && b.host_inhibited);
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && requests == 2);
    puts("PASS unknown-PDO 5 V timeout and one attempt");

    b = setup();
    source_voltage = 5000000;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && requests == 0);
    b = setup();
    source_type = 0;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && requests == 0 && queued == 1);
    jiffies = 4000;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && !b.host_pd_pending);
    puts("PASS reported 5 V-only PD and non-PD sources skip release");

    b = setup();
    upgrade_after = 800;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && jiffies == 900);
    assert(requests == 2 && rates[1] == 0);
    b = setup();
    detach_after = 300;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && jiffies == 300);
    assert(requests == 2 && rates[1] == 0);
    puts("PASS early 9 V and unplug during the window both restore stop");

    b = setup();
    b.usb.online = 0;
    qcom_battmgr_host_pd_connection(&b, 0);
    dev.data = &b;
    assert(qcom_battmgr_pd_suspend_prepare(&dev) == 0);
    jiffies = 2000;
    b.usb.online = 1;
    qcom_battmgr_host_pd_connection(&b, 0);
    assert(!b.host_pd_pending && b.host_pd_suspended);
    qcom_battmgr_pd_suspend_complete(&dev);
    assert(!b.host_pd_suspended && !b.host_pd_pending && requests == 0);
    puts("PASS attachment observed during s2idle cannot open a window");

    b = setup();
    replies[0] = -ETIMEDOUT;
    replies[1] = 0;  /* May be a late reply to the release. */
    replies[2] = -ETIMEDOUT;
    replies[3] = 0;  /* At least one of the two successes was a stop. */
    dev.data = &b;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == -EAGAIN);
    assert(b.host_pd_restop && !b.host_rate_valid && queued == 1);
    assert(qcom_battmgr_pd_suspend_prepare(&dev) == -EBUSY);
    assert(qcom_battmgr_host_pd_reapply_stop(&b, 0) == -ETIMEDOUT);
    assert(b.host_pd_restop && !b.host_rate_valid && queued == 2);
    assert(qcom_battmgr_host_pd_reapply_stop(&b, 0) == 0);
    assert(b.host_rate_valid && !b.host_pd_restop && requests == 4);
    assert(rates[1] == 0 && rates[2] == 0 && rates[3] == 0);
    b.host_pd_pending = true;
    assert(qcom_battmgr_host_pd_upgrade(&b, 0) == 0 && requests == 4);
    assert(qcom_battmgr_pd_suspend_prepare(&dev) == 0);
    puts("PASS late or missing release reply keeps stop pending through retry");
    return 0;
}
'''


def main():
    source = SOURCE.read_text()
    functions = []
    for name in FUNCTIONS:
        match = re.search(rf'^static [^\n]*\b{name}\([^{{]*\{{\n.*?^}}',
                          source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise RuntimeError(f'Missing function {name}')
        functions.append(match.group())
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'pd-test.c'
        output = Path(tmp) / 'pd-test'
        path.write_text('\n'.join([STUBS, *functions, TESTS]))
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra',
                        '-Werror', str(path), '-o', str(output)], check=True)
        subprocess.run([str(output)], check=True)


if __name__ == '__main__':
    main()
