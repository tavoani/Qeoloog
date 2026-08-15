"""Pure geometry and data helpers for Qeoloog multi-well cross-sections."""

from math import hypot


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def polyline_length(points):
    """Return the planar length of a sequence of ``(x, y)`` points."""
    return sum(
        hypot(b[0] - a[0], b[1] - a[1])
        for a, b in zip(points, points[1:])
    )


def point_at_station(points, station):
    """Return the point at a planar chainage along a polyline."""
    if not points:
        return None
    remaining = max(0.0, float(station))
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if remaining <= length or not length:
            fraction = remaining / length if length else 0.0
            return (
                start[0] + fraction * dx,
                start[1] + fraction * dy,
            )
        remaining -= length
    return points[-1]


def project_to_polyline(point, line):
    """Return ``(station, offset, projected_point)`` for the nearest segment."""
    if not point or not line:
        return 0.0, 0.0, point
    if len(line) == 1:
        return 0.0, hypot(point[0] - line[0][0], point[1] - line[0][1]), line[0]
    best = None
    station_base = 0.0
    for start, end in zip(line, line[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        length = hypot(dx, dy)
        if length_squared:
            fraction = max(
                0.0,
                min(
                    1.0,
                    (
                        (point[0] - start[0]) * dx
                        + (point[1] - start[1]) * dy
                    ) / length_squared,
                ),
            )
        else:
            fraction = 0.0
        projected = (
            start[0] + fraction * dx,
            start[1] + fraction * dy,
        )
        offset = hypot(point[0] - projected[0], point[1] - projected[1])
        candidate = (offset, station_base + fraction * length, projected)
        if best is None or candidate[0] < best[0]:
            best = candidate
        station_base += length
    return best[1], best[0], best[2]


def line_from_items(items):
    """Build a polyline from item coordinates in their current order."""
    return [
        (float(item["x"]), float(item["y"]))
        for item in items
        if number(item.get("x")) is not None
        and number(item.get("y")) is not None
    ]


def section_positions(items, mode="line", line=None):
    """Return display items enriched with station/offset and deterministic order."""
    rows = [dict(item) for item in items if item.get("enabled", True)]
    if mode == "equal":
        for index, row in enumerate(rows):
            row["_station"] = float(index * 100)
            row["_offset"] = 0.0
        return rows

    effective_line = list(line or ())
    if mode == "order" or len(effective_line) < 2:
        effective_line = line_from_items(rows)
    if len(effective_line) < 2:
        for index, row in enumerate(rows):
            row["_station"] = float(index * 100)
            row["_offset"] = 0.0
        return rows

    for row in rows:
        x, y = number(row.get("x")), number(row.get("y"))
        if x is None or y is None:
            row["_station"] = None
            row["_offset"] = None
            continue
        station, offset, projected = project_to_polyline((x, y), effective_line)
        row["_station"] = station
        row["_offset"] = offset
        row["_projected"] = projected
    if mode == "line":
        rows.sort(key=lambda row: (
            row["_station"] is None,
            row["_station"] if row["_station"] is not None else 0.0,
        ))
    return rows


def elevation_range(items, terrain=None):
    """Return a padded absolute-elevation range for drawable section content."""
    values = []
    for item in items:
        elevation = number(item.get("elevation"))
        depth = number(item.get("depth"))
        if elevation is None:
            continue
        values.append(elevation)
        values.append(elevation - max(0.0, depth or 0.0))
    values.extend(
        elevation for _, value in (terrain or ())
        if (elevation := number(value)) is not None
    )
    if not values:
        return -10.0, 10.0
    minimum, maximum = min(values), max(values)
    padding = max(2.0, (maximum - minimum) * 0.04)
    return minimum - padding, maximum + padding
