"""Lisa 5 log geometry, redrawn as native vectors from local measurements."""

from bisect import bisect_left, bisect_right
from collections import Counter
from itertools import chain
from math import ceil, cos, floor, isfinite, radians, sin, tau
from statistics import median

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen, QPolygonF

from .etl_lab import lab_key
from .lithology_report import (
    MAX_PAGES, PAPER, Annotation, LithologyReport, Page, _annotation_text,
    _get, _number, _tables, _text, _unit_label, _wrap,
)


_WIDTH, _LEFT, _RIGHT = 807.84, 14.16, 793.68
_HEADER, _HEADER_END, _LEGEND = 70.92, 175.80, 181.44
_BOTTOM, _MAX_HEIGHT = 72.24, 14000.0
_BLACK = QColor("#000000")
_BLUE = QColor("#0000ff")
_RED = QColor("#b02020")
_GRID = QColor("#d3d3d3")
_BAR = QColor("#929292")
_STRUCTURE_COLORS = {
    "foliation": QColor("#0000ff"),
    "fracture": QColor("#ff0000"),
    "other": QColor("#606060"),
}
_XRD = (
    (("kaltsiit", "calcite", "cal"), "#a9bffe"),
    (("dolomiit", "dolomite", "dol"), "#ffffe0"),
    (("kvarts", "quartz", "qz"), "#ffff00"),
    (("k-päevakivi", "k päevakivi", "k-feldspar", "kfs"), "#feb3b8"),
    (("plagioklass", "plagioclase", "pl"), "#c763fe"),
    (("püriit", "pyrite", "py"), "#ef9f09"),
    (("kloriit", "chlorite", "chl"), "#1def31"),
    (("illiit", "illite", "ill"), "#008195"),
    (("kaoliniit", "kaolinite"), "#786e1e"),
    (("smektiit", "smectite"), "#ff8200"),
    (("hematiit", "hematite", "hem"), "#c72727"),
    (("apatiit", "apatite", "ap"), "#96be0a"),
    (("teised", "muu", "other"), "#686868"),
)
_BASEMENT_XRD = (
    (("amfibool", "amphibole", "amp"), "#0587fa"),
    (("plagioklass", "plagioclase", "pl"), "#afc4df"),
    (("biotiit", "biotite", "bt"), "#c4c4c4"),
    (("kaltsiit", "calcite", "cal"), "#e0e0e0"),
    (("kloriit", "chlorite", "chl"), "#c8e2ba"),
    (("küünekivi", "hornblende", "kln"), "#9efbfd"),
    (("püriit", "pyrite", "py"), "#fafa69"),
    (("hematiit", "hematite", "hem"), "#eda28c"),
    (("k-päevakivi", "k päevakivi", "k-feldspar", "kfs"), "#feb3c4"),
    (("apatiit", "apatite", "ap"), "#ffebed"),
    (("kvarts", "quartz", "qz"), "#f9f9f9"),
    (("muskoviit", "muskovite", "ms-ill", "illiit", "illite"), "#ffffa3"),
)
_ROCK_FILL = {
    "soil": "#fcf1dd", "organic": "#fbe5d0", "till": "#fce7d6",
    "clay": "#f9e5d7", "sand": "#fbe7d3",
    "carbonate": "#88cb9d", "dolomite": "#98d6b2", "gravel": "#a3dcb6",
    "gneiss": "#bce1d5", "migmatite": "#fbdbe6", "weathered": "#f9bf9e",
}
# The source legend orders its four line motifs by visual density. The
# literal string "none" means a measured non-migmatized interval.
_MIGMATIZATION_LEGEND = (
    ("none", "Migmatiseerumata", "Unmigmatized"),
    ("strong", "Tugevalt migmatiseerunud", "Strongly migmatized"),
    ("moderate", "Keskmiselt migmatiseerunud", "Moderately migmatized"),
    ("weak", "Nõrgalt migmatiseerunud", "Weakly migmatized"),
)
_MIGMATIZATION_STYLE = {
    # Pitch, lines per band (offsets), drift per period (in band pitches),
    # primary/secondary wave amplitudes, and repeating band-phase groups.
    "none": (3.05, (0.,), -16, 3.6, 1.15, 4),
    "strong": (13.2, (-2.35, -.8, .8, 2.35), -3, 2.8, .9, 3),
    "moderate": (12.4, (-1.35, 1.35), -4, 1.9, .55, 4),
    "weak": (7.8, (0.,), 6, 1.5, .25, 3),
}


def _font(size=8, bold=False):
    font = QFont("Arial")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def _rock_motif(entry):
    name = entry.lithology.casefold()
    if any(term in name for term in ("murenemiskoor", "murenenu", "weathered")):
        return "weathered"
    if "migmat" in name:
        return "migmatite"
    if "gneiss" in name or "gneis" in name:
        return "gneiss"
    if "muld" in name or "soil" in name:
        return "soil"
    if any(term in name for term in ("dolokivi", "dolomiit", "dolostone", "dolomite")):
        return "dolomite"
    if entry.pattern == "mud":
        return "clay"
    return entry.pattern


