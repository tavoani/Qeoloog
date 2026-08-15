import unittest

from Qeoloog.leapfrog import (
    compound_index,
    hole_identifier,
    interval_row,
    latest_row,
    safe_column,
    vertical_survey,
)


class LeapfrogHelpersTest(unittest.TestCase):
    def test_compound_index_joins_lower_and_upper(self):
        self.assertEqual(
            compound_index({
                "indeks": "Liitüksus",
                "liityksus_indeks_alumine": "O3mo",
                "liityksus_indeks_ylemine": "O3adl",
            }),
            "O3mo-O3adl",
        )

    def test_compound_index_ignores_unknown_part(self):
        self.assertEqual(
            compound_index({
                "indeks": "Liitüksus",
                "liityksus_indeks_alumine": "O3mo",
                "liityksus_indeks_ylemine": "Teadmata",
            }),
            "O3mo",
        )

    def test_source_qualified_ids_do_not_collide(self):
        self.assertEqual(
            hole_identifier("EGT", "boreholes", {"gea_id": 12}),
            "EGT_PA_12",
        )
        self.assertEqual(
            hole_identifier("VEKA", "veka_boreholes", {"kkr_kood": "PRK12"}),
            "VEKA_PRK12",
        )

    def test_vertical_survey_uses_leapfrog_default_convention(self):
        self.assertEqual(vertical_survey("A")["Dip"], 90.0)

    def test_invalid_interval_is_omitted(self):
        self.assertIsNone(interval_row("A", 10, 5))
        self.assertIsNone(interval_row("A", "", 5))

    def test_latest_row_requires_numeric_value(self):
        row = latest_row([
            {"katse_kp": "2020-01-01", "st_veetase": 2},
            {"katse_kp": "2024-01-01", "st_veetase": None},
            {"katse_kp": "2023-01-01", "st_veetase": 3},
        ], "st_veetase")
        self.assertEqual(row["st_veetase"], 3)

    def test_safe_analysis_column(self):
        self.assertEqual(safe_column("Baarium [mg/l]"), "Baarium_mg_l")


if __name__ == "__main__":
    unittest.main()
