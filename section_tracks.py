"""Native cross-section tracks: measured records, projection and drawing."""

from collections import Counter, OrderedDict
from dataclasses import dataclass
from math import ceil, isfinite, log10, sqrt

from qgis.PyQt.QtCore import QLineF, QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen


TRACKS = ("isotopes", "biofinds", "biozones", "stages")
POINT_TRACKS = ("isotopes", "biofinds")
TRACK_TITLES = {
    "isotopes": "Isotoobid",
    "biofinds": "Biotsoonide leiupunktid",
    "biozones": "Tõlgendatud biotsoonide ulatus",
    "stages": "Lademed",
}
CURVE_COLORS = ("#31569a", "#9f4035", "#287561", "#765178", "#ac631d")
PATTERN_LABELS = {
    "carbonate": "Karbonaatkivim",
    "sand": "Liiv / liivakivi",
    "mud": "Savi / aleuriit",
    "gravel": "Kruus / konglomeraat",
    "organic": "Orgaaniline sete",
    "other": "Muu / määramata litoloogia",
}


def finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def record_id(record):
    """Use an actual source ID or a local UUID, not position or row number."""
    return next((
        str(record[key]).strip() for key in ("id", "esri_globalid", "globalid")
        if record.get(key) not in (None, "") and str(record[key]).strip()
    ), "")


def anchor_choices(row):
    """Human label and stable reference for each valid joinable boundary."""
    choices = []
    item_key = str(row.get("key") or "")
    if not item_key:
        return choices
    for track in ("units", *TRACKS):
        for record in row.get(track) or ():
            identifier = record_id(record)
            if not identifier:
                continue
            label = (
                record.get("name") or record.get("analyte") or record.get("taxon")
                or record.get("zone")
                or record.get("indeks") or record.get("litoloogia") or identifier
            )
            bounds = (("point", "depth"),) if track in POINT_TRACKS else (
                ("top", "z_suht_ylemine"), ("base", "z_suht_alumine")
            )
            for boundary, data_key in bounds:
                if track == "isotopes" and finite_number(record.get("value")) is None:
                    continue
                value = finite_number(record.get(data_key))
                if value is None or value < 0:
                    continue
                choices.append((
                    f"{label} — {value:g} m",
                    dict(item_key=item_key, track=track, id=identifier, boundary=boundary),
                ))
    return choices


def anchor_position(row, ref):
    if not isinstance(ref, dict):
        return None
    if ref.get("item_key") not in (None, "", row.get("key")):
        return None
    track = ref.get("track")
    if track not in ("units", *TRACKS):
        return None
    identifier = str(ref.get("id") or "")
    boundary = ref.get("boundary")
    if not identifier:
        return None
    if track in POINT_TRACKS:
        if boundary != "point":
            return None
        data_key = "depth"
    else:
        data_key = {"top": "z_suht_ylemine", "base": "z_suht_alumine"}.get(boundary)
        if not data_key:
            return None
    # An ambiguous ID should not silently anchor a geological interpretation.
    matches = [
        record for record in row.get(track) or ()
        if record_id(record).casefold() == identifier.casefold()
    ]
    if len(matches) != 1:
        return None
    if track == "isotopes" and finite_number(matches[0].get("value")) is None:
        return None
    value = finite_number(matches[0].get(data_key))
    return value if value is not None and value >= 0 else None


@dataclass(frozen=True)
class LogAxis:
    origin: float
    signed_factor: float

    @classmethod
    def from_row(cls, row, mode, ref=None):
        upward = row.get("axis") == "height"
        direction = 1.0 if upward else -1.0
        if mode == "relative":
            # A measured axis is not a vertical projection. Use raw distances.
            return cls(0.0, direction)
        factor = finite_number(row.get("vertical_factor"))
        if factor is None and not upward:
            factor = 1.0
        if factor is None or not 0 < factor <= 1:
            return None
        signed = direction * factor
        if mode == "correlation":
            position = anchor_position(row, ref)
            return None if position is None else cls(-signed * position, signed)
        origin = finite_number(row.get("elevation"))
        return None if origin is None else cls(origin, signed)

    def ordinate(self, position):
        return self.origin + self.signed_factor * position


