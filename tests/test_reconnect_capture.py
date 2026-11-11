"""Check exact diagnostic register parsing and preservation of battery values."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'tools/capture-reconnect-state.py'
spec = importlib.util.spec_from_file_location('reconnect_capture', path)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def test_preserves_values(self):
        self.assertEqual(capture.parse_uevent('POWER_SUPPLY_HEALTH=Good\n'
            'POWER_SUPPLY_STATUS=Charging\nPOWER_SUPPLY_CURRENT_NOW=294198\n'),
            dict(health='Good', status='Charging', current_now='294198'))

    def test_reads_exact_register_line(self):
        self.assertEqual(capture.decode_register(b'2654: 06\n', 0x2654), 6)
        self.assertEqual(capture.decode_register(b'2646: 00\n', 0x2646), 0)
        for raw in (b'2655: 06\n', b'2654: XX\n', b'2654: 06', b'2654: 006\n'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                capture.decode_register(raw, 0x2654)

    def test_register_whitelist(self):
        self.assertEqual(set(capture.REGISTERS), {0x2606, 0x2646, 0x2650, 0x2654, 0x2658})


if __name__ == '__main__':
    unittest.main()
