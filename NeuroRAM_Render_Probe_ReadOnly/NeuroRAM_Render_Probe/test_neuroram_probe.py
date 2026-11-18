import math
import struct
import unittest
from neuroram_probe import FRAME_BYTES, analyze_frame, HOSTS

class ProbeTests(unittest.TestCase):
    def test_published_hosts(self):
        self.assertEqual(len(HOSTS), 2)
        self.assertTrue(all(h.startswith('https://') for h in HOSTS))
    def test_valid_empty_32_channel_packet(self):
        r = analyze_frame(bytes(FRAME_BYTES))
        self.assertEqual(r['wire_channels'], 32)
        self.assertEqual(r['saved_channels'], 32)
        self.assertEqual(r['rms_source_units'], 0)
        self.assertFalse(r['independent_biological_verification'])
    def test_128_channel_selects_requested_block(self):
        data = bytearray(FRAME_BYTES * 4)
        struct.pack_into('<f', data, FRAME_BYTES * 3, 15)
        r = analyze_frame(data, 4)
        self.assertEqual(r['wire_channels'], 128)
        self.assertEqual(r['max_source_units'], 15)
        r2 = analyze_frame(data, 1)
        self.assertEqual(r2['max_source_units'], 0)
        self.assertNotEqual(r['sha256'], r2['sha256'])
    def test_reject_wrong_geometry(self):
        for sample in (b'', b'bad', bytes(FRAME_BYTES + 4)):
            with self.assertRaises(ValueError):
                analyze_frame(sample)
    def test_reject_nan_inf(self):
        for value in [float('nan'), float('inf'), -float('inf')]:
            sample = bytearray(FRAME_BYTES)
            struct.pack_into('<f', sample, 0, value)
            with self.assertRaises(ValueError):
                analyze_frame(sample)

if __name__ == '__main__':
    unittest.main()