def measured_extent(row):
    values = [0.0]
    for value in (row.get("depth"),):
        number = finite_number(value)
        if number is not None:
            values.append(number)
    for track in (
        "units", "biozones", "stages", "core_boxes", "sarv_core_boxes", "samples",
        "analyses", "sarv_samples", "sarv_analyses", "sarv_specimens",
        "veka_construction", *POINT_TRACKS,
    ):
        for record in row.get(track) or ():
            for key in (
                ("depth",) if track in POINT_TRACKS else (
                    "z_suht_ylemine", "z_suht_alumine", "alg", "lopp"
                )
            ):
                value = finite_number(record.get(key))
                if value is not None:
                    values.append(value)
    if row.get("static_water"):
        value = finite_number(row["static_water"].get("st_veetase"))
        if value is not None:
            values.append(value)
    return min(values), max(values)


def axis_range(rows, terrain):
    values = [
        row["_log_axis"].ordinate(value)
        for row in rows for value in row["_measured_extent"]
    ]
    values.extend(
        value for _, raw in terrain if (value := finite_number(raw)) is not None
    )
    if not values:
        return -10.0, 10.0
    minimum, maximum = min(values), max(values)
    pad = max(2.0, (maximum - minimum) * 0.04)
    return minimum - pad, maximum + pad


def track_order(layout):
    custom = layout.get("track_order")
    chosen = [key for key in custom if key in TRACKS] if isinstance(custom, (tuple, list)) else []
    return tuple(dict.fromkeys(chosen + list(TRACKS)))


def band_groups(records):
    groups = OrderedDict()
    for record in records:
        scheme = str(record.get("scheme") or "").strip()
        groups.setdefault(scheme, []).append(record)
    return groups.items()


def biofind_positions(records):
    """A finding's measured position is independent of its optional zone label."""
    result = []
    for record in records:
        depth = finite_number(record.get("depth"))
        if depth is not None and depth >= 0:
            result.append((depth, record))
    return sorted(result, key=lambda point: point[0])


def biofind_width(points):
    count = max(Counter(depth for depth, _ in points).values(), default=1)
    return max(142, 105 + count * 10)