def _pattern(painter, rect, motif, fill, enabled=True):
    if rect.isEmpty():
        return
    painter.fillRect(rect, fill)
    if not enabled or motif == "other":
        return
    painter.save()
    try:
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        painter.translate(rect.left(), rect.top())
        w, h = rect.width(), rect.height()
        path = QPainterPath()

        def line(x1, y1, x2, y2):
            # QSvgGenerator may omit painter clipping, so bound paths in
            # geometry as well as installing the screen/PDF clip.
            if max(x1, x2) < 0 or min(x1, x2) > w or max(y1, y2) < 0 or min(y1, y2) > h:
                return
            path.moveTo(max(0., min(w, x1)), max(0., min(h, y1)))
            path.lineTo(max(0., min(w, x2)), max(0., min(h, y2)))

        def dot(x, y, rx, ry):
            if rx <= x <= w - rx and ry <= y <= h - ry:
                path.addEllipse(QPointF(x, y), rx, ry)

        # The motif is vector-based and clipped to the true interval bounds.
        step = max(5.8, h / 1600)
        if motif in {"carbonate", "dolomite", "clay"}:
            step = max(step, 10.6 if motif != "clay" else 4.0)
            for i in range(ceil(h / step)):
                y = i * step
                line(0, y, w, y)
                if motif == "carbonate":
                    for x in (w / 2,) if i % 2 == 0 else (w / 4, 3 * w / 4):
                        line(x, y, x, y + step)
                elif motif == "dolomite":
                    for x in (w / 3, 2 * w / 3):
                        line(x, y, x, y + step)
                        line(x + 2, y, x + 2, y + step)
                    if i % 2:
                        line(w * .46, y + step / 2, w * .53, y + step / 2)
                elif i % 2:
                    line(0, y + 1.5, w, y + 1.5)
        elif motif in {"organic", "soil", "migmatite", "gneiss", "weathered"}:
            for j in range(ceil(w / 9) + 1):
                x = j * 9 + 3
                if motif in {"migmatite", "gneiss", "weathered"}:
                    for offset in (0, 1.8, 3.5):
                        prev_x, prev_y = x + offset, 0
                        for i in range(1, ceil(h / 2.4) + 1):
                            y = i * 2.4
                            z = sin(i * .45 + j) * 1.7 + sin(i * .12 + j) * 2.2
                            line(prev_x, prev_y, x + offset + z, y)
                            prev_x, prev_y = x + offset + z, y
                else:
                    for i in range(ceil(h / 8)):
                        y = i * 8 + (j % 2) * 2
                        if motif == "soil":
                            line(x, y, x + 1.2, y + 1.7)
                            line(x + 1.2, y + 1.7, x - .2, y + 4)
                            line(x - .2, y + 4, x + 1.2, y + 5.8)
                        else:
                            line(x + 1.8, y, x, y + 1.8)
                            line(x, y + 1.8, x + 2.6, y + 4.1)
        else:
            for i in range(ceil(h / (step * .8))):
                for j in range(ceil(w / 4.3)):
                    x = (j + (.18 if i % 2 else .62)) * 4.3
                    y = (i + .3) * step * .8 + ((i + 3 * j) % 3) * .5
                    if motif == "till" and (i + j) % 4 == 0:
                        if 1.8 <= x <= w - 1.8 and 1.6 <= y <= h - 1.1:
                            path.moveTo(x - 1.8, y + 1.1)
                            path.lineTo(x, y - 1.6)
                            path.lineTo(x + 1.8, y + 1.1)
                            path.closeSubpath()
                    elif motif == "till" and j % 2:
                        line(x, y, x + 2.1, y)
                    elif motif == "gravel" and (i + j) % 3 == 0:
                        dot(x, y, 1.15, .7)
                    else:
                        dot(x, y, .32, .32)
        painter.setPen(QPen(_BLACK, .36))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    finally:
        painter.restore()


def _clip_line(x0, y0, x1, y1, width, height):
    """Clip vector geometry explicitly; QSvgGenerator may ignore clipping."""
    if (0 <= x0 <= width and 0 <= x1 <= width
            and 0 <= y0 <= height and 0 <= y1 <= height):
        return x0, y0, x1, y1
    dx, dy = x1 - x0, y1 - y0
    start, end = 0., 1.
    for distance, room in ((-dx, x0), (dx, width - x0), (-dy, y0), (dy, height - y0)):
        if distance:
            t = room / distance
            if distance < 0:
                start = max(start, t)
            else:
                end = min(end, t)
        elif room < 0:
            return None
    if start >= end:
        return None
    return x0 + dx * start, y0 + dy * start, x0 + dx * end, y0 + dy * end


def _migmatization_pattern(painter, rect, grade, fill, phase=0.):
    """Redraw the Annex 5 band/dash patterns as vectors on the lithology colour."""
    if rect.isEmpty():
        return
    painter.fillRect(rect, fill)
    width, height = rect.width(), rect.height()
    left, top = rect.left(), rect.top()
    period = 48.
    # Keep the dash offsets and directions continuous across cropped bands.
    full_period = period * 4 * 5 * 7 * 19
    phase = phase % full_period if isfinite(phase) else 0.
    limit = phase + height
    pitch, offsets, drift, major, minor, groups = _MIGMATIZATION_STYLE[grade]
    slope = drift * pitch / period
    margin = major + minor + .45
    path = QPainterPath()

    def flow(y, band):
        cycle = tau * (y % period) / period
        return (slope * y + major * sin(3 * cycle) + minor * sin(5 * cycle + .8)
                + .38 * sin(cycle + tau * (band % groups) / groups))

    def add(x0, y0, x1, y1, previous=None):
        piece = _clip_line(x0, y0 - phase, x1, y1 - phase, width, height)
        if piece is None:
            return None
        a, b, c, d = piece
        if previous is None or abs(a - previous[0]) + abs(b - previous[1]) > 1e-7:
            path.moveTo(left + a, top + b)
        path.lineTo(left + c, top + d)
        return c, d

    first = floor((-max(slope * phase, slope * limit) - margin - max(offsets)) / pitch)
    last = ceil((width - min(slope * phase, slope * limit) + margin - min(offsets)) / pitch)
    for band in range(first, last + 1):
        for offset in offsets:
            center = band * pitch + offset
            y0, y1 = sorted(((-margin - center) / slope, (width + margin - center) / slope))
            a, b = max(phase, y0), min(limit, y1)
            if b <= a:
                continue
            steps = ceil((b - a) / 1.1)
            last_x, last_y, previous = center + flow(a, band), a, None
            for i in range(1, steps + 1):
                y = a + (b - a) * i / steps
                x = center + flow(y, band)
                previous = add(last_x, last_y, x, y, previous)
                last_x, last_y = x, y

    if grade != "none":
        # The short dashes occupy the space between the wavy line groups.
        dy = 6.
        for row in range(floor(phase / dy) - 1, ceil(limit / dy) + 1):
            y0 = dy * row
            for band in range(floor((-slope * y0 - margin) / pitch) - 1,
                              ceil((width - slope * y0 + margin) / pitch) + 1):
                y = y0 + ((row * 5 + band * 3) % 7 - 3) * .28
                x = (band + .5) * pitch + flow(y, band) + ((row * 3 + band * 7) % 5 - 2) * .26
                angle = (row * 17 + band * 11) % 19 * tau / 19
                n = 1.02 + ((row * 7 + band * 3) % 4) * .17
                dx, delta_y = n * cos(angle), n * sin(angle)
                add(x - dx, y - delta_y, x + dx, y + delta_y)
    painter.setPen(QPen(_BLACK, .32))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _reading_points(rows, *, density=False, continuous=False):
    """Return sorted finite depth/value pairs, with literal gaps only for a trace."""
    points = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            continue
        depth, value = _number(row[0]), _number(row[1])
        if depth is None or depth < 0:
            continue
        if value is None or (density and value <= 0):
            if continuous:
                points.append((depth, None))
        else:
            points.append((depth, value))
    return tuple(sorted(points, key=lambda point: point[0]))


def _structural_points(rows):
    points = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 4:
            continue
        depth, angle, kind, azimuth = row
        depth, angle, azimuth = _number(depth), _number(angle), _number(azimuth)
        if depth is None or depth < 0 or angle is None or not 0 <= angle <= 90:
            continue
        if azimuth is not None and not 0 <= azimuth <= 360:
            azimuth = None
        kind = kind if isinstance(kind, str) and kind in _STRUCTURE_COLORS else "other"
        points.append((depth, angle, kind, azimuth))
    return tuple(sorted(points, key=lambda point: point[0]))


