"""Generate a diagnostic-only backend from the previously tested manual harness."""
from pathlib import Path
import difflib,hashlib,json,re,shutil,subprocess,tempfile
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='kpfe-rate-prepare-') as directory:
    tree=Path(directory)/'kernel'
    shutil.copytree(root/'src/base',tree)
    subprocess.run(['git','-c','core.autocrlf=false','apply',
                    str(Path(__file__).with_name('input-manual.patch'))],cwd=tree,check=True)
    data=(tree/'drivers/power/supply/qcom_battmgr.c').read_bytes()
assert hashlib.sha256(data).hexdigest()=='092d80ab1eaae4b6afc1ab9feea0887ea8f0a1c5d9d226273c1178f54048b984'
s=data.decode()
s=s.replace('#define BATT_OEM_CHARGE_ONLINE\t\t29\n', '')
assert 'BATT_OEM_CHARGE_ONLINE' in s  # References are removed below.
s=s.replace('#define BATTMGR_BAT_STATUS', '#define BATTMGR_SET_CHARGE_RATE\t\t0x6\n\n#define BATTMGR_BAT_STATUS',1)
s=s.replace('struct qcom_battmgr_charge_ctrl_request {', '''struct qcom_battmgr_charge_rate_request {
\tstruct pmic_glink_hdr hdr;
\t__le32 battery_id;
\t__le32 charge_rate;
\t__le32 charging_path;
};

struct qcom_battmgr_charge_ctrl_request {''',1)
s=s.replace('bool oem_charge_online;', 'bool charge_rate_inhibited;')
s,n=re.subn(r'\tint ret;\n\n\tif \(battmgr->oem_bypass_supported && target_soc < CHARGE_CTRL_END_THR_MAX\) \{.*?\n\t}\n\n\treturn qcom_battmgr_request\(battmgr, &request, sizeof\(request\)\);',
lambda m:'''\tif (battmgr->oem_bypass_supported && battmgr->charge_rate_inhibited &&
\t    target_soc < CHARGE_CTRL_END_THR_MAX)
\t\treturn -EBUSY;

\treturn qcom_battmgr_request(battmgr, &request, sizeof(request));''',s,count=1,flags=re.S)
assert n==1
s=s.replace('/* Caller holds lock; read firmware state before every possible transition. */',
'''/* Diagnostic readback is the last acknowledged request, not hardware state. */''')
get='''static int qcom_battmgr_get_oem_charge_behaviour(struct qcom_battmgr *battmgr,
\t\t\t\t\t       union power_supply_propval *val)
{
\tif (!battmgr->oem_bypass_supported)
\t\treturn -EOPNOTSUPP;

\tval->intval = battmgr->charge_rate_inhibited ?
\t\tPOWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE :
\t\tPOWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO;
\treturn 0;
}
'''
s,n=re.subn(r'static int qcom_battmgr_get_oem_charge_behaviour\(.*?\n}\n',lambda m:get,s,count=1,flags=re.S);assert n==1
setter='''static int qcom_battmgr_set_oem_charge_behaviour(struct qcom_battmgr *battmgr,
\t\t\t\t\t       int behaviour)
{
\tstruct qcom_battmgr_charge_rate_request request = {
\t\t.hdr.owner = cpu_to_le32(PMIC_GLINK_OWNER_BATTMGR),
\t\t.hdr.type = cpu_to_le32(PMIC_GLINK_REQ_RESP),
\t\t.hdr.opcode = cpu_to_le32(BATTMGR_SET_CHARGE_RATE),
\t\t.battery_id = cpu_to_le32(0),
\t\t.charging_path = cpu_to_le32(0),
\t};
\tint ret;

\tif (!battmgr->oem_bypass_supported)
\t\treturn -EOPNOTSUPP;
\tif (behaviour != POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO &&
\t    behaviour != POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE)
\t\treturn -EINVAL;

\trequest.charge_rate = cpu_to_le32(behaviour ==
\t\tPOWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO ? 100 : 0);
\tmutex_lock(&battmgr->lock);
\t/* The diagnostic must not mix this command with native percentage limiting. */
\tif (behaviour == POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE) {
\t\tret = qcom_battmgr_request_property(battmgr, BATTMGR_BAT_PROPERTY_GET,
\t\t\t\t\t\t    BATT_CHG_CTRL_EN, 0);
\t\tif (ret)
\t\t\tgoto out;
\t\tif (battmgr->native_charge_limit_enabled) {
\t\t\tret = -EBUSY;
\t\t\tgoto out;
\t\t}
\t}
\tret = qcom_battmgr_request(battmgr, &request, sizeof(request));
\tif (!ret)
\t\tbattmgr->charge_rate_inhibited =
\t\t\tbehaviour == POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
out:
\tmutex_unlock(&battmgr->lock);
\tif (!ret)
\t\tpower_supply_changed(battmgr->bat_psy);
\treturn ret > 0 ? -EIO : ret;
}
'''
s,n=re.subn(r'static int qcom_battmgr_set_oem_charge_behaviour\(.*?\n}\n',lambda m:setter,s,count=1,flags=re.S);assert n==1
s=s.replace('\t\tcase BATT_OEM_CHARGE_ONLINE:\n','')
s=s.replace('''\t\t\tif (property == BATT_OEM_CHARGE_ONLINE)
\t\t\t\tbattmgr->oem_charge_online = val;
\t\t\telse
\t\t\t\tbattmgr->native_charge_limit_enabled = val;''','''\t\t\tbattmgr->native_charge_limit_enabled = val;''')
assert 'BATT_OEM_CHARGE_ONLINE' not in s
ack='''static void qcom_battmgr_charge_rate_ack(struct qcom_battmgr *battmgr,
\t\t\t\t\tconst void *data, size_t len)
{
\tconst struct {
\t\tstruct pmic_glink_hdr hdr;
\t\t__le32 result;
\t} *response = data;

\tif (len != sizeof(*response))
\t\tbattmgr->error = -ENODATA;
\telse
\t\tbattmgr->error = le32_to_cpu(response->result) ? -EIO : 0;
\tcomplete(&battmgr->ack);
}

'''
s=s.replace('static void qcom_battmgr_callback(',ack+'static void qcom_battmgr_callback(',1)
s=s.replace('''\tif (opcode == BATTMGR_NOTIFICATION)
\t\tqcom_battmgr_notification(battmgr, data, len);''','''\tif (opcode == BATTMGR_SET_CHARGE_RATE && battmgr->oem_bypass_supported)
\t\tqcom_battmgr_charge_rate_ack(battmgr, data, len);
\telse if (opcode == BATTMGR_NOTIFICATION)
\t\tqcom_battmgr_notification(battmgr, data, len);''',1)
for old,new in [('oem_bypass_supported','charge_rate_supported'),
                ('get_oem_charge_behaviour','get_charge_rate_behaviour'),
                ('set_oem_charge_behaviour','set_charge_rate_behaviour'),
                ('qcom_battmgr_oem_battery_desc','qcom_battmgr_charge_rate_battery_desc')]:
    s=s.replace(old,new)
