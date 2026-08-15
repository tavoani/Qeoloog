import unittest

from Qeoloog.veka import (
    aggregate,
    analysis_codes,
    analysis_key,
    analysis_matches,
    analysis_options,
    analysis_row_value,
    cadastral_number,
    construction_category,
    converted_result,
    equal_breaks,
    hydro_matches,
    interval_intersects,
    latest_static_water_level,
    merge_water_analyses,
    parse_kotkas_protocols,
    parse_kotkas_report_registry,
    parse_veka_water_analyses,
    quantile_breaks,
    specific_capacity,
)


class VekaLogicTests(unittest.TestCase):
    def test_chemistry_key_falls_back_to_prk_registry_code(self):
        self.assertEqual(cadastral_number("007232"), "7232")
        self.assertEqual(cadastral_number("7232.0"), "7232")
        self.assertEqual(cadastral_number(None, "PRK0007232"), "7232")
        self.assertEqual(cadastral_number("NULL", "<NULL>"), "")

    def test_construction_codes_are_grouped_for_detail_view(self):
        self.assertEqual(construction_category("P"), "drill")
        self.assertEqual(construction_category("manteltoru_PVC"), "casing")
        self.assertEqual(construction_category("perfofilter"), "filter")
        self.assertEqual(construction_category("filtrita"), "open")
        self.assertEqual(construction_category("manteldamata"), "open")
        self.assertEqual(construction_category("unknown"), "other")

    def test_legacy_veka_water_analysis_is_parsed(self):
        rows = parse_veka_water_analyses("""
            <h6>Veeproovi analüüsi akt 2140255904, 25.06.2007</h6>
            <table>
              <tr><th>Nimetus</th><th>Tulemus</th><th>Ühik</th></tr>
              <tr><td>Baarium</td><td>&lt;0.2</td><td>mg/l</td></tr>
            </table>
        """, "https://veka.eelis.ee/puurauk/PRK0021987")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["analyys_number"], "2140255904")
        self.assertEqual(rows[0]["naitaja_tulem"], "<0.2")
        self.assertEqual(rows[0]["_protocol_label"], "VEKA")

    def test_kotkas_registry_and_protocol_file_are_parsed(self):
        reports = parse_kotkas_report_registry("""
            <table><tr>
              <td>01.01.2016</td><td>31.12.2018</td>
              <td><a href="/permits/public_assignment_view?id=267">Ava</a></td>
            </tr></table>
        """)
        self.assertEqual(
            reports[("2016-01-01", "2018-12-31")],
            "https://kotkas.envir.ee/permits/public_assignment_view?id=267",
        )
        protocols = parse_kotkas_protocols("""
            <table><tr>
              <td data-id="app:t:AS_WATER_10_SELF_T:0:AS_WATER_10_SELF_T_AnalyysiNumber">J-347</td>
              <td data-id="app:t:AS_WATER_10_SELF_T:0:AS_WATER_10_SELF_T_Failid">
                <a href="/permit_assignments/forms_file_download?file_id=261">J-347.asice</a>
              </td>
            </tr></table>
        """)
        self.assertEqual(
            protocols["j347"][0]["url"],
            "https://kotkas.envir.ee/permit_assignments/forms_file_download?file_id=261",
        )

    def test_primary_water_rows_take_precedence_over_legacy_duplicates(self):
        primary = [{
            "proov_algus": "2007-06-25", "naitaja_nimi": "Baarium",
            "naitaja_tulem": "<0.2", "naitaja_yhik": "mg/l",
        }]
        legacy = [{
            "proov_algus": "25.06.2007", "naitaja_nimi": "Baarium",
            "naitaja_tulem": "<0,2", "naitaja_yhik": "mg/l",
        }, {
            "proov_algus": "25.06.2007", "naitaja_nimi": "Kloriid",
            "naitaja_tulem": "12", "naitaja_yhik": "mg/l",
        }]
        self.assertEqual(len(merge_water_analyses(primary, legacy)), 2)

    def test_qualified_results_keep_detection_limit_after_conversion(self):
        self.assertEqual(converted_result("<200", "µg/l", "Baarium"), ("<0.2", "mg/l"))
        self.assertEqual(converted_result("0,25", "mg/l", "Baarium"), (0.25, "mg/l"))

    def test_filter_interval_intersection_is_inclusive(self):
        self.assertTrue(interval_intersects(10, 30, 30, 40))
        self.assertTrue(interval_intersects(30, 10, 20, 25))
        self.assertFalse(interval_intersects(10, 19.9, 20, 30))

    def test_specific_capacity_rejects_zero_drawdown(self):
        self.assertAlmostEqual(
            specific_capacity({"deebit": 7.78, "alandus": 5.6}), 1.3892857,
            places=6,
        )
        self.assertIsNone(specific_capacity({"deebit": 2, "alandus": 0}))

    def test_latest_valid_static_water_level_is_selected(self):
        row = latest_static_water_level([
            {"katse_kp": "2024-01-01", "st_veetase": None},
            {"katse_kp": "2023-06-01", "st_veetase": 4.2},
            {"katse_kp": "2020-01-01", "st_veetase": 3.7},
        ])
        self.assertEqual(row["st_veetase"], 4.2)

    def test_hydro_any_requires_same_test_to_match_both_metrics(self):
        rows = [
            {"deebit": 10, "alandus": 10, "katse_kp": "2020-01-01"},
            {"deebit": 2, "alandus": 0.2, "katse_kp": "2021-01-01"},
        ]
        self.assertFalse(hydro_matches(rows, {
            "hydro_mode": "any", "debit_min": 8, "debit_max": None,
            "specific_min": 5, "specific_max": None,
        }))
        self.assertTrue(hydro_matches(rows, {
            "hydro_mode": "latest", "debit_min": None, "debit_max": 3,
            "specific_min": 5, "specific_max": None,
        }))

    def test_hydro_latest_uses_one_complete_test(self):
        rows = [
            {"deebit": 8, "alandus": 4, "katse_kp": "2020-01-01"},
            {"deebit": 2, "alandus": None, "katse_kp": "2024-01-01"},
        ]
        self.assertTrue(hydro_matches(rows, {
            "hydro_mode": "latest", "debit_min": 7, "debit_max": 9,
            "specific_min": 1.5, "specific_max": 2.5,
        }))

    def test_latest_aggregation_uses_dated_record(self):
        rows = [
            {"value": 5, "date": "2020-01-01"},
            {"value": 3, "date": "2024-01-01"},
        ]
        self.assertEqual(
            aggregate(rows, lambda row: row["value"], "latest", "date"), 3,
        )

    def test_analysis_filter_can_limit_sampling_year(self):
        rows = [
            {
                "naitaja_kood": "NO3", "naitaja_yhik": "mg/l",
                "naitaja_tulem": 42,
                "proov_algus": "04.09.2018",
            },
            {
                "naitaja_kood": "NO3", "naitaja_yhik": "mg/l",
                "naitaja_tulem": 12,
                "proov_algus": "2024-05-01",
            },
        ]
        self.assertFalse(analysis_matches(rows, {
            "analysis_code": analysis_key("NO3", "mg/l"),
            "analysis_mode": "any",
            "analysis_min": 40, "analysis_max": None,
            "analysis_year_min": 2020, "analysis_year_max": None,
        }))
        self.assertTrue(analysis_matches(rows, {
            "analysis_code": analysis_key("NO3", "mg/l"),
            "analysis_mode": "latest",
            "analysis_min": 10, "analysis_max": 20,
            "analysis_year_min": None, "analysis_year_max": None,
        }))
        self.assertTrue(analysis_matches(rows, {
            "analysis_code": analysis_key("NO3", "µg/l"),
            "analysis_mode": "any", "analysis_min": 11999,
            "analysis_max": 12001, "analysis_year_min": 2020,
            "analysis_year_max": None,
        }))

    def test_analysis_options_combine_convertible_mass_units(self):
        options = analysis_options([
            {"naitaja_kood": "Pb", "naitaja_nimi": "Plii", "naitaja_yhik": "mg/l"},
            {"naitaja_kood": "Pb", "naitaja_nimi": "Plii", "naitaja_yhik": "µg/l"},
            {"naitaja_kood": "Pb", "naitaja_nimi": "Plii", "naitaja_yhik": "ug/l"},
        ])
        self.assertEqual(len(options), 1)
        key, label = options[0]
        self.assertEqual(label, "Plii [mg/l]")
        self.assertAlmostEqual(analysis_row_value({
            "naitaja_kood": "Pb", "naitaja_nimi": "Plii",
            "naitaja_yhik": "µg/l", "naitaja_tulem": 250,
        }, key), 0.25)

    def test_microbiology_unit_spellings_share_one_search_option(self):
        options = analysis_options([
            {"naitaja_kood": "Coli.Bakt", "naitaja_nimi": "Coli-laadsed bakterid", "naitaja_yhik": "PMÜ/100 ml"},
            {"naitaja_kood": "Coli.Bakt", "naitaja_nimi": "Coli-laadsed bakterid", "naitaja_yhik": "MPN/100ml"},
            {"naitaja_kood": "Coli.Bakt", "naitaja_nimi": "Coli-laadsed bakterid", "naitaja_yhik": "arv/100 ml"},
            {"naitaja_kood": "Coli.Bakt", "naitaja_nimi": "Coli-laadsed bakterid", "naitaja_yhik": "ml"},
        ])
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0][1], "Coli-laadsed bakterid [arv/100 ml]")

    def test_known_alias_codes_are_merged_but_reused_code_names_are_not(self):
        options = analysis_options([
            {"naitaja_kood": "Enterok", "naitaja_nimi": "Enterokokid", "naitaja_yhik": "PMÜ/100 ml"},
            {"naitaja_kood": "Enterokokid", "naitaja_nimi": "Enterokokid", "naitaja_yhik": "arv/100ml"},
            {"naitaja_kood": "Enterok", "naitaja_nimi": "Soole enterokokid", "naitaja_yhik": "PMÜ/100 ml"},
        ])
        ordinary = next(item for item in options if item[1].startswith("Enterokokid ["))
        intestinal = next(item for item in options if item[1].startswith("Soole enterokokid ["))
        self.assertEqual(set(analysis_codes(ordinary[0])), {"Enterok", "Enterokokid"})
        self.assertEqual(analysis_codes(intestinal[0]), ("Enterok",))
        self.assertIsNone(analysis_row_value({
            "naitaja_kood": "Enterok", "naitaja_nimi": "Enterokokid",
            "naitaja_yhik": "PMÜ/100 ml", "naitaja_tulem": 1,
        }, intestinal[0]))

    def test_nonconvertible_unit_and_generic_names_remain_separate(self):
        options = analysis_options([
            {"naitaja_kood": "Cl", "naitaja_nimi": "Kloriid", "naitaja_yhik": "mg/l"},
            {"naitaja_kood": "Cl", "naitaja_nimi": "Kloriid", "naitaja_yhik": "g/100g"},
            {"naitaja_kood": "puudub", "naitaja_nimi": "Enterokokid", "naitaja_yhik": "PMÜ/100 ml"},
            {"naitaja_kood": "puudub", "naitaja_nimi": "Elektrijuhtivus", "naitaja_yhik": "µS/cm"},
        ])
        self.assertEqual(len(options), 4)

    def test_class_breaks_are_monotonic_and_end_at_maximum(self):
        values = [1, 2, 2, 3, 10]
        for breaks in (quantile_breaks(values, 4), equal_breaks(values, 4)):
            self.assertEqual(breaks, sorted(set(breaks)))
            self.assertEqual(breaks[-1], 10)


if __name__ == "__main__":
    unittest.main()