def _migmatization_intervals(rows):
    intervals = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            continue
        first, last, grade = _number(row[0]), _number(row[1]), row[2]
        if (first is not None and last is not None and 0 <= first < last
                and isinstance(grade, str) and grade in _MIGMATIZATION_STYLE):
            intervals.append((first, last, grade))
    intervals.sort()
    for (_, last, _), (first, _, _) in zip(intervals, intervals[1:]):
        if first < last:
            raise ValueError("Migmatiseerumise vahemikud kattuvad. / Migmatization intervals overlap.")
    return tuple(intervals)


def _outer_scale(preferred, values, step):
    """Expand a reference scale outward; a measured extremum is never clipped."""
    lo, hi = preferred
    minimum, maximum = lo, hi
    used = False
    for value in values:
        if value is not None:
            minimum = min(minimum, value)
            maximum = max(maximum, value)
            used = True
    if not used:
        return None
    if minimum < lo and abs(minimum) < 1e9:
        minimum = min(minimum, round(floor(minimum / step) * step, 8))
    if maximum > hi and abs(maximum) < 1e9:
        maximum = max(maximum, round(ceil(maximum / step) * step, 8))
    return minimum, maximum


def _linear_fraction(value, limits):
    lo, hi = limits
    if not isfinite(hi - lo):
        # Opposite-signed finite measurements can still overflow the difference.
        value, lo, hi = value / 2, lo / 2, hi / 2
    return (value - lo) / (hi - lo)


def _clip_curve(points, start, end, gap):
    """Clip segments at actual page edges without connecting blanks or long gaps."""
    previous = None
    for depth, value in points:
        if value is None:
            previous = None
            continue
        if previous is not None:
            first_depth, first_value = previous
            distance = depth - first_depth
            if distance > 0 and depth >= start and first_depth <= end and (gap is None or distance <= gap):
                start_leg, end_leg = max(start, first_depth), min(end, depth)
                start_frac, end_frac = (start_leg - first_depth) / distance, (end_leg - first_depth) / distance
                yield ((start_leg, first_value * (1 - start_frac) + value * start_frac),
                       (end_leg, first_value * (1 - end_frac) + value * end_frac))
        previous = depth, value


