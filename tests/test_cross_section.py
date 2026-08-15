import unittest

from Qeoloog.cross_section import (
    elevation_range,
    point_at_station,
    polyline_length,
    project_to_polyline,
    section_positions,
)


class CrossSectionTests(unittest.TestCase):
    def test_point_is_projected_to_chainage_and_offset(self):
        station, offset, point = project_to_polyline(
            (60, 20), [(0, 0), (100, 0), (100, 100)]
        )
        self.assertAlmostEqual(station, 60)
        self.assertAlmostEqual(offset, 20)
        self.assertEqual(point, (60, 0))
        self.assertEqual(
            point_at_station([(0, 0), (100, 0), (100, 100)], 150),
            (100, 50),
        )

    def test_line_mode_orders_items_by_true_chainage(self):
        rows = section_positions([
            {"id": "B", "x": 80, "y": 2},
            {"id": "A", "x": 10, "y": -3},
        ], "line", [(0, 0), (100, 0)])
        self.assertEqual([row["id"] for row in rows], ["A", "B"])
        self.assertEqual([round(row["_station"]) for row in rows], [10, 80])

    def test_order_mode_uses_user_sequence(self):
        rows = section_positions([
            {"id": "B", "x": 100, "y": 0},
            {"id": "A", "x": 0, "y": 0},
            {"id": "C", "x": 100, "y": 100},
        ], "order")
        self.assertEqual([row["id"] for row in rows], ["B", "A", "C"])
        self.assertAlmostEqual(rows[-1]["_station"], 100 + 2 ** 0.5 * 100)
        self.assertAlmostEqual(polyline_length([(0, 0), (3, 4)]), 5)

    def test_elevation_range_uses_well_bottom_and_dem(self):
        minimum, maximum = elevation_range([
            {"elevation": 50, "depth": 30},
        ], [(0, 55), (10, 52)])
        self.assertLess(minimum, 20)
        self.assertGreater(maximum, 55)


if __name__ == "__main__":
    unittest.main()