out=Path(__file__).parent
(out/'qcom_battmgr.c').write_text(s,newline='\n')
base=(root/'src/base/drivers/power/supply/qcom_battmgr.c').read_text()
patch=''.join(difflib.unified_diff(base.splitlines(True),s.splitlines(True),
    fromfile='a/drivers/power/supply/qcom_battmgr.c',tofile='b/drivers/power/supply/qcom_battmgr.c'))
patch='''Subject: [DIAGNOSTIC] power: supply: qcom_battmgr: test KPFE charge-rate stop

Exercise the firmware charge-rate command through a KPFE-only manual
charge_behaviour interface. Rate zero enters the firmware stop-state path;
rate 100 releases it. Reject mixing with native percentage limiting and
validate the command's distinct acknowledgment payload.

This is an untested diagnostic backend, not the automatic charge-limit fix.

diff --git a/drivers/power/supply/qcom_battmgr.c b/drivers/power/supply/qcom_battmgr.c
'''+patch
(out/'charge-rate-diagnostic.patch').write_text(patch,newline='\n')
meta={'kind':'manual diagnostic only; no automatic percentage policy',
      'base_source_sha256':hashlib.sha256(base.encode()).hexdigest(),
      'source_sha256':hashlib.sha256(s.encode()).hexdigest(),
      'hardware_tested':False,'installed_or_loaded':False,
      'firmware_opcode':6,'request_bytes':24,'response_bytes':16,
      'stop_rate':0,'resume_rate':100,'charging_path':0,
      'kernel_patch_additions':sum(l.startswith('+') and not l.startswith('+++') for l in patch.splitlines()),
      'kernel_patch_deletions':sum(l.startswith('-') and not l.startswith('---') for l in patch.splitlines())}
(out/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n',newline='\n')
print(json.dumps(meta,indent=2))
