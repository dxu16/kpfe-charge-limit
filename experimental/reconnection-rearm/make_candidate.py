"""Prepare an uninstalled revision of the tested source for review and tests."""
import hashlib
import difflib
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
with tempfile.TemporaryDirectory(prefix='kpfe-original-candidate-') as tmp:
    kernel = Path(tmp) / 'kernel'
    shutil.copytree(ROOT / 'src/base', kernel)
    subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply',
                    str(ROOT / 'history/pre-reconnection-candidate/charge-limit.patch')],
                   cwd=kernel, check=True)
    base = kernel / 'drivers/power/supply/qcom_battmgr.c'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == 'd84cef5a94aafe4f1e2b7997f902f3b7818f8fdf8753bd200ec19d50c626a345'
    base_code = base.read_text()
code = base_code


def replace(old, new):
    global code
    assert code.count(old) == 1, old
    code = code.replace(old, new)


replace('#include <linux/devm-helpers.h>', '#include <linux/delay.h>\n#include <linux/devm-helpers.h>\n#include <linux/jiffies.h>')
replace('\tstruct delayed_work host_work;', '\tstruct delayed_work host_work;\n\tbool host_holding;\n\tbool host_rearmed;\n\tunsigned long host_verify_after;')
replace('\tbattmgr->host_ready = true;', '\tbattmgr->host_holding = false;\n\tbattmgr->host_rearmed = false;\n\tbattmgr->host_ready = true;')
helpers = r'''
/* The caller holds the request mutex. Avoid overwriting saved bypass current. */
static int qcom_battmgr_host_set_online(struct qcom_battmgr *battmgr, bool online)
{
	int ret;

	ret = qcom_battmgr_host_get(battmgr, BATTMGR_BAT_PROPERTY_GET,
				 BATT_OEM_CHARGE_ONLINE);
	/* A failed read must not skip stopping after a confirmed release. */
	if (ret && (online || !battmgr->oem_charge_online))
		return ret;
	if (!ret && battmgr->oem_charge_online == online)
		return 0;
	ret = qcom_battmgr_request_property(battmgr, BATTMGR_BAT_PROPERTY_SET,
					    BATT_OEM_CHARGE_ONLINE, online);
	if (ret)
		return ret > 0 ? -EIO : ret;
	ret = qcom_battmgr_host_get(battmgr, BATTMGR_BAT_PROPERTY_GET,
				 BATT_OEM_CHARGE_ONLINE);
	if (!ret && battmgr->oem_charge_online != online)
		ret = -EIO;
	return ret;
}

/* Reconcile a stale hold once; do not leave normal charging selected on error. */
static int qcom_battmgr_host_rearm(struct qcom_battmgr *battmgr)
{
	unsigned long deadline = jiffies + msecs_to_jiffies(2000);
	int ret, stop_ret;

	ret = qcom_battmgr_host_set_online(battmgr, true);
	while (!ret) {
		ret = qcom_battmgr_host_get(battmgr, BATTMGR_BAT_PROPERTY_GET,
					 BATT_CHG_CTRL_LIM);
		if (ret || battmgr->info.charge_current_limit)
			break;
		if (time_after_eq(jiffies, deadline)) {
			ret = -ETIMEDOUT;
			break;
		}
		msleep(50);
	}
	stop_ret = qcom_battmgr_host_set_online(battmgr, false);
	return ret ? ret : stop_ret;
}

'''.replace('\\t', '\t')
replace('static void qcom_battmgr_host_worker(struct work_struct *work)', helpers + 'static void qcom_battmgr_host_worker(struct work_struct *work)')
replace('\tbool charging, changed = false, retry = false;\n\tint ret = 0;', '\tbool charging, changed = false, retry = false;\n\tunsigned long delay = 60 * HZ;\n\tint ret = 0;')
verification = r'''
	if (charging) {
		battmgr->host_holding = false;
		battmgr->host_rearmed = false;
	} else {
		if (!battmgr->host_holding) {
			battmgr->host_holding = true;
			battmgr->host_verify_after = jiffies + 5 * HZ;
		}
		if (time_before(jiffies, battmgr->host_verify_after)) {
			delay = battmgr->host_verify_after - jiffies;
		} else {
			ret = qcom_battmgr_host_get(battmgr, BATTMGR_BAT_PROPERTY_GET,
						 BATT_CURR_NOW);
			if (ret)
				goto out;
			/* Gauge readings can lag a successful hardware stop. */
			if (battmgr->status.current_now > 50000) {
				if (battmgr->host_rearmed) {
					ret = -EIO;
					goto out;
				}
				battmgr->host_rearmed = true;
				ret = qcom_battmgr_host_rearm(battmgr);
				battmgr->host_verify_after = jiffies + 5 * HZ;
				delay = 5 * HZ;
				changed = true;
				if (ret)
					goto out;
			}
		}
	}
'''.replace('\\t', '\t')
replace('\t\tchanged = true;\n\t}\n', '\t\tchanged = true;\n\t\tif (!charging)\n\t\t\tbattmgr->host_holding = false;\n\t}\n')
replace('\tbattmgr->host_restart = false;\n\tretry = battmgr->usb.online', verification + '\tbattmgr->host_restart = false;\n\tretry = battmgr->usb.online')
replace('queue_delayed_work(system_wq, &battmgr->host_work, 60 * HZ);', 'queue_delayed_work(system_wq, &battmgr->host_work, delay);')
candidate = HERE / 'qcom_battmgr.c'
candidate.write_text(code, newline='\n')
path = 'drivers/power/supply/qcom_battmgr.c'
patch = f'diff --git a/{path} b/{path}\n' + ''.join(difflib.unified_diff(
    base_code.splitlines(keepends=True), code.splitlines(keepends=True),
    fromfile=f'a/{path}', tofile=f'b/{path}'))
(HERE / 'reconnection-rearm.patch').write_text(patch, newline='\n')
print('Regenerated source and incremental diff; no device action performed.')
