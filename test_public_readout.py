import unittest
from public_readout import choose_public_selection

class PublicReadoutTests(unittest.TestCase):
    def test_eligible_public_controller_uses_published_channel_indices(self):
        controllers = [{"_id": "public-controller", "online": True, "maintenance": False,
            "channels": [32, 0, 0, 0], "electrode_layout": [
                {"mea_index": 0, "channel_index": 7}, {"mea_index": 0, "channel_index": 1}]}]
        payload, info = choose_public_selection(controllers, 1600)
        self.assertEqual(payload, {"id_intan": "public-controller", "mea_index": 0, "channel_index": [1, 7]})
        self.assertEqual(info["status"], "eligible_public_view_controller_found")

    def test_maintenance_controller_not_selected(self):
        controllers = [{"_id": 2, "online": True, "maintenance": True, "channels": [32]}]
        payload, info = choose_public_selection(controllers, 1600)
        self.assertIsNone(payload)
        self.assertEqual(info["status"], "no_online_nonmaintenance_controller")

    def test_offline_controller_not_selected(self):
        controllers = [{"_id": 2, "online": False, "maintenance": False, "channels": [32]}]
        self.assertIsNone(choose_public_selection(controllers, 1600)[0])

    def test_avoids_empty_sample_window(self):
        controllers = [{"_id": 2, "online": True, "maintenance": False, "channels": [32]}]
        self.assertIsNone(choose_public_selection(controllers, 0)[0])

    def test_fallback_first_eight_public_channels(self):
        controllers = [{"_id": 2, "online": True, "maintenance": False, "channels": [32]}]
        payload, _ = choose_public_selection(controllers, 1600)
        self.assertEqual(payload["channel_index"], list(range(8)))

if __name__ == "__main__":
    unittest.main()