class Lisa5LithologyReport(LithologyReport):
    """Keep the template's 285 mm width and proportional physical depth axis."""

    custom_paper = True

    def __init__(self, record, start, end, scale, language, options):
        self.basement = options.get("layout") == "lisa5-basement"
        self.related = record.get("related") or {}
        basement = options.get("basement_measurements") if self.basement else None
        basement = basement if isinstance(basement, dict) else {}
        self.density_probe = _reading_points(basement.get("density_probe") or (), density=True, continuous=True)
        self.density_sample = _reading_points(basement.get("density_sample") or (), density=True)
        self.magnetic = _reading_points(basement.get("magnetic") or ())
        self.structure_points = _structural_points(basement.get("structures") or ())
        self.migmatization = _migmatization_intervals(basement.get("migmatization") or ())
        self._migmatization_ends = tuple(last for _, last, _ in self.migmatization)
        self._probe_depths = tuple(depth for depth, value in self.density_probe)
        differences = [b - a for a, b in zip(self._probe_depths, self._probe_depths[1:]) if b > a]
        self.density_gap = 5 * median(differences) if len(differences) >= 3 else None
        super().__init__(record, start, end, scale, language, options)

    def _automatic_depth_range(self):
        if not self.basement:
            return super()._automatic_depth_range()
        depths = chain(
            (e.top for e in self.entries if e.top is not None),
            (e.base for e in self.entries if e.base is not None),
            (d for d, v in chain(self.gamma, self.density_probe, self.density_sample, self.magnetic) if v is not None),
            (row[0] for row in self.structure_points),
            (depth for first, last, _ in self.migmatization for depth in (first, last)),
        )
        first = last = next(depths, 0)
        for depth in depths:
            first, last = min(first, depth), max(last, depth)
        return first, last

    def _probe_readings(self, start, end):
        first = max(0, bisect_left(self._probe_depths, start) - 1)
        last = bisect_right(self._probe_depths, end) + 1
        return self.density_probe[first:last]

    def _basement_ranges(self):
        start, end = self.depth_min, self.depth_max
        probe = self._probe_readings(start, end)
        probe_limits = _outer_scale((2.2, 3.0), chain(
            (value for depth, value in probe if start <= depth <= end),
            (value for segment in _clip_curve(probe, start, end, self.density_gap) for _, value in segment),
        ), .1)
        sample_limits = _outer_scale((2.2, 3.0), (v for d, v in self.density_sample if start <= d <= end), .1)
        density_scales = tuple(scale for scale in (probe_limits, sample_limits) if scale is not None)
        self.density_range = ((min(lo for lo, _ in density_scales), max(hi for _, hi in density_scales))
                              if density_scales else None)
        self.density_probe_visible = probe_limits is not None
        self.density_sample_visible = sample_limits is not None
        self.magnetic_range = _outer_scale((0., 50.), (v for d, v in self.magnetic if start <= d <= end), 10.)
        self.visible_structures = frozenset(kind for d, a, kind, az in self.structure_points if start <= d <= end)
        self.visible_azimuth = any(start <= d <= end and az is not None for d, _, _, az in self.structure_points)
        self.visible_migmatization = self.options.get("patterns", True) and any(
            first < end and last > start for first, last, _ in self.migmatization
        )

    def _migmatization_spans(self, start, end):
        """Cover the requested range without filling missing grades."""
        cursor = start
        offset = bisect_right(self._migmatization_ends, start)
        for index in range(offset, len(self.migmatization)):
            first, last, grade = self.migmatization[index]
            if first >= end:
                break
            a, b = max(start, first), min(end, last)
            if a > cursor:
                yield cursor, a, None, None
            if b > a:
                yield a, b, grade, first
                cursor = b
        if cursor < end:
            yield cursor, end, None, None

    def _configure_layout(self):
        self._basement_ranges()
        rock = {}
        for entry in self.entries:
            if (entry.kind == "unit" and entry.top is not None and
                    entry.top <= self.depth_max and entry.base >= self.depth_min):
                label = entry.lithology
                if label:
                    rock.setdefault(label, _rock_motif(entry))
        self.rocks = tuple(rock.items())
        self.xrd_colors = self._ordered_colors()
        self.series = self._series()
        if self.basement:
            self.rock_columns, self.rock_step = 2, 22
            self.xrd_columns, self.xrd_step = 3, 16
            min_legend = 110
        else:
            self.rock_columns, self.rock_step = 4, 28
            self.xrd_columns, self.xrd_step = 2, 16
            min_legend = 89.28
        legend_height = 0
        if self.options.get("legend", True):
            legend_height = max(min_legend, 27 + ceil(len(self.rocks) / self.rock_columns) * self.rock_step,
                                24 + ceil(len(self.xrd_colors) / self.xrd_columns) * self.xrd_step)
        self.table_top = _LEGEND + legend_height
        self.grid_top = self.table_top + (85.44 if self.basement else 28.32)
        # The shallow sheets include one blank strip between the header grid
        # and depth zero. Basement sheets start directly with geological rows.
        self.body_top = self.grid_top + (0.0 if self.basement else 8.52)
        available = _MAX_HEIGHT - self.body_top - _BOTTOM
        if available < 100:
            raise ValueError(self._bi("Lisa 5 legend on liiga pikk", "The Lisa 5 legend is too long"))
        distance = (self.depth_max - self.depth_min) * self.per_m
        if not isfinite(distance):
            raise ValueError(self._bi("Vigane sügavusvahemik", "Invalid depth range"))
        self.body_height = min(available, max(110.0, distance))
        self.body_bottom = self.body_top + self.body_height
        self.size = (_WIDTH, self.body_bottom + _BOTTOM)

    def _ordered_colors(self):
        catalog = _BASEMENT_XRD if self.basement else _XRD
        entries = {name.casefold(): name for name in self.xrd_colors}
        colors = {}
        for aliases, color in catalog:
            for alias in aliases:
                if alias in entries:
                    colors[entries[alias]] = QColor(color)
        colors.update((name, color) for name, color in self.xrd_colors.items() if name not in colors)
        return colors

    def _series(self):
        if self.basement or not self.options.get("samples", True):
            return ()
        sample_entries = [e for e in self.entries if e.kind == "sample" and e.top is not None]
        identifiers = Counter(lab_key(e.row.get("ID_ajutine")) for e in sample_entries)
        samples = {lab_key(e.row.get("ID_ajutine")): e for e in sample_entries
                   if lab_key(e.row.get("ID_ajutine")) and identifiers[lab_key(e.row.get("ID_ajutine"))] == 1}
        series = list(_tables(self.related, "mall_seeria"))
        counts = Counter(lab_key(s.get("ID_ajutine")) for s in series)
        labels = {lab_key(s.get("ID_ajutine")): _annotation_text(s, "nimi") or _text(s.get("ID_ajutine"))
                  for s in series if lab_key(s.get("ID_ajutine")) and counts[lab_key(s.get("ID_ajutine"))] == 1}
        groups = {}
        for row in _tables(self.related, "mall_seos"):
            series_key, sample = lab_key(row.get("ID_ajutine")), samples.get(lab_key(row.get("algne_id")))
            if series_key in labels and sample is not None:
                groups.setdefault(series_key, []).append(sample)
        return tuple((min(s.top for s in members), max(s.base for s in members), labels[key])
                     for key, members in groups.items())

    def _columns(self):
        if self.basement:
            keys = ("axis", "column", "litho", "gamma", "magnetic", "structures", "specimen", "xrd", "description")
            dividers = (_LEFT, 42.72, 88.32, 172.92, 257.96, 297.12, 428.04, 484.68, 632.16, _RIGHT)
        else:
            keys = ("axis", "column", "gamma", "index", "litho")
            dividers = (_LEFT, 45.36, 90.72, 175.80, 255.12, 325.92)
            if self.series:
                keys += ("series",)
                dividers += (340.20,)
                tails = (388.32, 487.56)
            else:
                tails = (377.04, 476.16)
            keys += ("specimen", "xrd", "description")
            dividers += (*tails, _RIGHT)
        return {key: (x, stop - x) for key, x, stop in zip(keys, dividers, dividers[1:])}

    def _format_lines(self, entry, width):
        note = entry.note
        if entry.kind != "unit" and note:
            note = f"{entry.label} · {note}" if entry.label else note
        if entry.status:
            note = "; ".join(filter(None, (self.t(entry.status), note)))
        return [(line, False) for line in (_wrap(note, width, _font(8)) if note else ())]

    def _fit_notes(self, entries, first, last, include_continuing=False):
        desc, width = self.columns["description"]
        top = self.body_top + 2
        chart_bottom = min(self.body_bottom, self.body_top + (last - first) * self.per_m)
        notes, leftover = [], []
        for entry in entries:
            if entry.top < first and not include_continuing and not entry.point:
                continue
            lines = self._format_lines(entry, width - 9)
            if not lines:
                continue
            anchor = self.body_top + (max(first, min(last, entry.top)) - first) * self.per_m
            next_y = max(anchor + 2, top)
            if next_y + 9 * len(lines) > chart_bottom + 0.1:
                leftover.append(entry)
                continue
            notes.append(Annotation(entry.kind, anchor, desc, next_y, lines))
            top = next_y + 9 * len(lines) + 3
        return tuple(notes), leftover

    @staticmethod
    def _line(painter, x0, y0, x1, y1, color=_BLACK, width=.38):
        painter.setPen(QPen(color, width))
        painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    @staticmethod
    def _text_at(painter, x, y, text, size=8, color=_BLACK, bold=False, width=None):
        painter.setFont(font := _font(size, bold))
        painter.setPen(color)
        text = _text(text).replace("\n", " ")
        if width is not None:
            text = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QPointF(x, y), text)

    def _center(self, painter, x, w, y, text, size=8, color=_BLACK, bold=False):
        text = _text(text)
        available = max(w - 2, 0)
        metrics = QFontMetricsF(_font(size, bold))
        while size > 6 and metrics.horizontalAdvance(text) > available:
            size -= 1
            metrics = QFontMetricsF(_font(size, bold))
        text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, available)
        self._text_at(painter, x + (w - metrics.horizontalAdvance(text)) / 2, y, text, size, color, bold)

    def _box(self, painter, rect, color=_BLACK, width=.38):
        painter.setPen(QPen(color, width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def _header(self, painter, page, index):
        self._box(painter, QRectF(_LEFT, _HEADER, _RIGHT - _LEFT, _HEADER_END - _HEADER))
        left, mid, right = 27.65, 242.4, 520.2
        for column in (226.8, 510.24):
            self._line(painter, column, _HEADER + 5.2, column, _HEADER_END - 5.5)
        attrs = self.attrs
        alias = _text(_get(attrs, "alias"))
        title = f"{self.title} ({alias})" if alias and alias != self.title else self.title
        self._text_at(painter, left, _HEADER + 19.3, title, 13, width=190)
        self._line(painter, 20.2, _HEADER + 27.6, 210.0, _HEADER + 27.6)
        location = _text(_get(attrs, "asukoht", "location", "aadress", "address"))
        site = self._bi("Puuraugu asukoht", "Borehole location")
        self._text_at(painter, left, _HEADER + 48.2, site + ":", 10)
        for i, line in enumerate(_wrap(location, 82, _font(9))[:2] if location else ()):
            self._text_at(painter, left + 99, _HEADER + 48.2 + i * 10.1, line, 9)
        self._text_at(painter, left, _HEADER + 78.8, self.t("Koordinaadid") + ":", 10)
        east, north = _number(_get(attrs, "geom_x", "x")), _number(_get(attrs, "geom_y", "y"))
        if north is not None:
            self._text_at(painter, left + 76, _HEADER + 78.8, f"X {self._fmt(north, 2)}", 10)
        if east is not None:
            self._text_at(painter, left + 76, _HEADER + 89.6, f"Y {self._fmt(east, 2)}", 10)
        # X and Y follow the reference's surveying convention, not GIS X/Y.
        length = _number(_get(attrs, "pikkus", "depth", "length"))
        inclination = _number(_get(attrs, "kallakusnurk", "kalle", "inclination"))
        azimuth = _number(_get(attrs, "asimuut", "azimuth"))
        method = _get(attrs, "puurimismeetod_label", "puurimismeetod", "drilling_method")
        drilling_date = _get(attrs, "puurimise_kuupaev", "valmimise_kuupaev", "completion_date")
        groups = [
            (self._bi("Puurimismeetod", "Drilling method"), method),
            (self._bi("Puuraugu pikkus (m)", "Borehole length (m)"), self._fmt(length) if length is not None else ""),
            (self._bi("Puurimise kuupäev", "Drilling date"), drilling_date),
        ]
        if inclination is not None:
            groups.append((self._bi("Puuraugu kallakusnurk", "Borehole inclination"), self._fmt(inclination) + "°"))
        if azimuth is not None:
            groups.append((self._bi("Puuraugu asimuut", "Borehole azimuth"), self._fmt(azimuth) + "°"))
        step = 22.4 if len(groups) == 3 else 17.6
        start = 42.2 if len(groups) == 3 else 21.3
        for i, (label, value) in enumerate(groups):
            y = _HEADER + start + step * i
            self._text_at(painter, mid, y, label + ":", 10)
            off = QFontMetricsF(_font(10)).horizontalAdvance(label + ":") + 8
            self._text_at(painter, mid + off, y, value, 9, width=255 - off)
        self._text_at(painter, right, _HEADER + 20.2, self._bi("Koostajad:", "Prepared by:"), 10)
        author = self.options.get("author") or _get(attrs, "isik_nimi")
        for j, line in enumerate(_wrap(author, 207, _font(10))[:3] if author else ()):
            self._text_at(painter, right, _HEADER + 44 + 11 * j, line, 10)
        self._text_at(painter, 690.2, _HEADER + 77.0, self._bi("Koostamise kuupäev:", "Report date:"), 9)
        self._text_at(painter, 731.4, _HEADER + 93.0, self.options.get("report_date", ""), 9, width=60)
        if self.page_count > 1:
            self._text_at(painter, _RIGHT - 35, self.size[1] - 39.2,
                          f"{index + 1} / {self.page_count}", 8)

    def _legend(self, painter, page):
        if not self.options.get("legend", True):
            return
        self._line(painter, _LEFT, _LEGEND, _RIGHT, _LEGEND)
        self._line(painter, _LEFT, _LEGEND, _LEFT, self.table_top)
        self._text_at(painter, _LEFT + 5.5, _LEGEND + 11.4, self._bi("Kivimi tüüp:", "Rock type:"), 8)
        rock_step_x = 114 if not self.basement else 126
        rows = max(2, ceil(len(self.rocks) / self.rock_columns))
        for i, (name, motif) in enumerate(self.rocks):
            col, row = divmod(i, rows)
            x = _LEFT + 5 + col * rock_step_x
            y = _LEGEND + 19 + row * self.rock_step
            width = 44.8 if not self.basement else 28.4
            height = 21.8 if not self.basement else 13.4
            rect = QRectF(x, y, width, height)
            fill = (_ROCK_FILL.get(motif, "#f3f3f3") if self.basement and
                    self.options.get("colors", True) else "#ffffff")
            _pattern(painter, rect, motif, QColor(fill), self.options.get("patterns", True))
            self._box(painter, rect)
            self._text_at(painter, x + width + 5, y + height / 2 + 2.5, name, 7,
                          width=rock_step_x - width - 8)
        xrd_x = 555.0 if self.basement else 509.0
        if self.basement:
            if self.visible_migmatization:
                self._text_at(painter, 276, _LEGEND + 11.4,
                              self._bi("Migmatiseerumise aste:", "Degree of migmatization:"), 8)
                for row, (grade, estonian, english) in enumerate(_MIGMATIZATION_LEGEND):
                    y = _LEGEND + 24.7 + 19.7 * row
                    rect = QRectF(276, y, 28.3, 14)
                    _migmatization_pattern(painter, rect, grade, PAPER)
                    self._box(painter, rect)
                    self._text_at(painter, 310.5, y + 9.2, self._bi(estonian, english), 7, width=129)
            self._text_at(painter, 441.5, _LEGEND + 11.4,
                          self._bi("Struktuurielemendid:", "Structural elements:"), 8)
            structure_labels = (
                ("foliation", self._bi("Gneisilisus", "Foliation")),
                ("fracture", self._bi("Lõhed", "Fractures")),
                ("other", self._bi("Muu", "Other")),
            )
            for row, (kind, label) in enumerate(
                (pair for pair in structure_labels if pair[0] in self.visible_structures)
            ):
                y = _LEGEND + 24.7 + 13 * row
                self._structure_symbol(painter, 452.5, y, kind, 45 if self.visible_azimuth else None, None)
                self._text_at(painter, 472, y + 2.4, label, 7, width=77)
            if self.visible_azimuth:
                self._text_at(painter, 443.5, _LEGEND + 67,
                              self._bi("Joon: asimuut", "Tail: azimuth"), 7, width=99)
        self._text_at(painter, xrd_x, _LEGEND + 11.4, "XRD:", 8)
        rows = max(1, ceil(len(self.xrd_colors) / self.xrd_columns))
        advance = (_RIGHT - xrd_x) / self.xrd_columns
        for i, (name, color) in enumerate(self.xrd_colors.items()):
            col, row = divmod(i, rows)
            x, y = xrd_x + col * advance, _LEGEND + 20.8 + row * self.xrd_step
            width = 22.5 if self.basement else 28.3
            rect = QRectF(x, y, width, 10.5)
            painter.fillRect(rect, color)
            self._box(painter, rect)
            self._text_at(painter, x + width + 4.6, y + 7.5, name, 7, width=advance - width - 8)

    def _caption(self, painter, key, lines):
        x, w = self.columns[key]
        for i, line in enumerate(lines):
            self._center(painter, x, w, self.table_top + 11.3 + i * 12.0, line)

    def _track_scale(self, painter, key, first, last, units, color=_BLACK):
        x, width = self.columns[key]
        underline = self.table_top + 14.6
        self._line(painter, x + 4.8, underline, x + width - 4.8, underline, color, .65)
        self._text_at(painter, x + 4.8, underline + 10.2, first, 7)
        self._center(painter, x, width, underline + 10.2, units, 7)
        metric = QFontMetricsF(_font(7))
        self._text_at(painter, x + width - 4.8 - metric.horizontalAdvance(last), underline + 10.2, last, 7)

    def _scale_caption(self, painter, key, first, last, units):
        x, width = self.columns[key]
        y = self.table_top + 25.1
        self._text_at(painter, x + 4.8, y, first, 7)
        self._center(painter, x, width, y, units, 7)
        w = QFontMetricsF(_font(7)).horizontalAdvance(last)
        self._text_at(painter, x + width - 4.8 - w, y, last, 7)

    def _axis_value(self, value):
        if abs(value) >= 10000 or 0 < abs(value) < .001:
            text = f"{value:.2g}"
            return text if self.en else text.replace(".", ",")
        return self._fmt(value)

    def _basement_scale(self, painter, key, limits, units, line_y, *, color=_BLACK, margin=3.0):
        x, w = self.columns[key]
        x0, x1 = x + margin, x + w - margin
        self._line(painter, x0, line_y, x1, line_y, color, .64)
        for xx in (x0, x1):
            self._line(painter, xx, line_y - 1.7, xx, line_y + 1.7, color, .52)
        labels = [self._axis_value(value) for value in limits]
        for size in (7, 6, 5):
            metric = QFontMetricsF(_font(size))
            widths = [metric.horizontalAdvance(s) for s in (labels[0], units, labels[1])]
            if widths[0] + widths[2] + (widths[1] + 2 if units else 0) <= x1 - x0:
                break
        self._text_at(painter, x0, line_y + 9.5, labels[0], size)
        self._text_at(painter, x1 - widths[2], line_y + 9.5, labels[1], size)
        if units:
            pos = max(x0 + widths[0] + 1, (x0 + x1 - widths[1]) / 2)
            pos = min(pos, x1 - widths[2] - widths[1] - 1)
            if pos >= x0 + widths[0]:
                self._text_at(painter, pos, line_y + 9.5, units, size)

    def _chart(self, painter, page):
        top = self.body_top
        bottom = top + (page.end - page.start) * self.per_m
        desc_start = self.columns["description"][0]

        def y(value):
            return top + (value - page.start) * self.per_m

        for x, _ in self.columns.values():
            self._line(painter, x, self.table_top, x, bottom)
        self._line(painter, _RIGHT, self.table_top, _RIGHT, bottom)
        for yy in (self.table_top, self.grid_top, bottom):
            self._line(painter, _LEFT, yy, _RIGHT, yy)
        self._caption(painter, "axis", [self._bi("Süg. (m)", "Depth (m)"), f"1:{self._fmt(self.scale)}"])
        self._caption(painter, "column", [self._bi("Kivimi tüüp", "Rock type")])
        self._caption(painter, "gamma", [
            self._bi("Looduskiirgus", "Natural radioactivity") if self.basement else
            self._bi("Gammakiirgus", "Gamma radiation"),
        ])
        self._caption(painter, "litho", [
            self._bi("Põhikivimi nimetus", "Host rock") if self.basement else
            self._bi("Kivimi nimetus", "Rock name"),
        ] + ([] if self.basement else [self._bi("Alumine piir (m)", "Lower limit (m)")]))
        if not self.basement:
            self._caption(painter, "index", [self._bi("Üksus ja väljatulek (m)", "Unit and recovery (m)")])
        else:
            self._caption(painter, "magnetic", ["Mag. susc."])
            self._caption(painter, "structures", [self._bi("Struktuurielemendid", "Structural elements")])
            x, w = self.columns["gamma"]
            density_rows = (
                (self._bi("Tihedus (sond)", "Density (probe)"), self.density_probe_visible),
                (self._bi("Tihedus (proov)", "Density (sample)"), self.density_sample_visible),
            )
            for i, (label, visible) in enumerate(density_rows):
                yy = self.table_top + 28.4 * (1 + i)
                self._line(painter, x, yy, x + w, yy)
                self._center(painter, x, w, yy + 10.0, label, 8)
                if visible:
                    self._basement_scale(painter, "gamma", self.density_range, "g/cm³", yy + 15.6)
            if self.magnetic_range:
                self._basement_scale(painter, "magnetic", self.magnetic_range, "mSI", self.table_top + 14.6)
            if self.visible_structures:
                self._basement_scale(painter, "structures", (0, 90), "°", self.table_top + 14.6)
        self._caption(painter, "specimen", [
            self._bi("Proovi nr.", "Sample no.") if self.options.get("samples", True) else
            self._bi("Analüüsi nr.", "Analysis no."),
        ])
        self._caption(painter, "xrd", ["XRD"])
        self._caption(painter, "description", [
            (self._bi("Kommentaarid", "Comments") if self.basement else self.t("Kirjeldus")),
        ])
        if self.gamma_range:
            low, high = self.gamma_range
            self._track_scale(painter, "gamma", self._fmt(low, 1), self._fmt(high, 1), self.gamma_unit,
                              _RED if self.basement else _BLUE)
        self._scale_caption(painter, "xrd", "0", "100", "%")
        self._xrd_header(painter)
        gamma_x, gamma_width = self.columns["gamma"]
        for i in (1, 2, 3):
            x = gamma_x + i * gamma_width / 4
            self._line(painter, x, self.grid_top, x, bottom, _GRID, .38)
        if self.basement:
            self._basement_grid(painter, page, y, bottom)
        self._ruler(painter, page, y)
        if self.visible_migmatization:
            self._paint_migmatization_without_host(painter, page, y)
        for entry in page.entries:
            if entry.kind != "unit":
                continue
            self._paint_unit(painter, page, entry, y, desc_start)
        for scope in page.notes:
            # If a long note crosses a shallower row's next boundary, preserve
            # the geological boundary in the other lanes without striking text.
            painter.fillRect(QRectF(desc_start + 4, scope.y, _RIGHT - desc_start - 4.5,
                                    len(scope.lines) * 9 - .4), PAPER)
            if abs(scope.y - scope.anchor) > 4:
                self._line(painter, desc_start, scope.anchor, desc_start + 4, scope.y + 4,
                           _BLACK, .22)
            if scope.kind == "unit":
                self._line(painter, desc_start, scope.y - .5, _RIGHT, scope.y - .5,
                           _BLACK, .3)
            for i, (line, bold) in enumerate(scope.lines):
                self._text_at(painter, desc_start + 4.5, scope.y + 7.2 + 9 * i, line, 8,
                              bold=bold, width=_RIGHT - desc_start - 7)
        for top_depth, bottom_depth, label in self.series:
            if top_depth <= page.end and bottom_depth >= page.start:
                self._paint_series(painter, max(top_depth, page.start), min(bottom_depth, page.end), y, label)
        self._paint_specimens(painter, page, y, bottom)
        if self.basement:
            self._paint_basement_readings(painter, page, y, bottom)
        if self.gamma_range:
            # The scales are already printed in the shared table header.
            self._paint_gamma(painter, page, y, label=False, color=_RED if self.basement else _BLUE)
        self._paint_xrd(painter, page, y)

    def _ruler_ticks(self, page):
        raw = 26 / self.per_m
        step = next((val * 10**exponent for exponent in range(-5, 7)
                     for val in (1, 2, 5) if val * 10**exponent >= raw), raw)
        first = ceil(page.start / step - 1e-8)
        last = floor(page.end / step + 1e-8)
        return step, (step * index for index in range(first, last + 1))

    def _ruler(self, painter, page, y):
        x, width = self.columns["axis"]
        step, ticks = self._ruler_ticks(page)
        for depth in ticks:
            yy = y(depth)
            self._line(painter, x, yy, x + 3.8, yy)
            display = f"{depth:.1f}" if step >= .1 else f"{depth:g}"
            baseline = max(self.grid_top + 8, min(y(page.end) - 2.2, yy + 2.8))
            self._center(painter, x + 4, width - 5, baseline, display, 8)
            if depth + step / 2 < page.end:
                self._line(painter, x, y(depth + step / 2), x + 2.1, y(depth + step / 2))

    def _basement_grid(self, painter, page, y, bottom):
        if not any((self.density_range, self.magnetic_range, self.visible_structures)):
            return
        x0, x1 = self.columns["gamma"][0], self.columns["specimen"][0]
        _, ticks = self._ruler_ticks(page)
        for tick in ticks:
            if page.start < tick < page.end:
                self._line(painter, x0, y(tick), x1, y(tick), _GRID, .44)
        if self.magnetic_range:
            x, width = self.columns["magnetic"]
            xx = (self._track_x("magnetic", 0.0, self.magnetic_range)
                  if self.magnetic_range[0] < 0 else x + width / 2)
            self._line(painter, xx, self.body_top, xx, bottom, _GRID, .34)
        if self.visible_structures:
            for angle in range(10, 90, 10):
                xx = self._track_x("structures", angle, (0, 90))
                self._line(painter, xx, self.body_top, xx, bottom, _GRID, .38)

    def _track_x(self, key, value, limits):
        x, width = self.columns[key]
        return x + 3 + (width - 6) * _linear_fraction(value, limits)

    def _paint_bar(self, painter, y, x0, x1, top, bottom):
        if abs(x1 - x0) < .05:
            # A measured zero or a minimum-scale sample is a real datum.
            self._line(painter, x0, max(top, y - 1.5), x0, min(bottom, y + 1.5), _BLACK, .65)
            return
        a, b = max(top, y - 1.8), min(bottom, y + 1.8)
        rect = QRectF(min(x0, x1), a, abs(x0 - x1), b - a)
        painter.fillRect(rect, _BAR)
        self._box(painter, rect, _BLACK, .42)

    def _paint_basement_readings(self, painter, page, y, bottom):
        if self.density_range:
            limits = self.density_range
            origin = self._track_x("gamma", limits[0], limits)
            for depth, value in self.density_sample:
                if page.start <= depth <= page.end:
                    self._paint_bar(painter, y(depth), origin, self._track_x("gamma", value, limits),
                                    self.body_top, bottom)
            self._paint_probe(painter, page, y, bottom)
        if self.magnetic_range:
            limits = self.magnetic_range
            origin = self._track_x("magnetic", 0, limits)
            for depth, value in self.magnetic:
                if page.start <= depth <= page.end:
                    self._paint_bar(painter, y(depth), origin, self._track_x("magnetic", value, limits),
                                    self.body_top, bottom)
        if self.visible_structures:
            x, width = self.columns["structures"]
            bounds = QRectF(x, self.body_top, width, bottom - self.body_top)
            for depth, angle, kind, azimuth in self.structure_points:
                if page.start <= depth <= page.end:
                    self._structure_symbol(painter, self._track_x("structures", angle, (0, 90)),
                                           y(depth), kind, azimuth, bounds)

    def _paint_probe(self, painter, page, y, bottom):
        points = self._probe_readings(page.start, page.end)
        limits = self.density_range
        path = QPainterPath()
        for a, b in _clip_curve(points, page.start, page.end, self.density_gap):
            path.moveTo(self._track_x("gamma", a[1], limits), y(a[0]))
            path.lineTo(self._track_x("gamma", b[1], limits), y(b[0]))
        # A one-point reading and each end of an explicit gap are retained.
        for depth, value in points:
            if value is not None and page.start <= depth <= page.end:
                xx, yy = self._track_x("gamma", value, limits), y(depth)
                path.moveTo(xx - .43, yy)
                path.lineTo(xx + .43, yy)
        painter.setPen(QPen(_BLACK, .76))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _structure_symbol(self, painter, x, y, kind, azimuth, bounds):
        if azimuth is not None:
            angle = radians(azimuth)
            dx, dy = sin(angle), -cos(angle)  # clockwise from page up
            size = 12.5 if bounds is not None else 9.0
            if bounds is not None:
                if dx > 1e-9:
                    size = min(size, (bounds.right() - x) / dx)
                elif dx < -1e-9:
                    size = min(size, (bounds.left() - x) / dx)
                if dy > 1e-9:
                    size = min(size, (bounds.bottom() - y) / dy)
                elif dy < -1e-9:
                    size = min(size, (bounds.top() - y) / dy)
            if size > 1.0:
                end_x, end_y = x + size * dx, y + size * dy
                painter.setPen(QPen(_BLACK, .34))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if kind == "foliation":
                    def control(frac, bend):
                        u, v = x + size * frac * dx - bend * dy, y + size * frac * dy + bend * dx
                        if bounds is not None:
                            u = max(bounds.left(), min(bounds.right(), u))
                            v = max(bounds.top(), min(bounds.bottom(), v))
                        return QPointF(u, v)

                    path = QPainterPath(QPointF(x, y))
                    path.cubicTo(control(.23, 2.6), control(.71, -2.6), QPointF(end_x, end_y))
                    painter.drawPath(path)
                else:
                    painter.drawLine(QPointF(x, y), QPointF(end_x, end_y))
        radius = 2.65
        circle = QPainterPath()
        circle.addEllipse(QPointF(x, y), radius, radius)
        if bounds is not None and not bounds.contains(circle.boundingRect()):
            area = QPainterPath()
            area.addRect(bounds)
            circle = circle.intersected(area)  # SVG does not honour Qt clipRect reliably.
        painter.fillPath(circle, _STRUCTURE_COLORS[kind])

    def _paint_migmatization_without_host(self, painter, page, y):
        """Plot measured grades even in gaps in the host-rock log."""
        x, width = self.columns["column"]

        def paint_gap(start, end):
            for a, b, grade, origin in self._migmatization_spans(start, end):
                if grade is not None:
                    rect = QRectF(x, y(a), width, y(b) - y(a))
                    _migmatization_pattern(painter, rect, grade, PAPER, (a - origin) * self.per_m)

        cursor = page.start
        for entry in page.entries:
            if entry.kind != "unit" or entry.point:
                continue
            a, b = max(page.start, entry.top), min(page.end, entry.base)
            if a > cursor:
                paint_gap(cursor, a)
            cursor = max(cursor, b)
        if cursor < page.end:
            paint_gap(cursor, page.end)

    def _paint_unit(self, painter, page, entry, y, desc_start):
        ax, aw = self.columns["column"]
        start, end = max(page.start, entry.top), min(page.end, entry.base)
        a, b = y(start), y(end)
        if entry.point:
            self._line(painter, ax + 1, a, ax + aw - 1, a, _BLACK, .8)
            return
        if b <= a:
            return
        motif = _rock_motif(entry)
        color = QColor(_ROCK_FILL.get(motif, "#efefef")) if self.options.get("colors", True) else PAPER
        if not self.basement and entry.index[:1].upper() in {"O", "S", "D"} and motif in {"clay", "sand", "gravel"}:
            color = QColor("#a3dcb6") if self.options.get("colors", True) else PAPER
        rect = QRectF(ax, a, aw, b - a)
        if self.visible_migmatization:
            for z0, z1, grade, origin in self._migmatization_spans(start, end):
                piece = QRectF(ax, y(z0), aw, y(z1) - y(z0))
                if grade is None:
                    _pattern(painter, piece, motif, color)
                else:
                    _migmatization_pattern(painter, piece, grade, color, (z0 - origin) * self.per_m)
        else:
            _pattern(painter, rect, motif, color, self.options.get("patterns", True))
        self._box(painter, rect)
        rock_x, rock_w = self.columns["litho"]
        self._line(painter, rock_x, a, rock_x + rock_w, a)
        self._line(painter, rock_x, b, rock_x + rock_w, b)
        if b - a >= 9.0:
            self._center(painter, rock_x + 1, rock_w - 2, a + 7.2, entry.lithology)
        if not self.basement and entry.base <= page.end and b - a >= 18:
            self._center(painter, rock_x, rock_w, b - 3.1, f"{entry.base:.2f}")
        if not self.basement:
            xx, ww = self.columns["index"]
            self._line(painter, xx, a, xx + ww, a)
            self._line(painter, xx, b, xx + ww, b)
            length = _number(_get(entry.row, "paksus"))
            if length is None:
                length = entry.base - entry.top
            recovery = _number(_get(entry.row, "valjatulek"))
            if b - a >= 9.0:
                numbers = self._fmt(length) if recovery is None else f"{self._fmt(length)}/{self._fmt(recovery)}"
                tag = f"{entry.index} ({numbers})".strip()
                self._center(painter, xx + 1, ww - 2, a + 7.2, tag, 8)
        self._line(painter, desc_start, a, _RIGHT, a, _BLACK, .38)

    def _paint_series(self, painter, a, b, y, label):
        left, width = self.columns.get("series", (0.0, 0.0))
        if width == 0:
            return
        top, base = y(a), y(b)
        self._line(painter, left + .5, top, left + width - .5, top, _RED, .38)
        self._line(painter, left + .5, base, left + width - .5, base, _RED, .38)
        if base - top < 14:
            return
        painter.save()
        try:
            painter.translate(left + width / 2 + 2.4, (top + base) / 2)
            painter.rotate(-90)
            self._center(painter, -(base - top) / 2, base - top, 0, label, 7, _RED)
        finally:
            painter.restore()

    def _specimens(self, page):
        samples = Counter(lab_key(e.row.get("ID_ajutine")) for e in page.entries if e.kind == "sample")
        for entry in page.entries:
            if entry.kind not in {"sample", "measurement"} or not entry.label:
                continue
            linked = lab_key(entry.row.get("proov_id"))
            if entry.kind == "measurement" and linked and samples[linked] == 1:
                continue
            yield entry

    def _paint_specimens(self, painter, page, y, bottom):
        x, w = self.columns["specimen"]
        occupied = self.body_top - 1
        for entry in self._specimens(page):
            z = y((max(page.start, entry.top) + min(page.end, entry.base)) / 2)
            mark = min(max(z - 5.0, occupied + .8, self.body_top), bottom - 10.0)
            if mark < self.body_top or mark < occupied:
                continue
            if abs(mark + 5 - z) > 1:
                self._line(painter, x, z, x + 2.5, mark + 5)
            points = (
                QPointF(x, mark), QPointF(x + w - 2.3, mark), QPointF(x + w, mark + 5),
                QPointF(x + w - 2.3, mark + 10), QPointF(x, mark + 10),
            )
            painter.setPen(QPen(_BLACK, .38))
            painter.setBrush(PAPER)
            painter.drawPolygon(QPolygonF(points))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            self._center(painter, x, w - 2.3, mark + 7.1, entry.label, 7, _BLUE)
            occupied = mark + 10

    def _xrd_header(self, painter):
        if not self.xrd_colors:
            return
        x, w = self.columns["xrd"]
        a, b = x + 5.2, x + w - 5.3
        each = (b - a) / len(self.xrd_colors)
        for i, color in enumerate(self.xrd_colors.values()):
            r = QRectF(a + i * each, self.table_top + 13.4, each, 5)
            painter.fillRect(r, color)
            self._box(painter, r)

    def _paint_xrd(self, painter, page, y):
        x, width = self.columns["xrd"]
        bottom = y(page.end)
        for entry in page.entries:
            if not entry.xrd or not self.xrd_colors:
                continue
            values = dict(entry.xrd)
            middle = (max(page.start, entry.top) + min(page.end, entry.base)) / 2
            h = min(9.4, bottom - self.body_top)
            yy = max(self.body_top, min(bottom - h, y(middle) - h / 2))
            left = x
            for name, color in self.xrd_colors.items():
                frac = values.get(name, 0) / 100
                if frac > 0:
                    rect = QRectF(left, yy, width * frac, h)
                    painter.fillRect(rect, color)
                    self._box(painter, rect)
                    left += width * frac
            self._box(painter, QRectF(x, yy, width, h))
