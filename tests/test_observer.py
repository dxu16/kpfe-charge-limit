"""Regressions for the actual read-only observer's false-alarm conditions."""
import ast
from pathlib import Path
import unittest

TREE = ast.parse((Path(__file__).resolve().parents[1] /
                  'tools/observe-transition.py').read_text())


def assignment(name):
    return next(node.value for node in ast.walk(TREE) if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in node.targets))


def expression(name, **env):
    return eval(compile(ast.Expression(assignment(name)), '<observer-expression>', 'eval'), env)


def check(message, **env):
    node = next(node for node in ast.walk(TREE) if isinstance(node, ast.Assert)
                and isinstance(node.msg, ast.Constant) and node.msg.value == message)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<observer-validation>', 'exec'), env)


class Battery:
    def __init__(self, content, path=None):
        self.content, self.path = content, path

    def __truediv__(self, name):
        return Battery(self.content, name)

    def read_text(self):
        return self.content[self.path]


class ObserverTests(unittest.TestCase):
    def test_preserves_value_case(self):
        values = expression('values', bat=Battery({'uevent':
            'POWER_SUPPLY_HEALTH=Good\nPOWER_SUPPLY_STATUS=Full\n'
            'POWER_SUPPLY_CURRENT_NOW=-11597\nPOWER_SUPPLY_MODEL_NAME=CaseSensitive\n'}))
        self.assertEqual(values, dict(health='Good', status='Full',
                                     current_now='-11597', model_name='CaseSensitive'))

    def test_above_limit_initial_soc_is_allowed(self):
        ceiling = expression('capacity_ceiling', bat=Battery(
            {'capacity': '94', 'charge_control_end_threshold': '85'}))
        check('SOC increased beyond hold allowance', values={'capacity': '94'}, capacity_ceiling=ceiling)
        with self.assertRaises(AssertionError):
            check('SOC increased beyond hold allowance', values={'capacity': '96'}, capacity_ceiling=ceiling)

    def test_real_fault_and_persistent_charge_are_rejected(self):
        check('Persistent reported charging during limit hold', positive_hold=6)
        with self.assertRaises(AssertionError):
            check('Persistent reported charging during limit hold', positive_hold=7)
        health = next(node for node in ast.walk(TREE) if isinstance(node, ast.Assert)
                      and 'Health fault' in ast.unparse(node))
        code = compile(ast.fix_missing_locations(ast.Module(body=[health], type_ignores=[])),
                       '<observer-health>', 'exec')
        exec(code, {'values': {'health': 'Good'}})
        with self.assertRaises(AssertionError):
            exec(code, {'values': {'health': 'Over voltage'}})


if __name__ == '__main__':
    unittest.main()