def draw_biofind_track(painter, x, width, points, y_at, heading, title, hit):
    """Draw points at measured heights, spreading coincident dots only in X."""
    painter.save()
    color = QColor("#19665c")
    painter.setPen(color)
    painter.drawText(
        QRectF(x, heading, width, 16), Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(width)),
    )
    lane_bottoms = []
    exact_lanes = {}
    labels = []
    mark_slots = max(1, int((width - 95) // 10))
    for depth, record in points:
        y = y_at(depth)
        used = exact_lanes.setdefault(depth, set())
        slot = next((
            i for i, last_y in enumerate(lane_bottoms)
            if abs(y - last_y) >= 9 and i not in used
        ), None)
        if slot is None:
            if len(lane_bottoms) < mark_slots:
                slot = len(lane_bottoms)
                lane_bottoms.append(y)
            else:
                # Distinct but closely spaced horizons may share a lane at
                # this scale; exact ties never do, and can always be picked.
                slot = next(i for i in range(mark_slots) if i not in used)
        lane_bottoms[slot] = y
        used.add(slot)
        center = QPointF(x + 7 + slot * 10, y)
        point = QRectF(center.x() - 3.5, y - 3.5, 7.0, 7.0)
        painter.setPen(QPen(QColor("white"), .7))
        painter.setBrush(color)
        painter.drawEllipse(point)
        hit(point.adjusted(-.5, -.5, .5, .5), record, False)
        label = str(record.get("zone") or record.get("taxon") or record.get("sample_ref") or "").strip()
        if label:
            labels.append((center, record, label))
    # Render labels after markers, preventing packed labels at the same
    # horizon from covering another dot. Moving text never moves the marker.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    occupied_labels = []
    text_x = x + 12 + 10 * len(lane_bottoms)
    room = max(70, int(x + width - text_x))
    for center, record, label in labels:
        dx = finite_number(record.get("label_dx")) or 0.0
        dy = finite_number(record.get("label_dy")) or 0.0
        text = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, room)
        rect = QRectF(text_x + dx, center.y() - 8 + dy, painter.fontMetrics().horizontalAdvance(text) + 4, 16)
        if not (dx or dy) and any(rect.intersects(other) for other in occupied_labels):
            continue
        occupied_labels.append(rect)
        if dx or dy:
            painter.setPen(QPen(color, .55))
            painter.drawLine(QLineF(center, QPointF(rect.left(), rect.center().y())))
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        hit(rect, record, True)
    painter.restore()


def curve_groups(records):
    """Do not combine different analytes, units or reference scales."""
    groups = OrderedDict()
    for record in records:
        name = str(record.get("analyte") or "").strip()
        depth = finite_number(record.get("depth"))
        if not name or depth is None or depth < 0:
            continue
        key = (name, str(record.get("unit") or "").strip(), str(record.get("reference") or "").strip())
        groups.setdefault(key, []).append((depth, record))
    return [
        (key, sorted(points, key=lambda point: point[0]))
        for key, points in groups.items()
        if any(finite_number(record.get("value")) is not None for _, record in points)
    ]


def curve_edges(points, max_gap=None):
    """Connect only adjacent measured values, never across explicit gaps."""
    maximum = finite_number(max_gap)
    for (a, first), (b, second) in zip(points, points[1:]):
        if (
            finite_number(first.get("value")) is None
            or finite_number(second.get("value")) is None
            or second.get("gap_before")
            or b <= a
            or (maximum is not None and maximum > 0 and b - a > maximum)
        ):
            continue
        yield (a, first), (b, second)


def curve_scales(rows):
    """One repeatable scale and colour per analyte, unit, and reference."""
    scales = {}
    for row in rows:
        for key, points in row["_curves"]:
            for _, record in points:
                value = finite_number(record.get("value"))
                if value is None:
                    continue
                uncertainty = max(0.0, finite_number(record.get("uncertainty")) or 0.0)
                minimum, maximum = value - uncertainty, value + uncertainty
                if not isfinite(minimum) or not isfinite(maximum):
                    minimum = maximum = value
                if key in scales:
                    a, b = scales[key]
                    minimum, maximum = min(a, minimum), max(b, maximum)
                scales[key] = (minimum, maximum)
    result = {}
    for i, (key, (lower, upper)) in enumerate(scales.items()):
        if upper <= lower:
            pad = max(abs(upper) * 0.05, 0.1)
            lower, upper = lower - pad, upper + pad
        result[key] = (lower, upper, CURVE_COLORS[i % len(CURVE_COLORS)])
    return result


def lithology_pattern(unit):
    value = str(unit.get("litoloogia") or unit.get("litoloogia_orig") or "").casefold()
    for category, terms in (
        ("carbonate", ("limestone", "dolom", "carbonate", "lubjakivi", "karbonaat", "mergel", "marl")),
        ("gravel", ("kruus", "gravel", "konglom", "conglom", "veeris")),
        ("organic", ("turvas", "peat", "muld", "organic", "orgaan")),
        ("mud", ("mud", "clay", "shale", "savi", "aleur", "silt", "argilliit")),
        ("sand", ("sand", "liiv")),
    ):
        if any(term in value for term in terms):
            return category
    return "other"


def draw_lithology(painter, rect, category, background):
    # Draw vectors explicitly. Native Qt brush stipples may not render
    # identically through QSvgGenerator and QPdfWriter.
    painter.fillRect(rect, background)
    if category == "other":
        return
    width, height = rect.width(), rect.height()
    left, top = rect.left(), rect.top()
    right, bottom = rect.right(), rect.bottom()
    # Large highly zoomed columns stay a bounded-size vector, without
    # any lines escaping the measured layer rectangle.
    spacing = max(6.0, sqrt(width * height / 850), height / 400)
    path = QPainterPath()

    def line(x1, y1, x2, y2):
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)

    if category == "organic":
        for i in range(1, max(1, ceil((width + height) / spacing))):
            diagonal = i * spacing
            first = max(0.0, diagonal - height)
            last = min(width, diagonal)
            if first < last:
                line(left + first, top + diagonal - first, left + last, top + diagonal - last)
    elif category in {"carbonate", "mud"}:
        for i in range(max(1, ceil(height / spacing))):
            y = top + i * spacing
            if y + spacing < bottom:
                line(left, y + spacing, right, y + spacing)
            if category == "carbonate":
                for j in range(ceil(width / (spacing * 2))):
                    x = left + (j * 2 + (1 if i % 2 else 0.5)) * spacing
                    if x < right:
                        line(x, y, x, min(y + spacing, bottom))
    else:  # Sand dots and gravel outlines.
        for i in range(ceil(height / spacing)):
            y = top + (i + 0.5) * spacing
            for j in range(ceil(width / spacing)):
                x = left + (j + (0.75 if i % 2 else 0.25)) * spacing
                rx, ry = (0.6, 0.6) if category == "sand" else (1.8, 1.05)
                if x - rx >= left and x + rx <= right and y + ry <= bottom:
                    path.addEllipse(QPointF(x, y), rx, ry)
    if path.isEmpty():
        return
    painter.save()
    ink = QColor(44, 50, 55, 140)
    if category == "sand":
        painter.setBrush(ink)
        painter.setPen(Qt.PenStyle.NoPen)
    else:
        painter.setPen(QPen(ink, 0.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


def grain_fraction(unit):
    value = unit.get("grain_size")
    if value in (None, ""):
        value = unit.get("terasuurus")
    if value in (None, ""):
        return None
    numeric = finite_number(str(value).replace(",", "."))
    if numeric is not None:
        return grain_width_fraction(numeric) if numeric > 0 else None
    value = str(value).strip().casefold().replace("-", " ")
    for representative_size, terms in (
        (0.002, ("clay", "savi")),
        (0.016, ("silt", "aleuriit")),
        (0.088, ("very fine sand", "väga peenliiv")),
        (0.177, ("fine sand", "peenliiv", "peeneteraline")),
        (0.354, ("medium sand", "keskliiv", "keskmiseteraline")),
        (0.707, ("coarse sand", "jämeliiv", "jämedateraline")),
        (1.414, ("very coarse sand", "väga jämeliiv")),
        (4.0, ("gravel", "kruus")),
    ):
        if value in terms:
            return grain_width_fraction(representative_size)
    return None


def grain_width_fraction(size_mm):
    return max(0.15, min(1.0, (log10(size_mm) + 3.0) / 4.0))


def draw_grain_scale(painter, left, y, width, caption):
    painter.save()
    painter.setFont(QFont(painter.font().family(), 6))
    painter.setPen(QPen(QColor("#626b72"), 0.7))
    painter.drawLine(QLineF(left, y, left + width, y))
    for value in ((0.01, 0.3, 10.0) if width >= 45 else (0.01, 10.0)):
        x = left + grain_width_fraction(value) * width
        painter.drawLine(QLineF(x, y, x, y + 3))
        painter.drawText(QRectF(x - 11, y + 4, 22, 12), Qt.AlignmentFlag.AlignCenter, f"{value:g}")
    painter.drawText(QRectF(left + width + 12, y - 5, 115, 14), Qt.AlignmentFlag.AlignLeft, caption)
    painter.restore()


def contact_style(value):
    value = str(value or "").strip().casefold()
    if value in {"gradational", "üleminekuline", "astmeline"}:
        return Qt.PenStyle.DotLine
    if value in {"erosional", "unconformity", "erosiooniline", "lünk"}:
        return Qt.PenStyle.DashDotLine
    if value in {"uncertain", "ebakindel"}:
        return Qt.PenStyle.DashLine
    return Qt.PenStyle.SolidLine


def draw_interval_band(painter, x, width, values, y_at, color, hit):
    for row in values:
        top = finite_number(row.get("z_suht_ylemine"))
        base = finite_number(row.get("z_suht_alumine"))
        if top is None or base is None or base <= top:
            continue
        a, b = sorted((y_at(top), y_at(base)))
        rect = QRectF(x, a, width, max(1.0, b - a))
        painter.fillRect(rect, color)
        painter.setPen(QPen(color.darker(145), 0.7))
        painter.drawRect(rect)
        hit(rect, row)
        painter.setPen(QColor("#252b35"))
        if rect.height() >= 12:
            title = QFontMetrics(painter.font()).elidedText(
                str(row.get("name") or ""), Qt.TextElideMode.ElideRight, max(1, int(width - 6))
            )
            painter.drawText(rect.adjusted(3, 0, -3, 0), Qt.AlignmentFlag.AlignCenter, title)


def draw_isotope_track(painter, x, width, group, y_at, header_y, bounds, color, max_gap, hit, scale):
    (analyte, unit, ref), points = group
    measured = []
    for depth, row in points:
        value = finite_number(row.get("value"))
        if value is not None:
            uncertainty = max(0.0, finite_number(row.get("uncertainty")) or 0.0)
            measured.append((depth, value, uncertainty, row))
    if not measured:
        return
    lower, upper = scale
    magnitude = max(abs(lower), abs(upper), 1.0)
    low = lower / magnitude
    span = upper / magnitude - low
    if not isfinite(span) or span <= 0:
        return
    a, b = x + 4, x + width - 4
    def x_at(value):
        return a + (value / magnitude - low) * (b - a) / span

    ymin, ymax = sorted(bounds)
    painter.setPen(QPen(QColor("#c2c9d1"), 0.7))
    painter.drawRect(QRectF(x, ymin, width, max(1.0, ymax - ymin)))
    painter.setPen(QPen(color, 1.1))
    for (depth, first), (next_depth, second) in curve_edges(points, max_gap):
        painter.drawLine(QLineF(x_at(float(first["value"])), y_at(depth), x_at(float(second["value"])), y_at(next_depth)))
    for depth, value, uncertainty, row in measured:
        xx, y = x_at(value), y_at(depth)
        if uncertainty and isfinite(value - uncertainty) and isfinite(value + uncertainty):
            painter.drawLine(QLineF(x_at(value - uncertainty), y, x_at(value + uncertainty), y))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(xx, y), 2.4, 2.4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        hit(QRectF(xx - 4, y - 4, 8, 8), row)
    metrics = QFontMetrics(painter.font())
    title = metrics.elidedText(
        " ".join(part for part in (analyte, unit, ref) if part),
        Qt.TextElideMode.ElideRight, max(1, int(width)),
    )
    painter.drawText(QRectF(x, header_y, width, 12), Qt.AlignmentFlag.AlignCenter, title)
    painter.drawText(QRectF(x + 3, header_y + 12, width - 6, 12), Qt.AlignmentFlag.AlignLeft, f"{lower:.3g}")
    painter.drawText(QRectF(x + 3, header_y + 12, width - 6, 12), Qt.AlignmentFlag.AlignRight, f"{upper:.3g}")


def draw_correlation(painter, p1, p2, inferred, label):
    color = QColor("#7651ae") if inferred else QColor("#256d76")
    painter.setPen(QPen(color, 1.45, Qt.PenStyle.DashLine if inferred else Qt.PenStyle.SolidLine))
    painter.drawLine(QLineF(*p1, *p2))
    for x, y in (p1, p2):
        painter.drawEllipse(QPointF(x, y), 2.5, 2.5)
    if label and abs(p1[0] - p2[0]) >= 52:
        center = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        width = min(abs(p1[0] - p2[0]) - 10, 150)
        painter.setFont(QFont(painter.font().family(), 7))
        title = QFontMetrics(painter.font()).elidedText(str(label), Qt.TextElideMode.ElideRight, int(width))
        target = QRectF(center[0] - width / 2, center[1] - 15, width, 14)
        painter.fillRect(target, QColor(255, 255, 255, 235))
        painter.drawText(target, Qt.AlignmentFlag.AlignCenter, title)
