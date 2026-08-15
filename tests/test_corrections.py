import unittest

from Qeoloog.corrections import (
    apply_core_values,
    changed_core_values,
    core_correction_key,
    core_values,
)


class CorrectionTests(unittest.TestCase):
    def test_egt_roundtrip(self):
        source = {
            "globalid": "{ABC}",
            "kast_nr": "12",
            "z_suht_ylemine": None,
            "z_suht_alumine": 20,
            "diameeter": 50,
            "staatus": "olemas",
        }
        self.assertEqual(core_correction_key("EGT", source), "EGT:{ABC}")
        values = core_values("EGT", source)
        values["top"] = 10.5
        corrected = apply_core_values("EGT", source, values)
        self.assertEqual(corrected["z_suht_ylemine"], 10.5)

    def test_sarv_mapping(self):
        source = {"id": 99, "number": "A", "depth_start": 1, "depth_end": 2}
        corrected = apply_core_values(
            "SARV", source, {"top": 1.25, "status": "Tartu"}
        )
        self.assertEqual(corrected["depth_start"], 1.25)
        self.assertEqual(corrected["_qeoloog_status"], "Tartu")

    def test_only_real_changes_are_retained(self):
        original = {"number": " 1 ", "top": None, "bottom": "5"}
        corrected = {"number": "1", "top": 2, "bottom": 5.0}
        self.assertEqual(
            changed_core_values(original, corrected),
            {"top": 2},
        )


if __name__ == "__main__":
    unittest.main()
