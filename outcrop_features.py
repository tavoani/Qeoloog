"""Local outcrop observations and independently scaled wall geometry."""

from dataclasses import dataclass
from math import ceil, isfinite
from uuid import uuid4


OBSERVATIONS = "outcrop_observations"
COVERAGE = "outcrop_coverage"
SHAPES = "outcrop_shapes"
OBSERVATION_KINDS = {
    "note": "Märkus", "sample": "Proov", "photo": "Foto", "feature": "Tunnus",
}
COVERAGE_KINDS = {
    "rockfall_cover": "Varingurusuga kaetud",
    "obscured": "Varjatud",
    "unobserved": "Vaatlemata",
}
SHAPE_KINDS = {
    "wall": "Seinaprofiil", "rockfall": "Varingurusu",
    "ledge": "Eend", "recess": "Süvend",
}
WALL_WIDTH = 154.0
OBSERVATION_WIDTH = 130.0
LANE_GAP = 8.0


class OutcropDataError(ValueError):
    """An incomplete or invalid local observation."""


def is_outcrop(row):
    return row.get("role") == "local_section" and row.get("kind") == "outcrop"


def _number(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if isfinite(number) else None


def _distance(value, *, signed=False):
    number = _number(value)
    if number is None or abs(number) > 1_000_000 or (not signed and number < 0):
        raise OutcropDataError("Sisesta lõplik arv vahemikus ±1 000 000; kõrgus ei tohi olla negatiivne.")
    return number


def _text(value):
    return str(value or "").strip()


def normalize_record(track, data):
    """Validate own tracks without modifying source lithology or sorting vertices."""
    if not isinstance(data, dict):
        raise OutcropDataError("Vaatlusandmed peavad olema kirje kujul.")
    kind_sets = {OBSERVATIONS: OBSERVATION_KINDS, COVERAGE: COVERAGE_KINDS, SHAPES: SHAPE_KINDS}
    kinds = kind_sets.get(track)
    if kinds is None:
        raise OutcropDataError("Tundmatu paljandiraja tüüp.")
    kind = data.get("kind") or next(iter(kinds))
    if not isinstance(kind, str) or kind not in kinds:
        raise OutcropDataError("Tundmatu paljandikirje tüüp.")
    record = {
        "id": _text(data.get("id")) or str(uuid4()),
        "kind": kind, "text": _text(data.get("text") or data.get("note")),
    }
    if track == OBSERVATIONS:
        record["depth"] = _distance(data.get("depth"))
        for name in ("sample_ref", "source_ref", "attachment", "attachment_name"):
            if value := _text(data.get(name)):
                record[name] = value
        for name in ("label_dx", "label_dy"):
            if data.get(name) not in (None, ""):
                record[name] = _distance(data[name], signed=True)
    elif track == COVERAGE:
        record["top"], record["bottom"] = sorted(
            _distance(data.get(key)) for key in ("top", "bottom")
        )
        if record["top"] == record["bottom"]:
            raise OutcropDataError("Varjatud vahemik peab olema nullist pikem.")
    else:
        raw = data.get("points")
        if not isinstance(raw, (tuple, list)) or len(raw) > 2000:
            raise OutcropDataError("Paljandi kuju võib sisaldada kuni 2000 tippu.")
        points = []
        for value in raw:
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                raise OutcropDataError("Igal tipul peab olema nihe ja kõrgus.")
            point = [_distance(value[0], signed=True), _distance(value[1])]
            if not points or point != points[-1]:
                points.append(point)
        if kind == "rockfall":
            if points and points[0] == points[-1]:
                points.pop()
            if len({tuple(point) for point in points}) < 3 or abs(sum(
                a[0] * b[1] - a[1] * b[0] for a, b in zip(points, points[1:] + points[:1])
            )) < 1e-12:
                raise OutcropDataError("Varingurusu ala vajab vähemalt kolme tippu ja pindala.")
        elif len(points) < 2:
            raise OutcropDataError("Seinaprofiil vajab vähemalt kahte eri tippu.")
        record["points"] = points
        # Schematic does not claim a true horizontal offset.
        record["measured"] = data.get("measured") is True
    return record


def _valid_records(row, track):
    records = row.get(track) or ()
    if not isinstance(records, (tuple, list)):
        return
    for raw in records:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        try:
            yield normalize_record(track, raw)
        except OutcropDataError:
            continue


def measured_positions(row):
    """Include own observation/coverage/geometry heights in drawing bounds."""
    if not is_outcrop(row):
        return []
    return [
        *(record["depth"] for record in _valid_records(row, OBSERVATIONS)),
        *(record[edge] for record in _valid_records(row, COVERAGE) for edge in ("top", "bottom")),
        *(point[1] for record in _valid_records(row, SHAPES) for point in record["points"]),
    ]


def uncovered_spans(row, top, bottom, display, editing=False):
    """Original intervals survive; only definitely visible pieces get labels."""
    if not is_outcrop(row) or not (editing or display.get(COVERAGE, True)):
        return [(top, bottom)]
    spans = [(top, bottom)]
    for record in _valid_records(row, COVERAGE):
        lower, upper = record["top"], record["bottom"]
        kept = []
        for start, end in spans:
            if upper <= start or lower >= end:
                kept.append((start, end))
                continue
            if start < lower:
                kept.append((start, lower))
            if upper < end:
                kept.append((upper, end))
        spans = kept
    return spans


def _wall_modes(row, display, editing):
    if editing:
        return (True, False)
    if not display.get(SHAPES, True):
        return ()
    present = {record["measured"] for record in _valid_records(row, SHAPES)}
    return tuple(measured for measured in (True, False) if measured in present)


def _observations_visible(row, display, editing):
    return editing or (display.get(OBSERVATIONS, True) and any(_valid_records(row, OBSERVATIONS)))


def outcrop_width(row, display=None, editing=False):
    if not is_outcrop(row):
        return 0
    display = display or {}
    observations = (OBSERVATION_WIDTH + LANE_GAP) if _observations_visible(row, display, editing) else 0.0
    return observations + len(_wall_modes(row, display, editing)) * (WALL_WIDTH + LANE_GAP)


@dataclass(frozen=True)
class WallPanel:
    left: float
    top: float
    width: float
    height: float
    min_offset: float
    max_offset: float
    measured: bool

    @property
    def rect(self):
        from qgis.PyQt.QtCore import QRectF

        return QRectF(self.left, self.top, self.width, self.height)

    @property
    def pixels_per_unit(self):
        return (self.width - 16.0) / (self.max_offset - self.min_offset)

    @property
    def x0(self):
        return self.left + 8.0 - self.min_offset * self.pixels_per_unit

    def x(self, offset):
        return self.x0 + float(offset) * self.pixels_per_unit

    def offset(self, x):
        return (float(x) - self.x0) / self.pixels_per_unit


def wall_panels(row, track_x, plot_bounds, display, editing=False):
    """Allocate separate measured (metres) and schematic (no metre scale) lanes."""
    if not is_outcrop(row):
        return {}
    if _observations_visible(row, display, editing):
        track_x += OBSERVATION_WIDTH + LANE_GAP
    result = {}
    top, bottom = sorted(plot_bounds)
    records = list(_valid_records(row, SHAPES))
    for measured in _wall_modes(row, display, editing):
        offsets = [offset for item in records if item["measured"] is measured for offset, _ in item["points"]]
        lo = min(-0.5, *offsets) if offsets else -0.5
        hi = max(0.5, *offsets) if offsets else 0.5
        pad = (hi - lo) * 0.15
        result[measured] = WallPanel(track_x, top, WALL_WIDTH, max(1, bottom - top),
                                     lo - pad, hi + pad, measured)
        track_x += WALL_WIDTH + LANE_GAP
    return result


def _hatch(painter, rect, ink, polygon=()):
    """Draw vector hatching explicitly clipped, even with limited SVG clipping."""
    from qgis.PyQt.QtCore import QLineF
    from qgis.PyQt.QtGui import QPen

    painter.save()
    painter.setPen(QPen(ink, 0.7))
    # Restrict the number of hatch strokes for very large manual zooms.
    total = rect.width() + rect.height()
    step = max(6, ceil(total / (512 if polygon else 1800)))
    if polygon:
        xs = [node.x() for node in polygon]
        ys = [node.y() for node in polygon]
        segments = [
            (a.x() + a.y(), b.x() + b.y(), a.y(), b.y())
            for a, b in zip(polygon, list(polygon[1:]) + [polygon[0]])
        ]
        origin = min(xs) + min(ys)
        for x in range(0, ceil(total) + 1, step):
            constant = origin + x
            crossings = sorted(
                ya + (yb - ya) * (constant - sa) / (sb - sa)
                for sa, sb, ya, yb in segments
                if min(sa, sb) <= constant < max(sa, sb)
            )
            for start, end in zip(crossings[::2], crossings[1::2]):
                painter.drawLine(QLineF(constant - start, start, constant - end, end))
    else:
        for x in range(0, ceil(total) + 1, step):
            start, end = max(0.0, x - rect.width()), min(rect.height(), x)
            if start < end:
                painter.drawLine(QLineF(
                    rect.left() + x - start, rect.top() + start,
                    rect.left() + x - end, rect.top() + end,
                ))
    painter.restore()


def draw_coverage(painter, row, left, width, y_at, display, remember_hit, translate, editing=False):
    if not is_outcrop(row) or not (editing or display.get(COVERAGE, True)):
        return
    from qgis.PyQt.QtCore import QRectF, Qt
    from qgis.PyQt.QtGui import QColor, QPen

    painter.save()
    for item in _valid_records(row, COVERAGE):
        bounds = sorted((y_at(item["top"]), y_at(item["bottom"])))
        box = QRectF(left, bounds[0], width, max(2.0, bounds[1] - bounds[0]))
        rockfall = item["kind"] == "rockfall_cover"
        edge = QColor("#7a5547" if rockfall else "#526071")
        painter.fillRect(box, QColor("#f8eee8" if rockfall else "#f5f6f8"))
        _hatch(painter, box, QColor("#b38f82" if rockfall else "#8996a5"))
        painter.setPen(QPen(edge, 1.0, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        remember_hit(box.adjusted(-1, -3, 1, 3), COVERAGE, item)
        if editing:
            painter.setPen(QPen(edge, 1.0))
            painter.setBrush(QColor("white"))
            for edge_name in ("top", "bottom"):
                y = y_at(item[edge_name])
                handle = QRectF(box.center().x() - 4, y - 4, 8, 8)
                painter.drawRect(handle)
                remember_hit(handle.adjusted(-2, -2, 2, 2), COVERAGE, dict(item, _edge=edge_name))
        # Put the key next to the hatching so grayscale exports are intelligible.
        caption = translate(COVERAGE_KINDS[item["kind"]])
        label = QRectF(box.right() + 5, box.center().y() - 7, 132, 15)
        painter.fillRect(label, QColor("#ffffff"))
        painter.setPen(edge)
        painter.drawText(label, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(caption, Qt.TextElideMode.ElideRight, 132))
    painter.restore()


def _draw_observations(painter, records, left, y_at, header_y, remember_hit, translate):
    from qgis.PyQt.QtCore import QLineF, QRectF, Qt
    from qgis.PyQt.QtGui import QColor, QPen

    painter.setPen(QColor("#374d55"))
    painter.drawText(QRectF(left, header_y, OBSERVATION_WIDTH, 15),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     translate("Paljandi vaatlused"))
    colors = {"note": "#24566c", "sample": "#216944", "photo": "#61407b", "feature": "#903e1b"}
    lanes = []
    label_levels = []
    for item in sorted(records, key=lambda record: record["depth"]):
        y = y_at(item["depth"])
        if not isfinite(y):
            continue
        # Occupy lanes only when marks would cover one another, without moving in Y.
        lane = next((i for i, prev in enumerate(lanes) if abs(y - prev) >= 10), len(lanes))
        if lane == len(lanes):
            lanes.append(y)
        else:
            lanes[lane] = y
        x = left + 6 + lane * 10
        mark = QRectF(x - 3.5, y - 3.5, 7, 7)
        color = QColor(colors[item["kind"]])
        painter.setPen(QPen(color.darker(115), 1.0))
        painter.setBrush(color)
        if item["kind"] == "photo":
            painter.drawRect(mark)
        else:
            painter.drawEllipse(mark)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        remember_hit(mark.adjusted(-1, -2, 1, 2), OBSERVATIONS, item)
        label = item.get("text") or item.get("sample_ref") or item.get("attachment_name") or translate(OBSERVATION_KINDS[item["kind"]])
        label = " ".join(label.split())
        if not label:
            continue
        label_y = y + item.get("label_dy", 0.0)
        label_x = x + 10 + item.get("label_dx", 0.0)
        if "label_dy" not in item:
            while any(abs(label_y - previous) < 14 for previous in label_levels):
                label_y += 14
        label_levels.append(label_y)
        caption = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, 100)
        box = QRectF(label_x, label_y - 7, painter.fontMetrics().horizontalAdvance(caption) + 2, 14)
        painter.setPen(QPen(color, 0.7))
        if abs(label_y - y) > 2 or abs(label_x - x) > 12:
            painter.drawLine(QLineF(x + 4, y, box.left(), label_y))
        painter.fillRect(box, QColor(255, 255, 255, 240))
        painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, caption)
        remember_hit(box, OBSERVATIONS + "_label", item)


def _draw_wall(painter, panel, records, y_at, header_y, remember_hit, translate, editing):
    from qgis.PyQt.QtCore import QLineF, QPointF, QRectF, Qt
    from qgis.PyQt.QtGui import QColor, QPainterPath, QPen

    rect = panel.rect
    painter.setPen(QPen(QColor("#bdc6ce"), 0.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)
    painter.setPen(QPen(QColor("#9cabb7"), 0.8, Qt.PenStyle.DotLine))
    painter.drawLine(QLineF(panel.x0, rect.top(), panel.x0, rect.bottom()))
    painter.setPen(QColor("#374d55"))
    title = translate("Seinaprofiil (m)" if panel.measured else "Seinaprofiil (skeem)")
    painter.drawText(QRectF(rect.left(), header_y, rect.width(), 15),
                     Qt.AlignmentFlag.AlignCenter, title)
    if panel.measured:
        for offset in (panel.min_offset / 1.15, 0.0, panel.max_offset / 1.15):
            x = panel.x(offset)
            label = f"{offset:+.2g}" if offset else "0"
            painter.drawLine(QLineF(x, rect.bottom(), x, rect.bottom() + 4))
            painter.drawText(QRectF(x - 24, rect.bottom() + 4, 48, 14),
                             Qt.AlignmentFlag.AlignCenter, label)
    colors = {"wall": "#31485b", "ledge": "#135d72", "recess": "#345b86", "rockfall": "#a35234"}
    for item in records:
        if item["measured"] is not panel.measured:
            continue
        coords = [QPointF(panel.x(offset), y_at(depth)) for offset, depth in item["points"]]
        path = QPainterPath(coords[0])
        for point in coords[1:]:
            path.lineTo(point)
        color = QColor(colors[item["kind"]])
        if item["kind"] == "rockfall":
            path.closeSubpath()
            painter.fillPath(path, QColor("#eacbb6"))
            _hatch(painter, path.boundingRect(), QColor("#b9876b"), coords)
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine if item["measured"] else Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        segments = list(zip(coords, coords[1:]))
        if item["kind"] == "rockfall":
            segments.append((coords[-1], coords[0]))
        for a, b in segments:
            # Rectangular hit regions approximate the stroke without claiming
            # the whole bounding box of a long diagonal.
            n = max(1, min(32, ceil(max(abs(a.x() - b.x()), abs(a.y() - b.y())) / 8)))
            for i in range(n + 1):
                x = a.x() + (b.x() - a.x()) * i / n
                y = a.y() + (b.y() - a.y()) * i / n
                remember_hit(QRectF(x - 4, y - 4, 8, 8), SHAPES, item)
        if editing:
            painter.setPen(QPen(color, 1.0))
            painter.setBrush(QColor("white"))
            for i, point in enumerate(coords):
                handle = QRectF(point.x() - 3.0, point.y() - 3.0, 6, 6)
                painter.drawEllipse(handle)
                remember_hit(handle.adjusted(-2, -2, 2, 2), SHAPES, dict(item, _vertex=i))
        caption = item.get("text") or translate(SHAPE_KINDS[item["kind"]])
        painter.setPen(color)
        first = coords[0]
        label = QRectF(first.x() + 4, first.y() - 15, max(10, rect.right() - first.x() - 4), 15)
        painter.drawText(label, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(caption, Qt.TextElideMode.ElideRight,
                                                          int(label.width())))


def draw_outcrop_lanes(painter, row, track_x, y_at, y_start, plot_bounds, display,
                        remember_hit, translate, editing=False):
    if not is_outcrop(row):
        return {}
    painter.save()
    header_y = min(y_start, min(plot_bounds)) - 17.0
    if _observations_visible(row, display, editing):
        _draw_observations(painter, _valid_records(row, OBSERVATIONS), track_x, y_at,
                           header_y, remember_hit, translate)
    panels = wall_panels(row, track_x, plot_bounds, display, editing)
    records = list(_valid_records(row, SHAPES))
    for panel in panels.values():
        _draw_wall(painter, panel, records, y_at, header_y, remember_hit, translate, editing)
    painter.restore()
    return panels
