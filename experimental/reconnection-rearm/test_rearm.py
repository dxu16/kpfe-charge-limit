"""Compile the actual experimental helpers/worker with fault-injecting firmware."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=Path(__file__).with_name('qcom_battmgr.c'))
args = parser.parse_args()
source = args.source.read_text()
functions = source[source.index('static int qcom_battmgr_host_set_online('):
                   source.index('static int qcom_battmgr_host_set_threshold(')]
policy = re.search(r'static bool qcom_battmgr_host_should_charge\(.*?\n}\n', source, re.S).group()
names = ('BATTMGR_BAT_PROPERTY_GET', 'BATTMGR_BAT_PROPERTY_SET', 'BATTMGR_USB_PROPERTY_GET',
         'BATT_OEM_CHARGE_ONLINE', 'BATT_CHG_CTRL_LIM', 'BATT_CAPACITY', 'USB_ONLINE',
         'BATT_HEALTH', 'BATT_CURR_NOW', 'CHARGE_CTRL_END_THR_MAX')
defines = '\n'.join(re.search(r'^#define ' + name + r'\s+.*$', source, re.M).group() for name in names)
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stddef.h>
#include <errno.h>
#define HZ 1000UL
#define POWER_SUPPLY_HEALTH_GOOD 1
#define READ_ONCE(x) (x)
#define time_before(a,b) ((long)((a)-(b)) < 0)
#define time_after_eq(a,b) (!time_before(a,b))
#define msecs_to_jiffies(x) (x)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
struct qcom_battmgr {
    struct delayed_work host_work;
    bool oem_charge_online, host_holding, host_rearmed, host_ready;
    bool service_up, host_stopping, host_restart;
    unsigned long host_verify_after;
    int dev, lock, bat_psy;
    struct { unsigned int charge_current_limit, charge_ctrl_start, charge_ctrl_end; } info;
    struct { unsigned int percent; int health, current_now; } status;
    struct { bool online; } usb;
};
static unsigned long jiffies, queued_delay;
static int errors, notifications, writes, sequence[16], calls, fail_call, fail_code;
static bool firmware_online, timeout_limit, failure_applied;
static int physical_current;
static bool connected, fail_stop_once;
static int health_value;
static unsigned long normal_ready_at;
static void msleep(unsigned int ms) { jiffies += ms; }
static void pm_stay_awake(int x) { (void)x; }
static void pm_relax(int x) { (void)x; }
static void mutex_lock(int *x) { assert(!*x); *x = 1; }
static void mutex_unlock(int *x) { assert(*x); *x = 0; }
static void power_supply_changed(int x) { (void)x; ++notifications; }
#define dev_err_ratelimited(...) (++errors)
static int system_wq;
static void queue_delayed_work(int queue, struct delayed_work *work, unsigned long delay)
{ (void)queue; (void)work; queued_delay = delay; }
static int qcom_battmgr_host_prepare(struct qcom_battmgr *b) { (void)b; return 0; }
static int qcom_battmgr_request_property(struct qcom_battmgr *b, int opcode, int prop, int value)
{
    (void)opcode; assert(b->lock && prop == BATT_OEM_CHARGE_ONLINE);
    assert(writes < 16); sequence[writes++] = value;
    ++calls;
    if (!value && fail_stop_once) { fail_stop_once=false; return -ETIMEDOUT; }
    if (fail_call == calls && !failure_applied) return fail_code;
    firmware_online = value;
    if (value) normal_ready_at = jiffies + 50;
    if (fail_call == calls) return fail_code;
    return 0;
}
static int qcom_battmgr_host_get(struct qcom_battmgr *b, int opcode, int prop)
{
    assert(b->lock); ++calls;
    if (calls == fail_call) return fail_code > 0 ? -EIO : fail_code;
    if (opcode == BATTMGR_USB_PROPERTY_GET) { b->usb.online = connected; return 0; }
    switch(prop) {
    case BATT_OEM_CHARGE_ONLINE: b->oem_charge_online = firmware_online; break;
    case BATT_CHG_CTRL_LIM:
        b->info.charge_current_limit = firmware_online && !timeout_limit &&
            time_after_eq(jiffies,normal_ready_at) ? 8400000 : 0; break;
    case BATT_CAPACITY: b->status.percent = 94; break;
    case BATT_HEALTH: b->status.health = health_value; break;
    case BATT_CURR_NOW: b->status.current_now = physical_current; break;
    default: assert(false);
    }
    return 0;
}
static struct qcom_battmgr baseline(void)
{
    jiffies = 10000; queued_delay = 0; errors = notifications = writes = calls = 0;
    fail_call = 0; fail_code = -ETIMEDOUT; timeout_limit = failure_applied = false;
    firmware_online = false; connected = true; physical_current = 290000;
    fail_stop_once=false; health_value=POWER_SUPPLY_HEALTH_GOOD;
    return (struct qcom_battmgr){ .host_ready=true, .service_up=true,
        .info={.charge_ctrl_start=70,.charge_ctrl_end=85} };
}
'''
tests = r'''
int main(void)
{
    struct qcom_battmgr b = baseline(); b.lock = 1;
    assert(qcom_battmgr_host_rearm(&b) == 0);
    assert(writes == 2 && sequence[0] == 1 && sequence[1] == 0);
    assert(!firmware_online && !b.oem_charge_online && jiffies == 10050);
    b = baseline(); b.lock = 1; timeout_limit = true;
    assert(qcom_battmgr_host_rearm(&b) == -ETIMEDOUT);
    assert(writes == 2 && !firmware_online && jiffies == 12000);
    /* A failed request can still have reached firmware: reconcile and stop. */
    for (int fail=1; fail<=8; ++fail) {
        b = baseline(); b.lock=1; fail_call=fail; failure_applied=true;
        int result = qcom_battmgr_host_rearm(&b);
        assert(fail == 6 ? result == 0 : result < 0);
        assert(writes <= 2 && !firmware_online);
    }
    b=baseline(); b.lock=1; fail_call=2; fail_code=13;
    assert(qcom_battmgr_host_rearm(&b) == -EIO && !firmware_online);
    b=baseline(); b.lock=1;
    assert(qcom_battmgr_host_set_online(&b,false)==0 && writes==0);

    b=baseline();
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(!writes && b.host_holding && !b.host_rearmed && queued_delay==5000);
    jiffies=14999;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(!writes && queued_delay==1);
    jiffies=15000;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==2 && b.host_rearmed && queued_delay==5000 && !b.lock);
    physical_current=0; jiffies=b.host_verify_after;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==2 && queued_delay==60000);
    /* Persistent failure stays visible; no periodic release/re-enter loop. */
    physical_current=290000;
    qcom_battmgr_host_worker(&b.host_work.work);
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==2 && errors==2);
    connected=false;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(!b.host_holding && !b.host_rearmed && firmware_online);
    connected=true;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(b.host_holding && !b.host_rearmed && !firmware_online);
    jiffies=b.host_verify_after;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(b.host_rearmed && writes==6);
    /* Negative current and a settled healthy hold do not trigger recovery. */
    b=baseline(); physical_current=-300000;
    qcom_battmgr_host_worker(&b.host_work.work); jiffies=b.host_verify_after;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==0);
    b=baseline();
    qcom_battmgr_host_worker(&b.host_work.work); jiffies=b.host_verify_after;
    fail_stop_once=true;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==2 && firmware_online && errors==1);
    jiffies=b.host_verify_after;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==3 && !firmware_online && errors==1 && queued_delay==5000);
    physical_current=0; jiffies=b.host_verify_after;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==3 && errors==1);
    b=baseline(); health_value=4;
    qcom_battmgr_host_worker(&b.host_work.work);
    assert(writes==0);
    puts("PASS: actual rearm helpers and worker: acknowledgement, timeout, request/read failures, idempotence, gauge settling, one recovery per hold, unplug reset and real drain");
}
'''
with tempfile.TemporaryDirectory(prefix='kpfe-rearm-test-') as tmp:
    tmp = Path(tmp)
    c = tmp / 'test.c'
    c.write_text(defines + '\n' + stub + policy + functions + tests)
    exe = tmp / 'test'
    subprocess.run([os.environ.get('CC','gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
