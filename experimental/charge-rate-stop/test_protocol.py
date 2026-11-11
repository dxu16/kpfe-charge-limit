"""Compile actual diagnostic request/ACK helpers against a mock transport."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

source = Path(__file__).with_name('qcom_battmgr.c').read_text()


def function(name):
    match = re.search(r'static (?:int|void) ' + name + r'\(.*?\n}\n', source, re.S)
    assert match, name
    return match[0]


request = re.search(r'struct qcom_battmgr_charge_rate_request \{.*?\n};', source, re.S)[0]
program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t __le32;
#define cpu_to_le32(x) ((uint32_t)(x))
#define le32_to_cpu(x) ((uint32_t)(x))
#define PMIC_GLINK_OWNER_BATTMGR 32778
#define PMIC_GLINK_REQ_RESP 1
#define BATTMGR_SET_CHARGE_RATE 6
#define BATTMGR_BAT_PROPERTY_GET 48
#define BATT_CHG_CTRL_EN 24
#define POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO 0
#define POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE 1
struct pmic_glink_hdr { uint32_t owner, type, opcode; };
struct qcom_battmgr {
 bool charge_rate_supported, charge_rate_inhibited, native_charge_limit_enabled;
 int lock, ack, error;
 void *bat_psy;
};
union power_supply_propval { int intval; };
static unsigned requests, queries, changes;
static int transport_error, query_error;
static unsigned char packet[24];
static void mutex_lock(int *p) { assert(!*p); *p=1; }
static void mutex_unlock(int *p) { assert(*p); *p=0; }
static void complete(int *p) { ++*p; }
static void power_supply_changed(void *p) { (void)p; ++changes; }
static int qcom_battmgr_request(struct qcom_battmgr *b, void *p, size_t n) {
 assert(b->lock && n==24); memcpy(packet,p,n); ++requests; return transport_error;
}
static int qcom_battmgr_request_property(struct qcom_battmgr *b, int op, int prop, uint32_t v) {
 assert(b->lock && op==48 && prop==24 && v==0); ++queries; return query_error;
}
'''
program += request + '\n' + function('qcom_battmgr_charge_rate_ack')
program += function('qcom_battmgr_get_charge_rate_behaviour')
program += function('qcom_battmgr_set_charge_rate_behaviour')
program += r'''
static void assert_packet(unsigned rate) {
 const uint32_t expected[6]={32778,1,6,0,rate,0};
 assert(sizeof(struct qcom_battmgr_charge_rate_request)==24);
 assert(offsetof(struct qcom_battmgr_charge_rate_request,charge_rate)==16);
 assert(memcmp(packet,expected,24)==0);
}
int main(void) {
 struct qcom_battmgr b={0}; union power_supply_propval v;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==-EOPNOTSUPP && requests==0);
 b.charge_rate_supported=true;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,2)==-EINVAL && requests==0);
 b.native_charge_limit_enabled=true;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==-EBUSY && requests==0);
 b.native_charge_limit_enabled=false;
 query_error=-ETIMEDOUT;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==-ETIMEDOUT && requests==0);
 query_error=0;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==0 && b.charge_rate_inhibited);
 assert_packet(0);
 assert(qcom_battmgr_get_charge_rate_behaviour(&b,&v)==0 && v.intval==1);
 transport_error=-ETIMEDOUT;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,0)==-ETIMEDOUT && b.charge_rate_inhibited);
 transport_error=512;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,0)==-EIO && b.charge_rate_inhibited);
 transport_error=0;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,0)==0 && !b.charge_rate_inhibited);
 assert_packet(100);
 /* Reassertion sends another stop command; no release or skipped duplicate. */
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==0);
 unsigned before=requests;
 assert(qcom_battmgr_set_charge_rate_behaviour(&b,1)==0 && requests==before+1);
 assert_packet(0);
 struct { struct pmic_glink_hdr hdr; __le32 result; } response={{32778,1,6},0};
 qcom_battmgr_charge_rate_ack(&b,&response,sizeof(response)); assert(b.error==0);
 response.result=1;
 qcom_battmgr_charge_rate_ack(&b,&response,sizeof(response)); assert(b.error==-EIO);
 qcom_battmgr_charge_rate_ack(&b,&response,sizeof(response)-1); assert(b.error==-ENODATA);
 qcom_battmgr_charge_rate_ack(&b,&response,sizeof(response)+1); assert(b.error==-ENODATA);
 assert(b.ack==4 && !b.lock && queries==5 && changes==4);
 puts("PASS: actual C 24-byte stop/resume packets, native-limit guard, transport failures, duplicate stop and 16-byte ACK validation");
}
'''
with tempfile.TemporaryDirectory(prefix='kpfe-rate-protocol-') as directory:
    folder = Path(directory)
    (folder / 'protocol.c').write_text(program)
    binary = folder / ('protocol.exe' if os.name == 'nt' else 'protocol')
    subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra',
                    '-Werror', str(folder / 'protocol.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
