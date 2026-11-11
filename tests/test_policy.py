"""Exercise the actual production C decision function without charging hardware."""
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
match = re.search(r'static bool qcom_battmgr_host_should_charge\(.*?\n}\n', source, re.S)
assert match
program = '''#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define CHARGE_CTRL_END_THR_MAX 100
''' + match.group(0) + r'''
static bool step(unsigned int soc, unsigned int start, unsigned int end,
                 bool plugged, bool state, bool restart, unsigned int *writes)
{
    bool next = qcom_battmgr_host_should_charge(soc, start, end, plugged,
                                               restart || state);
    if (next != state)
        ++*writes;
    return next;
}

int main(void)
{
    unsigned int writes = 0;
    bool state = true;
    size_t cases = 0;

    /* Charge from below to85, hold through the hysteresis band, resume at70. */
    for (unsigned int soc = 80; soc <= 85; ++soc)
        state = step(soc, 70, 85, true, state, false, &writes);
    assert(!state && writes == 1);
    for (unsigned int soc = 85; soc > 70; --soc)
        state = step(soc, 70, 85, true, state, false, &writes);
    assert(!state && writes == 1);
    state = step(70, 70, 85, true, state, false, &writes);
    assert(state && writes == 2);

    /* Plugging in above the stop point must inhibit immediately. */
    state = step(90, 70, 85, false, false, false, &writes);
    assert(state);
    state = step(90, 70, 85, true, state, false, &writes);
    assert(!state);

    /* Raising85 to92 must resume at90, then stop when92 is reached. */
    state = step(90, 70, 92, true, state, true, &writes);
    assert(state);
    state = step(91, 70, 92, true, state, false, &writes);
    assert(state);
    state = step(92, 70, 92, true, state, false, &writes);
    assert(!state);
    unsigned int stopped_writes = writes;
    for (unsigned int i = 0; i < 100; ++i)
        state = step(92, 70, 92, true, state, false, &writes);
    assert(!state && writes == stopped_writes);

    /* Off releases bypass even at100; lowering the limit inhibits. */
    state = step(100, 70, 100, true, state, true, &writes);
    assert(state);
    state = step(90, 70, 85, true, state, true, &writes);
    assert(!state);

    for (unsigned int start = 50; start <= 95; ++start)
        for (unsigned int end = 55; end <= 100; ++end) {
            if (start > end)
                continue;
            for (unsigned int soc = 0; soc <= 100; ++soc)
                for (unsigned int plugged = 0; plugged <= 1; ++plugged)
                    for (unsigned int previous = 0; previous <= 1; ++previous) {
                        bool next = qcom_battmgr_host_should_charge(soc, start, end,
                                                                   plugged, previous);
                        if (!plugged || end == 100)
                            assert(next);
                        else if (soc >= end)
                            assert(!next);
                        else if (soc <= start)
                            assert(next);
                        else
                            assert(next == (bool)previous);
                        ++cases;
                    }
        }
    printf("PASS: charge-up, hysteresis, reconnect, changed target, off and duplicate-event trajectories\n");
    printf("PASS: %zu boundary/state combinations\n", cases);
    return 0;
}
'''
(output / 'test-policy.c').write_text(program)
subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                str(output / 'test-policy.c'), '-o', str(output / 'test-policy')], check=True)
result = subprocess.run([str(output / 'test-policy')], text=True, capture_output=True, check=True)
(output / 'policy-tests.txt').write_text(result.stdout)
print(result.stdout)
