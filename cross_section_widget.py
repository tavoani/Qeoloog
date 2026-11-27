"""Interactive multi-well cross-section builder for Qeoloog."""

import json
from math import ceil
from uuid import uuid4

from qgis.PyQt.QtCore import QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsFeatureRequest,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

from .cross_section import (
    line_from_items,
    number,
    point_at_station,
    polyline_length,
    section_positions,
)
from .observations import observation_index
from .section_workspace import SectionWorkspace, SectionWorkspaceError
from .section_workspace_ui import (
    SectionWorkspaceMixin, WORKSPACE_ENTRY, public_workspace_items,
    section_record_ids, section_source_ref,
)
from . import section_tracks as tracks
from . import outcrop_features as outcrop
from .outcrop_drawing import OutcropCanvasEditMixin, OutcropDrawingWidgetMixin


STATE_SCOPE = "Qeoloog"
STATE_KEY = "cross_section_v1"
METRIC_CRS = QgsCoordinateReferenceSystem("EPSG:3301")


def _safe_number(value, fallback=0.0):
    result = number(value)
    return fallback if result is None else result


def _unit_index(unit):
    index = unit.get("indeks") or unit.get("indeks_orig") or ""
    if str(index).strip().casefold() != "liitüksus":
        result = str(index)
        if (
            unit.get("_qeoloog_unpenetrated")
            and result and not result.endswith("+")
        ):
            result += "+"
        return result
    lower = str(unit.get("liityksus_indeks_alumine") or "").strip()
    upper = str(unit.get("liityksus_indeks_ylemine") or "").strip()
    invalid = {"", "ei kohaldu", "teadmata"}
    lower = "" if lower.casefold() in invalid else lower
    upper = "" if upper.casefold() in invalid else upper
    result = (
        f"{lower}-{upper}"
        if lower and upper and lower != upper else lower or upper
    )
    if (
        unit.get("_qeoloog_unpenetrated")
        and result and not result.endswith("+")
    ):
        result += "+"
    return result


def _stratigraphic_color(unit):
    first = _unit_index(unit).replace(" ", "").upper().replace("–", "-")
    mappings = (
        ("Q2", "#fff2cc"), ("Q1", "#fff2ae"), ("Q", "#fcfc8b"),
        ("D3", "#f1e19d"), ("D2-3", "#f1d583"),
        ("D2", "#f1c868"), ("D1-2", "#ebba5b"),
        ("D1", "#e5ac4d"), ("D", "#cb8c37"),
        ("S4", "#e6f5e1"), ("S3-4", "#d3eed8"),
        ("S3", "#bfe6cf"), ("S2-3", "#b9e4c9"),
        ("S2", "#a6dcbb"), ("S1-2", "#a6dcbb"),
        ("S1", "#8cd1a3"), ("S", "#b3e1b6"),
        ("O3", "#7fca93"), ("O2", "#4db47e"),
        ("O1-2", "#34a977"), ("O1", "#1a9d6f"),
        ("O", "#009270"), ("CM4", "#b3e095"),
        ("CM3", "#a6cf86"), ("CM2", "#99c078"),
        ("CM1", "#8cb06c"), ("CM", "#7fa056"),
        ("E", "#ffdc88"), ("MP", "#fac180"), ("PP", "#ec607e"),
    )
    for prefix, color in mappings:
        if first.startswith(prefix):
            return QColor(color)
    category = int(_safe_number(
        unit.get("klassif_yksus_kood") or unit.get("yksus_kood")
    ))
    return QColor({
        1: "#fcfc8b", 2: "#a7a7a7", 3: "#ec607e", 997: "#a7a7a7",
    }.get(category, "#a7a7a7"))


class CrossSectionCanvas(OutcropCanvasEditMixin, QWidget):
    """Draw several existing Qeoloog profile snapshots on shared axes."""

    scaleChanged = pyqtSignal(float, float)
    itemActivated = pyqtSignal(str)
    recordActivated = pyqtSignal(str, str, object)
    drawingAction = pyqtSignal(str, str, object)
    drawingFeedback = pyqtSignal(str)

    def _plot_rows(self):
        mode = "equal" if self.mode in {"relative", "correlation"} else self.mode
        result = []
        for row in section_positions(self.items, mode, self.line):
            position = tracks.finite_number(row.get("_station"))
            axis = tracks.LogAxis.from_row(
                row, self.mode, self.alignments.get(str(row.get("key") or ""))
            )
            if position is None or axis is None:
                continue
            row["_log_axis"] = axis
            limits = (*tracks.measured_extent(row), *outcrop.measured_positions(row))
            row["_measured_extent"] = (min(limits), max(limits))
            row["_curves"] = tracks.curve_groups(row.get("isotopes") or ())
            result.append(row)
        return result

    def _slider_width(self):
        width = tracks.finite_number(self.layout_options.get("column_width"))
        return min(100.0, max(20.0, width)) if width is not None else 58.0

    def _advanced_track_specs(self, row):
        for key in tracks.track_order(self.layout_options):
            if not self.display.get(key, True):
                continue
            if key == "isotopes":
                for group in row.get("_curves", ()):
                    yield key, group, 100
            elif key == "biofinds":
                points = tracks.biofind_positions(row.get(key) or ())
                if points:
                    yield key, points, tracks.biofind_width(points)
            else:
                values = row.get(key)
                if values:
                    for group in tracks.band_groups(values):
                        yield key, group, 86

    def _outcrop_editing(self, row):
        return bool(row.get("key") and row["key"] == getattr(self, "outcrop_edit_key", ""))

    def _advanced_width(self, rows, include_edit_lanes=True):
        return max((
            sum(width + 7 for _, _, width in self._advanced_track_specs(row))
            + outcrop.outcrop_width(row, self.display, include_edit_lanes and self._outcrop_editing(row))
            for row in rows
        ), default=0)

    def _metric_terrain(self):
        return [] if self.mode in {"relative", "correlation"} else self.terrain

    def _show_wellheads(self):
        return self.display["wellheads"] and self.mode not in {"relative", "correlation"}

    def effective_horizontal_scale(self):
        """Uniformly enlarge the metric axis, never move individual collars."""
        return self._plot_scale(self._plot_rows())

    def _plot_scale(self, rows):
        if self.horizontal_scale_manual:
            return self.horizontal_scale
        positions = sorted({row["_station"] for row in rows})
        gaps = [b - a for a, b in zip(positions, positions[1:]) if b - a > 1e-6]
        clearance = 232.0 + max(0, self._slider_width() - 58.0) + self._advanced_width(rows)
        return max(self.horizontal_scale, clearance / min(gaps)) if gaps else self.horizontal_scale

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.items = []
        self.mode = "line"
        self.line = []
        self.terrain = []
        self.horizontal_scale = 0.12
        self.horizontal_scale_manual = False
        self.vertical_scale = 4.0
        self.style = "classic"
        self.correlations = []
        self.alignments = {}
        self.layout_options = {}
        self._paint_hits = []
        self._capture_hits = False
        self._init_outcrop_mouse()
        self.display = {
            "indices": True,
            "lithology": True,
            "boundaries": True,
            "core": True,
            "samples": True,
            "analyses": True,
            "specimens": True,
            "construction": True,
            "water": True,
            "wellheads": True,
            "terrain": True,
            "isotopes": True,
            "biofinds": True,
            "biozones": False,
            "stages": True,
            "correlations": True,
        }
        self.setMinimumSize(700, 500)

    def set_model(
        self, items=None, mode=None, line=None, terrain=None,
        horizontal_scale=None, vertical_scale=None, display=None,
        style=None, correlations=None, alignments=None, layout=None,
    ):
        if items is not None:
            self.items = list(items)
        if mode is not None:
            self.mode = mode
        if line is not None:
            self.line = list(line)
        if terrain is not None:
            self.terrain = list(terrain)
        if horizontal_scale is not None:
            self.horizontal_scale = float(horizontal_scale)
        if vertical_scale is not None:
            self.vertical_scale = float(vertical_scale)
        if display is not None:
            self.display.update(display)
        if style is not None:
            self.style = "stratapy" if style == "stratapy" else "classic"
        if correlations is not None:
            self.correlations = list(correlations)
        if alignments is not None:
            self.alignments = dict(alignments)
        if layout is not None:
            self.layout_options = dict(layout)
        rows = self._plot_rows()
        stations = [
            row["_station"] for row in rows if row.get("_station") is not None
        ]
        span = max(stations, default=0.0) - min(stations, default=0.0)
        minimum, maximum = tracks.axis_range(rows, self._metric_terrain())
        left, right, top, bottom = self._margins(rows)
        self.setMinimumWidth(min(16777215, max(700, ceil(
            left + right + 52 + span * self._plot_scale(rows)
        ))))
        self.setMinimumHeight(max(
            500, min(16777215, round(top + bottom + 15 + (maximum - minimum) * self.vertical_scale))
        ))
        self.resize(self.minimumSize())
        self.updateGeometry()
        self.update()

    def wheelEvent(self, event):
        if self._outcrop_drag:
            event.accept()
            return
        modifiers = event.modifiers()
        delta_point = event.angleDelta()
        if delta_point.isNull():
            # macOS/precision touchpads can send only pixelDelta(). Use the
            # full gesture magnitude so small updates do not become 20% jumps.
            delta_point = event.pixelDelta()
        vertical_zoom = bool(modifiers & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ))
        horizontal_zoom = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        horizontal_gesture = abs(delta_point.x()) > abs(delta_point.y())
        if not (vertical_zoom or horizontal_zoom or horizontal_gesture):
            event.ignore()
            return
        delta = (delta_point.x() if horizontal_gesture else delta_point.y())
        if not delta:
            event.ignore()
            return
        factor = 1.2 ** max(-4.0, min(4.0, delta / 120.0))
        if vertical_zoom:
            self.vertical_scale = max(0.5, min(300.0, self.vertical_scale * factor))
            self.set_model(vertical_scale=self.vertical_scale)
            self.scaleChanged.emit(self.horizontal_scale, self.vertical_scale)
            event.accept()
            return
        if horizontal_zoom or horizontal_gesture:
            # Start from the visible (possibly auto-expanded) metric scale.
            # Explicit zoom must not be clamped back to the readability floor.
            self.horizontal_scale = max(
                0.005, min(10000.0, self.effective_horizontal_scale() * factor)
            )
            self.horizontal_scale_manual = True
            self.set_model(horizontal_scale=self.horizontal_scale)
            self.scaleChanged.emit(self.horizontal_scale, self.vertical_scale)
            event.accept()
            return
        event.ignore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("white"))
        self._paint_hits.clear()
        self._outcrop_geometry.clear()
        self._capture_hits = True
        try:
            self.draw_section(painter, QRectF(self.rect()), fit=False)
        finally:
            self._capture_hits = False
        self._draw_outcrop_edit_preview(painter)

    def _remember_hit(self, rect, row, track="log", record=None):
        if self._capture_hits and row.get("key"):
            self._paint_hits.append((QRectF(rect), str(row["key"]), track, record))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.outcrop_edit_key:
                event.accept()
                return
            for box, key, track, record in reversed(self._paint_hits):
                if box.contains(event.position()):
                    if record is None or track == "units":
                        self.itemActivated.emit(key)
                    else:
                        self.recordActivated.emit(key, track.removesuffix("_label"), dict(record))
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def _legend_patterns(self, rows):
        if self.style != "stratapy" or not self.layout_options.get("legend", True):
            return []
        present = {
            tracks.lithology_pattern(unit)
            for row in rows for unit in row.get("units") or ()
        }
        return [category for category in tracks.PATTERN_LABELS if category in present]

    def _margins(self, rows, include_edit_lanes=True):
        left = 52.0 + max(48.0, self._slider_width() / 2 + 15.0)
        right = 190.0 + max(0.0, (self._slider_width() - 58.0) / 2)
        right += self._advanced_width(rows, include_edit_lanes)
        top = 80.0
        if self.layout_options.get("legend", True):
            legend_lines = len(self._legend_patterns(rows))
            if self._show_wellheads():
                legend_lines += 1
            if self.display["terrain"] and self._metric_terrain():
                legend_lines += 1
            if self.correlations and self.display.get("correlations", True):
                legend_lines += 2
            top = max(top, 33.0 + 16.0 * legend_lines)
        if self.layout_options.get("subtitle"):
            top = max(top, 95.0)
        bottom = 74.0 if self.layout_options.get("notes") else 55.0
        return left, right, top, bottom

    def draw_section(self, painter, rect, fit=True, show_heading=True):
        drawable = self._plot_rows()
        terrain = self._metric_terrain()
        painter.save()
        painter.setClipRect(rect)
        family = painter.font().family()
        painter.setFont(QFont(family, 8))
        if not drawable:
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont(family, 9))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter,
                self.plugin.t(
                    "Määra vähemalt ühe tulba korrelatsiooni nulltase."
                    if self.mode == "correlation"
                    else "Lisa läbilõikele vähemalt üks objekt."
                    if self.mode == "relative"
                    else "Lisa läbilõikele vähemalt üks koordinaatide ja "
                    "absoluutkõrgusega objekt."
                ),
            )
            painter.restore()
            return

        min_elevation, max_elevation = tracks.axis_range(drawable, terrain)
        min_station = min(row["_station"] for row in drawable)
        max_station = max(row["_station"] for row in drawable)
        station_span = max(1.0, max_station - min_station)
        left_margin, right_margin, top_margin, bottom_margin = self._margins(
            drawable, include_edit_lanes=not fit,
        )
        if fit:
            x_scale = max(
                0.001,
                (rect.width() - left_margin - right_margin) / station_span,
            )
            y_scale = max(
                0.001,
                (rect.height() - top_margin - bottom_margin)
                / max(1.0, max_elevation - min_elevation),
            )
        else:
            x_scale = self._plot_scale(drawable)
            y_scale = self.vertical_scale
        origin_x = rect.left() + left_margin
        origin_y = rect.top() + top_margin

        def x_for(station):
            return origin_x + (station - min_station) * x_scale

        def y_for(elevation):
            return origin_y + (max_elevation - elevation) * y_scale

        content_right = x_for(max_station) + right_margin
        content_bottom = y_for(min_elevation)
        axis_x = origin_x - max(48.0, self._slider_width() / 2 + 15.0)
        painter.setPen(QPen(QColor("#7c858d"), 1))
        painter.drawLine(
            round(axis_x), round(origin_y),
            round(axis_x), round(content_bottom),
        )
        step = self._nice_elevation_step(
            max_elevation - min_elevation, rect.height()
        )
        elevation = ceil(min_elevation / step) * step
        while elevation <= max_elevation + step / 100:
            y = y_for(elevation)
            painter.setPen(QPen(QColor(100, 110, 120, 45), 1))
            painter.drawLine(
                round(axis_x - 4), round(y),
                round(content_right), round(y),
            )
            painter.setPen(QColor("#4e565d"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(rect.left(), y - 9, axis_x - rect.left() - 6, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{elevation:g} m",
            )
            elevation += step

        if self.display["terrain"] and terrain:
            painter.setPen(QPen(QColor("#5c8c42"), 2.2))
            for a, b in zip(terrain, terrain[1:]):
                if number(a[1]) is None or number(b[1]) is None:
                    continue
                first, second = (x_for(a[0]), y_for(a[1])), (x_for(b[0]), y_for(b[1]))
                painter.drawLine(
                    round(first[0]), round(first[1]),
                    round(second[0]), round(second[1]),
                )

        if self._show_wellheads():
            painter.setPen(QPen(QColor("#725f46"), 1.4))
            surface = [
                (x_for(row["_station"]), y_for(row["_log_axis"].origin))
                for row in drawable
            ]
            for first, second in zip(surface, surface[1:]):
                painter.drawLine(
                    round(first[0]), round(first[1]),
                    round(second[0]), round(second[1]),
                )

        curve_scales = tracks.curve_scales(drawable)
        correlation_ends = {}
        for row in drawable:
            self._draw_item(
                painter, row, x_for(row["_station"]), y_for,
                curve_scales, correlation_ends, (origin_y, content_bottom),
            )
        if self.display.get("correlations", True):
            self._draw_correlations(painter, drawable, correlation_ends, y_for)

        mode_label = self.plugin.t({
            "line": "Kaardijoone järgi",
            "order": "Objektide järjekorra järgi",
            "equal": "Võrdsete vahedega",
            "relative": "Mõõdetud kõrgus / −sügavus lähtekohast (m)",
            "correlation": "Korrelatsiooni nulltase (m)",
        }.get(self.mode, self.mode))
        effective = self._plot_scale(drawable)
        if effective > self.horizontal_scale + 1e-9:
            mode_label += f" · H auto {effective:g} px/m"
        if show_heading:
            painter.setPen(QColor("#41484e"))
            painter.setFont(QFont(family, 11, QFont.Weight.Bold))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 5,
                    max(100.0, rect.width() - 205), 26,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                str(self.layout_options.get("title") or self.plugin.t("Koondläbilõige")),
            )
            painter.setPen(QColor("#687078"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 30,
                    max(100.0, rect.width() - 205), 22,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                mode_label,
            )
        else:
            painter.setPen(QColor("#687078"))
            painter.setFont(QFont(family, 8))
            painter.drawText(
                QRectF(
                    rect.left() + 5, rect.top() + 4,
                    rect.width() - 10, 20,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                mode_label,
            )
        subtitle = self.layout_options.get("subtitle")
        if subtitle:
            painter.setPen(QColor("#687078"))
            painter.drawText(
                QRectF(rect.left() + 5, rect.top() + (50 if show_heading else 24),
                       max(100.0, rect.width() - 205), 17),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(subtitle),
            )
        notes = self.layout_options.get("notes")
        if notes:
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(rect.left() + 5, content_bottom + 12, rect.width() - 10, 48),
                int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap), str(notes),
            )
        if not self.layout_options.get("legend", True):
            painter.restore()
            return
        legend_x = rect.right() - 190
        legend_y = rect.top() + 14
        painter.setFont(QFont(family, 7))
        if self._show_wellheads():
            painter.setPen(QPen(QColor("#725f46"), 1.4))
            painter.drawLine(
                round(legend_x), round(legend_y),
                round(legend_x + 22), round(legend_y),
            )
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(legend_x + 28, legend_y - 9, 150, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t("Andmete absoluutkõrgus"),
            )
            legend_y += 18
        if self.display["terrain"] and terrain:
            painter.setPen(QPen(QColor("#5c8c42"), 2.2))
            painter.drawLine(
                round(legend_x), round(legend_y),
                round(legend_x + 22), round(legend_y),
            )
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(legend_x + 28, legend_y - 9, 150, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t("DEM maapind"),
            )
            legend_y += 18
        for category in self._legend_patterns(drawable):
            patch = QRectF(legend_x, legend_y - 5, 22, 10)
            tracks.draw_lithology(painter, patch, category, QColor("#eceef0"))
            painter.setPen(QColor("#596169"))
            painter.drawText(
                QRectF(legend_x + 28, legend_y - 8, 158, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.plugin.t(tracks.PATTERN_LABELS[category]),
            )
            legend_y += 16
        if self.correlations and self.display.get("correlations", True):
            for inferred, caption in (
                (False, "Kinnitatud seos"), (True, "Oletuslik seos")
            ):
                tracks.draw_correlation(
                    painter, (legend_x, legend_y), (legend_x + 22, legend_y), inferred, ""
                )
                painter.setPen(QColor("#596169"))
                painter.drawText(
                    QRectF(legend_x + 28, legend_y - 8, 158, 16),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self.plugin.t(caption),
                )
                legend_y += 16
        painter.restore()

    def _draw_item(
        self, painter, row, center_x, y_for,
        curve_scales, correlation_ends, plot_bounds,
    ):
        axis = row["_log_axis"]
        elevation = axis.origin
        low, high = row["_measured_extent"]
        def y_at(measured):
            return y_for(axis.ordinate(measured))

        bar_width = self._slider_width()
        left = center_x - bar_width / 2
        right = left + bar_width
        y_start, y_end = sorted((y_at(low), y_at(high)))
        key = str(row.get("key") or "")
        editing_outcrop = self._capture_hits and self._outcrop_editing(row)
        def outcrop_hit(rect, track, record):
            self._remember_hit(rect, row, track, record)

        correlation_ends[(key, "units")] = (left, right)
        self._remember_hit(QRectF(left, y_start, bar_width, max(8, y_end - y_start)), row)
        painter.save()
        painter.setPen(QPen(QColor("#33383c"), 1.2))
        painter.drawLine(
            round(center_x), round(y_start), round(center_x), round(y_end),
        )

        units = row.get("units") or []
        for unit in units:
            top = _safe_number(unit.get("z_suht_ylemine"))
            bottom = _safe_number(unit.get("z_suht_alumine"), top)
            if bottom < top:
                continue
            y_top, y_bottom = sorted((y_at(top), y_at(bottom)))
            height = max(2.0, y_bottom - y_top)
            width = bar_width
            if self.style == "stratapy":
                fraction = tracks.grain_fraction(unit)
                if fraction is not None:
                    width *= fraction
            unit_rect = QRectF(left, y_top, width, height)
            if self.style == "stratapy":
                background = (
                    _stratigraphic_color(unit) if self.layout_options.get("pattern_colors", True)
                    else QColor("#f1f2f3")
                )
                tracks.draw_lithology(
                    painter, unit_rect, tracks.lithology_pattern(unit), background,
                )
            else:
                painter.fillRect(unit_rect, _stratigraphic_color(unit))
            if self.display["boundaries"]:
                painter.setPen(QPen(QColor("#555b60"), 0.8))
                if self.style == "stratapy":
                    from qgis.PyQt.QtCore import QLineF

                    painter.drawLine(QLineF(left, y_top, left, y_bottom))
                    painter.drawLine(QLineF(left + width, y_top, left + width, y_bottom))
                    # Explicit contact is at the first measured boundary;
                    # EGT's source field describes the lower boundary.
                    contact = unit.get("contact")
                    first_y, last_y = (
                        (y_at(top), y_at(bottom)) if contact else (y_at(bottom), y_at(top))
                    )
                    painter.drawLine(QLineF(left, last_y, left + width, last_y))
                    painter.setPen(QPen(QColor("#555b60"), 1.0, tracks.contact_style(
                        contact or unit.get("alumine_kontaktpind")
                    )))
                    painter.drawLine(QLineF(left, first_y, left + width, first_y))
                else:
                    painter.drawRect(unit_rect)
            if tracks.record_id(unit):
                correlation_ends[(key, "units", tracks.record_id(unit).casefold())] = (left, left + width)
            self._remember_hit(unit_rect, row, "units", unit)
            label_x = right + 4
            label = []
            index = _unit_index(unit)
            if row.get("role") == "observations":
                index = observation_index(unit, index)
            if self.display["indices"] and index:
                label.append(index)
            lithology = unit.get("litoloogia") or unit.get("litoloogia_orig")
            if self.display["lithology"] and lithology:
                label.append(str(lithology))
            if label and height >= 7:
                visible = [sorted((y_at(a), y_at(b))) for a, b in outcrop.uncovered_spans(
                    row, top, bottom, self.display, editing_outcrop,
                )]
                for label_top, label_bottom in sorted(visible):
                    available = label_bottom - label_top
                    if available < 7:
                        continue
                    painter.setPen(QColor("#42484d"))
                    painter.setFont(QFont(painter.font().family(), 7))
                    painter.drawText(
                        QRectF(label_x, label_top, 130, max(14, available)),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                        " · ".join(label),
                    )
                    break

        if self.display["core"]:
            painter.setPen(QPen(
                QColor("#2d2d2d"), 0.8, Qt.PenStyle.DashLine
            ))
            for box_track in ("core_boxes", "sarv_core_boxes"):
                for box in row.get(box_track) or ():
                    for attribute in ("z_suht_ylemine", "z_suht_alumine"):
                        box_depth = tracks.finite_number(box.get(attribute))
                        if box_depth is not None:
                            y = y_at(box_depth)
                            painter.drawLine(
                                round(left), round(y),
                                round(left + bar_width), round(y),
                            )
                            self._remember_hit(QRectF(left, y - 2, bar_width, 4), row, box_track, box)

        outcrop.draw_coverage(
            painter, row, left, bar_width, y_at, self.display, outcrop_hit,
            self.plugin.t, editing_outcrop,
        )
        track_left = left + bar_width + 1
        marker_tracks = (
            ("samples", "samples", QColor("#4f9b61")),
            ("analyses", "analyses", QColor("#8b4a9b")),
        )
        if row.get("role") != "observations":
            marker_tracks += (
                ("samples", "sarv_samples", QColor("#267d92")),
                ("analyses", "sarv_analyses", QColor("#c06b25")),
                ("specimens", "sarv_specimens", QColor("#b23a62")),
            )
        for toggle, marker_track, color in marker_tracks:
            if not self.display[toggle]:
                continue
            painter.setPen(QPen(color.darker(130), 0.8))
            painter.setBrush(color)
            for interval in row.get(marker_track) or ():
                top = _safe_number(interval.get("z_suht_ylemine"))
                bottom = _safe_number(
                    interval.get("z_suht_alumine"), top
                )
                y_top, y_bottom = sorted((y_at(top), y_at(bottom)))
                rect = QRectF(
                    track_left, y_top, 6, max(3, y_bottom - y_top)
                )
                painter.drawRect(rect)
                self._remember_hit(rect, row, marker_track, interval)
            track_left += 8
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.display["construction"]:
            construction_left = left - 13
            for part in row.get("veka_construction") or []:
                top = _safe_number(
                    part.get("z_suht_ylemine", part.get("alg"))
                )
                bottom = _safe_number(
                    part.get("z_suht_alumine", part.get("lopp")), top
                )
                y_top, y_bottom = sorted((y_at(top), y_at(bottom)))
                category = part.get("_category", "other")
                color = {
                    "filter": QColor("#237a9b"),
                    "casing": QColor("#3f474d"),
                    "open": QColor("#d07a22"),
                    "drill": QColor("#737b82"),
                }.get(category, QColor("#92989d"))
                style = (
                    Qt.PenStyle.DashLine
                    if category == "open" else Qt.PenStyle.SolidLine
                )
                painter.setPen(QPen(color, 2, style))
                painter.drawLine(
                    round(construction_left), round(y_top),
                    round(construction_left), round(y_bottom),
                )

        if self.display["water"] and row.get("static_water"):
            water_depth = number(row["static_water"].get("st_veetase"))
            if water_depth is not None:
                y = y_at(water_depth)
                painter.setPen(QPen(
                    QColor("#1677b8"), 1.4, Qt.PenStyle.DashDotLine
                ))
                painter.drawLine(
                    round(left - 7), round(y),
                    round(track_left + 6), round(y),
                )

        surface_y = y_for(elevation)
        station = row.get("_station")
        terrain_height = self._terrain_at(station) if self._metric_terrain() else None
        delta_color = QColor("#626b72")
        if terrain_height is not None:
            delta = elevation - terrain_height
            delta_color = (
                QColor("#b3261e") if abs(delta) >= 3.0
                else QColor("#a06400") if abs(delta) >= 1.0
                else QColor("#527342")
            )
            terrain_y = y_for(terrain_height)
            comparison_x = left - 7
            painter.setPen(QPen(
                delta_color, 1.1, Qt.PenStyle.DashLine
            ))
            painter.drawLine(
                round(comparison_x), round(surface_y),
                round(comparison_x), round(terrain_y),
            )
            painter.drawLine(
                round(comparison_x - 3), round(surface_y),
                round(comparison_x + 3), round(surface_y),
            )
            painter.drawLine(
                round(comparison_x - 3), round(terrain_y),
                round(comparison_x + 3), round(terrain_y),
            )
        painter.setPen(QPen(QColor("#22272b"), 1))
        painter.setBrush(QColor("#22272b"))
        painter.drawEllipse(QRectF(center_x - 3, surface_y - 3, 6, 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        name = str(row.get("name") or row.get("id") or "")
        if len(name) > 22:
            name = name[:20] + "…"
        offset = row.get("_offset")
        subtitle = (
            f"{station:g} m"
            if self.mode in {"line", "order"} and station is not None
            else str(row.get("source") or "")
        )
        if offset is not None and self.mode == "line":
            subtitle += f" · ±{offset:g} m"
        if terrain_height is not None:
            subtitle += f" · ΔDEM {elevation - terrain_height:+.1f} m"
        painter.setPen(QColor("#293038"))
        painter.setFont(QFont(painter.font().family(), 8, QFont.Weight.Bold))
        heading = QRectF(center_x - 72, y_start - 47, 144, 18)
        painter.drawText(
            heading,
            Qt.AlignmentFlag.AlignCenter, name,
        )
        self._remember_hit(heading, row)
        painter.setFont(QFont(painter.font().family(), 7))
        painter.setPen(delta_color)
        painter.drawText(
            QRectF(center_x - 82, y_start - 30, 164, 18),
            Qt.AlignmentFlag.AlignCenter, subtitle,
        )
        if self.style == "stratapy" and any(tracks.grain_fraction(unit) is not None for unit in units):
            tracks.draw_grain_scale(
                painter, left, y_end + 4, bar_width, self.plugin.t("Terasuurus (mm)"),
            )
        track_x = right + 141
        for track, values, width in self._advanced_track_specs(row):
            correlation_ends[(str(row.get("key") or ""), track)] = (track_x, track_x + width)
            if track == "isotopes":
                group_key, points = values
                def isotope_hit(rect, record):
                    self._remember_hit(rect, row, "isotopes", record)
                    identifier = tracks.record_id(record)
                    if identifier:
                        correlation_ends[(str(row.get("key") or ""), "isotopes", identifier.casefold())] = (
                            rect.center().x(), rect.center().x()
                        )

                lower, upper, color = curve_scales[group_key]
                tracks.draw_isotope_track(
                    painter, track_x, width, values, y_at,
                    y_start - 29, (y_start, y_end), QColor(color),
                    self.layout_options.get("isotope_max_gap"), isotope_hit, (lower, upper),
                )
            elif track == "biofinds":
                def biofind_hit(rect, record, label):
                    self._remember_hit(rect, row, "biofinds_label" if label else "biofinds", record)
                    identifier = tracks.record_id(record)
                    if identifier and not label:
                        x = rect.center().x()
                        correlation_ends[(str(row.get("key") or ""), track, identifier.casefold())] = (x, x)

                tracks.draw_biofind_track(
                    painter, track_x, width, values, y_at, y_start - 16,
                    self.plugin.t(tracks.TRACK_TITLES[track]), biofind_hit,
                )
            else:
                scheme, records = values
                color = QColor("#c9d9f1" if track == "biozones" else "#e6d7ba")
                painter.setPen(QColor("#596169"))
                title = self.plugin.t(tracks.TRACK_TITLES[track])
                if scheme:
                    title += " · " + scheme
                painter.drawText(
                    QRectF(track_x, y_start - 16, width, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(width)),
                )
                def band_hit(rect, record):
                    self._remember_hit(rect, row, track, record)
                    identifier = tracks.record_id(record)
                    if identifier:
                        correlation_ends[(key, track, identifier.casefold())] = (rect.left(), rect.right())
                tracks.draw_interval_band(
                    painter, track_x, width, records, y_at, color, band_hit,
                )
            track_x += width + 7
        wall = outcrop.draw_outcrop_lanes(
            painter, row, track_x, y_at, y_start, plot_bounds, self.display,
            outcrop_hit, self.plugin.t, editing_outcrop,
        )
        if self._capture_hits and outcrop.is_outcrop(row):
            plots = getattr(self, "_outcrop_geometry", None)
            if plots is not None:
                plots[key] = {
                    "axis": axis, "y_at": y_at,
                    "bar_rect": QRectF(left, plot_bounds[0] if editing_outcrop else y_start,
                                       bar_width, max(8, plot_bounds[1] - plot_bounds[0])
                                       if editing_outcrop else max(8, y_end - y_start)),
                    "wall": wall,
                }
        painter.restore()

    def _draw_correlations(self, painter, rows, ends, y_for):
        by_key = {str(row.get("key") or ""): row for row in rows}
        painter.save()
        for item in self.correlations:
            if not isinstance(item, dict):
                continue
            ends_for_item = []
            for side in ("left", "right"):
                ref = item.get(side)
                if not isinstance(ref, dict):
                    break
                key = str(ref.get("item_key") or "")
                row = by_key.get(key)
                track = ref.get("track")
                bounds = ends.get(
                    (key, track, str(ref.get("id") or "").casefold()), ends.get((key, track))
                )
                if row is None or bounds is None:
                    break
                position = tracks.anchor_position(row, ref)
                if position is None:
                    break
                ends_for_item.append((
                    bounds, y_for(row["_log_axis"].ordinate(position)),
                ))
            if len(ends_for_item) == 2 and item["left"].get("item_key") != item["right"].get("item_key"):
                first, second = sorted(ends_for_item, key=lambda pair: sum(pair[0]))
                tracks.draw_correlation(
                    painter, (first[0][1], first[1]), (second[0][0], second[1]),
                    bool(item.get("inferred")), item.get("label") or "",
                )
        painter.restore()

    def _terrain_at(self, station):
        if station is None or not self.terrain:
            return None
        samples = sorted(self.terrain)
        for position, height in samples:
            if abs(position - station) < 1e-6:
                return number(height)
        for (a, za), (b, zb) in zip(samples, samples[1:]):
            if a < station < b:
                if number(za) is None or number(zb) is None:
                    return None
                return za + (zb - za) * (station - a) / (b - a)
        return None

    @staticmethod
    def _nice_elevation_step(span, height):
        target = max(2.0, span / max(4, int(height / 90)))
        choices = (1, 2, 5, 10, 20, 25, 50, 100, 200, 500)
        return next((value for value in choices if value >= target), choices[-1])


class CrossSectionScrollArea(QScrollArea):
    """Route zoom gestures over viewport margins as well as the drawing."""

    def wheelEvent(self, event):
        self.widget().wheelEvent(event)
        if not event.isAccepted():
            super().wheelEvent(event)


class CrossSectionWidget(QWidget, SectionWorkspaceMixin, OutcropDrawingWidgetMixin):
    """Manage the current project cross-section and its export."""

    modelChanged = pyqtSignal(int)

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.items = []
        self.line = []
        self.terrain = []
        # Building controls emits signals; never overwrite saved project state
        # before it has been read.
        self._updating = True
        self._table_item_indices = []
        self._init_section_workspace()
        self._init_outcrop_drawing()
        self._build_ui()
        self.reload_rasters()
        self.load_project_state()
        self._updating = False
        project = QgsProject.instance()
        project.readProject.connect(self.load_project_state)
        project.cleared.connect(self.load_project_state)

    def _build_ui(self):
        t = self.plugin.t
        outer = QVBoxLayout(self)
        self._workspace_controls(outer)
        toolbar = QHBoxLayout()
        self.name = QLineEdit(t("Koondläbilõige"))
        self.name.editingFinished.connect(self.save_project_state)
        toolbar.addWidget(QLabel(t("Nimi")))
        toolbar.addWidget(self.name, 1)
        self.mode = QComboBox()
        for label, value in (
            ("Kaardijoone järgi", "line"),
            ("Objektide järjekorra järgi", "order"),
            ("Võrdsete vahedega", "equal"),
            ("Suhteline kõrgus / sügavus", "relative"),
            ("Korrelatsioon", "correlation"),
        ):
            self.mode.addItem(t(label), value)
        self.mode.currentIndexChanged.connect(self._model_changed)
        toolbar.addWidget(self.mode)
        draw_line = QPushButton(t("Joonista kaardil"))
        draw_line.clicked.connect(lambda: self._require_closed_outcrop_edit()
                                  and self.plugin.start_cross_section_line())
        toolbar.addWidget(draw_line)
        clear = QPushButton(t("Uus / tühjenda"))
        clear.clicked.connect(self.clear)
        toolbar.addWidget(clear)
        outer.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        self.canvas = CrossSectionCanvas(self.plugin)
        self.canvas.scaleChanged.connect(self._canvas_scale_changed)
        self.canvas.itemActivated.connect(self._open_section_source)
        self.canvas.recordActivated.connect(self._show_section_record)
        self.canvas.drawingAction.connect(self._receive_drawing_action)
        self.canvas.drawingFeedback.connect(self._notify_outcrop_edit)
        canvas_scroll = CrossSectionScrollArea()
        canvas_scroll.setWidgetResizable(False)
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setToolTip(t(
            "Ctrl/Command + kerimine: vertikaalne suum. Shift + kerimine "
            "või horisontaalne kerimine: horisontaalne suum."
        ))
        splitter.addWidget(canvas_scroll)

        objects_panel = QWidget()
        self.objects_panel = objects_panel
        objects_layout = QVBoxLayout(objects_panel)
        objects_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels((
            t("Kuva"), t("Allikas"), t("Nimi"), t("Absoluutkõrgus"),
            t("Sügavus"), t("Pikett"), t("Kõrvalekalle"),
        ))
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(260)
        self.table.itemChanged.connect(self._table_changed)
        objects_layout.addWidget(self.table)
        row_actions = QHBoxLayout()
        for label, callback in (
            ("↑", lambda: self.move_selected(-1)),
            ("↓", lambda: self.move_selected(1)),
            ("Pööra", self.reverse),
            ("Määra kõrgus", self.set_selected_elevation),
            ("Eemalda", self.remove_selected),
        ):
            button = QPushButton(t(label))
            button.clicked.connect(callback)
            row_actions.addWidget(button)
        self._build_outcrop_controls(outer, row_actions)
        objects_layout.addLayout(row_actions)

        options = QWidget()
        options_layout = QVBoxLayout(options)
        self._section_style_controls(options_layout)
        display_group = QGroupBox(t("Kuvamine"))
        display_layout = QVBoxLayout(display_group)
        self.display_checks = {}
        for key, label in (
            ("indices", "Indeksid"),
            ("lithology", "Litoloogia"),
            ("boundaries", "Piiride sügavused"),
            ("core", "Puursüdamiku kastid"),
            ("samples", "Proovid"),
            ("analyses", "Analüüsid"),
            ("specimens", "Eksemplarid"),
            ("construction", "Konstruktsioon"),
            ("water", "Staatiline veetase"),
            ("wellheads", "Ühenda suudmed"),
            ("terrain", "DEM maapinnaprofiil"),
            ("isotopes", "Isotoobid"),
            ("biofinds", "Biotsoonide leiupunktid"),
            ("biozones", "Tõlgendatud biotsoonide ulatus"),
            ("stages", "Lademed"),
            ("correlations", "Korrelatsioonid"),
            ("outcrop_observations", "Paljandi vaatlused"),
            ("outcrop_coverage", "Varjatud vahemikud"),
            ("outcrop_shapes", "Seinaprofiil"),
        ):
            checkbox = QCheckBox(t(label))
            checkbox.setChecked(key != "biozones")
            checkbox.toggled.connect(self._display_changed)
            self.display_checks[key] = checkbox
            display_layout.addWidget(checkbox)
        options_layout.addWidget(display_group)

        scale_group = QGroupBox(t("Mõõtkava"))
        scale_form = QFormLayout(scale_group)
        self.horizontal_scale = QDoubleSpinBox()
        self.horizontal_scale.setRange(0.005, 10000.0)
        self.horizontal_scale.setDecimals(6)
        self.horizontal_scale.setSingleStep(0.02)
        self.horizontal_scale.setValue(0.12)
        self.horizontal_scale.valueChanged.connect(self._horizontal_scale_changed)
        self.vertical_scale = QDoubleSpinBox()
        self.vertical_scale.setRange(0.5, 300.0)
        self.vertical_scale.setSingleStep(0.5)
        self.vertical_scale.setValue(4.0)
        self.vertical_scale.valueChanged.connect(self._model_changed)
        scale_form.addRow(t("Horisontaalne px/m"), self.horizontal_scale)
        scale_form.addRow(t("Vertikaalne px/m"), self.vertical_scale)
        options_layout.addWidget(scale_group)

        dem_group = QGroupBox(t("DEM"))
        dem_form = QFormLayout(dem_group)
        self.dem_layer = QComboBox()
        self.dem_band = QSpinBox()
        self.dem_band.setRange(1, 99)
        self.dem_band.setValue(1)
        self.dem_band.valueChanged.connect(self.sample_dem)
        refresh_dem = QPushButton(t("Värskenda rasterkihte"))
        refresh_dem.clicked.connect(self.reload_rasters)
        sample_dem = QPushButton(t("Loe DEM-profiil"))
        sample_dem.clicked.connect(self.sample_dem)
        dem_form.addRow(t("Rasterkiht"), self.dem_layer)
        dem_form.addRow(t("Kõrguskanal"), self.dem_band)
        dem_form.addRow(refresh_dem)
        dem_form.addRow(sample_dem)
        options_layout.addWidget(dem_group)

        map_group = QGroupBox(t("Kaart ja eksport"))
        map_layout = QVBoxLayout(map_group)
        self.show_map_line = QCheckBox(t("Kuva läbilõikejoon kaardil"))
        self.show_map_line.setChecked(True)
        self.show_map_line.toggled.connect(self._map_line_changed)
        self.show_map_line.toggled.connect(self.save_project_state)
        self.include_overview = QCheckBox(t("Lisa ülevaatekaart"))
        self.include_overview.setChecked(True)
        self.include_overview.toggled.connect(self.save_project_state)
        export_svg = QPushButton(t("Ekspordi SVG"))
        export_pdf = QPushButton(t("Ekspordi PDF"))
        export_svg.clicked.connect(lambda: self.export("svg"))
        export_pdf.clicked.connect(lambda: self.export("pdf"))
        map_layout.addWidget(self.show_map_line)
        map_layout.addWidget(self.include_overview)
        map_layout.addWidget(export_svg)
        map_layout.addWidget(export_pdf)
        options_layout.addWidget(map_group)
        options_layout.addStretch(1)
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_scroll.setMinimumWidth(250)
        options_scroll.setWidget(options)
        splitter.addWidget(options_scroll)
        splitter.setSizes((1000, 280))

        self.objects_toggle = QToolButton()
        self.objects_toggle.setText(t("Läbilõike objektid"))
        self.objects_toggle.setCheckable(True)
        self.objects_toggle.setChecked(True)
        self.objects_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.objects_toggle.toggled.connect(self._set_objects_expanded)
        outer.addWidget(self.objects_toggle)
        outer.addWidget(objects_panel)
        self._set_objects_expanded(True)

        self.status = QLabel()
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

    def _set_objects_expanded(self, expanded):
        """Show the chainage-ordered object list below the drawing."""
        self.objects_panel.setVisible(bool(expanded))
        self.objects_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        if not self._updating:
            self.save_project_state()

    def _item_index_for_table_row(self, row):
        if 0 <= row < len(self._table_item_indices):
            return self._table_item_indices[row]
        return -1

    def _select_item_key(self, key):
        target = str(key or "")
        for row, item_index in enumerate(self._table_item_indices):
            if self.item_key(self.items[item_index]) == target:
                self.table.selectRow(row)
                return

    def _canvas_scale_changed(self, horizontal, vertical):
        """Keep wheel zoom, controls and persisted project state in sync."""
        self._updating = True
        self.horizontal_scale.setValue(float(horizontal))
        self.vertical_scale.setValue(float(vertical))
        self._updating = False
        self.save_project_state()

    def _horizontal_scale_changed(self):
        if self._updating:
            return
        self.canvas.horizontal_scale_manual = True
        self._model_changed()

    def item_key(self, snapshot):
        return str(snapshot.get("key") or "")

    def contains(self, key):
        return any(self.item_key(item) == str(key) for item in self.items)

    def add_snapshot(self, snapshot):
        if not snapshot or not snapshot.get("key"):
            return
        if self.workspace and not public_workspace_items([snapshot]):
            self.workspace_status.setText(self.plugin.t("Toetatud allikad: EGT, SARV ja VEKA."))
            return
        snapshot = section_record_ids(self._json_safe(snapshot))
        if snapshot.get("role") != "local_section" and not snapshot.get("source_ref"):
            ref = section_source_ref(snapshot)
            if ref:
                snapshot["source_ref"] = ref
        key = self.item_key(snapshot)
        for index, item in enumerate(self.items):
            if self.item_key(item) == key:
                enabled = item.get("enabled", True)
                replacement = {**snapshot, "enabled": enabled}
                if not replacement.get("source_ref") and item.get("source_ref"):
                    replacement["source_ref"] = item["source_ref"]
                if item.get("elevation_override"):
                    replacement["elevation"] = item.get("elevation")
                    replacement["elevation_override"] = True
                    replacement["elevation_source"] = "manual"
                self.items[index] = replacement
                break
        else:
            snapshot["enabled"] = True
            self.items.append(snapshot)
        self.refresh()
        self.save_project_state()

    def update_snapshot(self, key, updates, *, serial=None):
        """Merge asynchronously loaded detail data into one section item.

        Automatic line selection creates lightweight snapshots first so the
        section can be shown immediately.  Profile and construction requests
        may finish later; merging here keeps any manual elevation override and
        the user's enabled state intact while refreshing the drawing.
        """
        target = str(key or "")
        if (
            not target or not isinstance(updates, dict)
            or (serial is not None and serial != self._workspace_serial)
        ):
            return False
        for index, item in enumerate(self.items):
            if self.item_key(item) != target:
                continue
            enabled = item.get("enabled", True)
            replacement = {**item, **self._json_safe(updates)}
            replacement["enabled"] = enabled
            if item.get("elevation_override"):
                replacement["elevation"] = item.get("elevation")
                replacement["elevation_override"] = True
                replacement["elevation_source"] = "manual"
            self.items[index] = section_record_ids(replacement)
            self.refresh()
            self.save_project_state()
            return True
        return False

    def backfill_egt_elevations(self):
        """Recover elevations missing from snapshots made before PointZ support."""
        missing = [
            item for item in self.items
            if item.get("role") in {"boreholes", "observations"}
            and number(item.get("elevation")) is None
            and number(item.get("x")) is not None
            and number(item.get("y")) is not None
        ]
        if not missing:
            return 0
        recovered = 0
        project = QgsProject.instance()
        for item in missing:
            expected_id = str(item.get("id") or "").strip().casefold()
            for layer in self.plugin._role_layers(item["role"]):
                try:
                    point = QgsCoordinateTransform(
                        METRIC_CRS, layer.crs(), project
                    ).transform(QgsPointXY(
                        float(item["x"]), float(item["y"])
                    ))
                except (QgsCsException, TypeError, ValueError):
                    continue
                radius = 0.00001 if layer.crs().isGeographic() else 1.0
                request = QgsFeatureRequest().setFilterRect(QgsRectangle(
                    point.x() - radius, point.y() - radius,
                    point.x() + radius, point.y() + radius,
                ))
                candidates = list(layer.getFeatures(request))
                if not candidates:
                    continue
                feature = next((
                    candidate for candidate in candidates
                    if expected_id and expected_id == str(
                        candidate.attribute("esri_globalid")
                        if layer.fields().indexOf("esri_globalid") >= 0
                        else candidate.attribute("globalid")
                        if layer.fields().indexOf("globalid") >= 0
                        else ""
                    ).strip().casefold()
                ), candidates[0])
                attributes = self.plugin._detail_attributes_with_location(
                    {}, layer, feature
                )
                elevation = number(attributes.get("z_abs"))
                if elevation is None:
                    continue
                item["elevation"] = elevation
                item["elevation_source"] = "WFS PointZ"
                recovered += 1
                break
        if recovered:
            self.refresh()
            self.save_project_state()
        return recovered

    def remove_key(self, key):
        if self._outcrop_draft and key == self._outcrop_draft["key"]:
            self._require_closed_outcrop_edit()
            return
        self.items = [
            item for item in self.items if self.item_key(item) != str(key)
        ]
        self.refresh()
        self.save_project_state()

    def clear(self):
        if not self._require_closed_outcrop_edit():
            return
        if self.items and QMessageBox.question(
            self, self.plugin.t("Uus / tühjenda"),
            self.plugin.t("Kas eemaldada kõik koondläbilõike objektid?"),
        ) != QMessageBox.StandardButton.Yes:
            return
        self.items = []
        self.line = []
        self.terrain = []
        self.section_correlations = []
        self.section_alignments = {}
        self._workspace_serial = uuid4()
        self.refresh()
        self.save_project_state()

    def move_selected(self, direction):
        row = self.table.currentRow()
        item_index = self._item_index_for_table_row(row)
        target = item_index + direction
        if item_index < 0 or not 0 <= target < len(self.items):
            return
        key = self.item_key(self.items[item_index])
        self.items[item_index], self.items[target] = (
            self.items[target], self.items[item_index]
        )
        self.refresh()
        self._select_item_key(key)
        self.save_project_state()

    def reverse(self):
        self.items.reverse()
        self.line.reverse()
        self.refresh()
        self.save_project_state()

    def remove_selected(self):
        if not self._require_closed_outcrop_edit():
            return
        row = self.table.currentRow()
        item_index = self._item_index_for_table_row(row)
        if 0 <= item_index < len(self.items):
            self.items.pop(item_index)
            self.refresh()
            self.save_project_state()

    def set_selected_elevation(self):
        if not self._require_closed_outcrop_edit():
            return
        row = self.table.currentRow()
        item_index = self._item_index_for_table_row(row)
        if not 0 <= item_index < len(self.items):
            return
        current = number(self.items[item_index].get("elevation")) or 0.0
        value, accepted = QInputDialog.getDouble(
            self, self.plugin.t("Määra kõrgus"),
            self.plugin.t("Absoluutkõrgus"), current,
            -500.0, 10000.0, 2,
        )
        if accepted:
            self.items[item_index]["elevation"] = value
            self.items[item_index]["elevation_override"] = True
            self.refresh()
            self.save_project_state()

    def set_line(self, points):
        self.line = [
            [float(point[0]), float(point[1])] for point in points
        ]
        self.mode.setCurrentIndex(self.mode.findData("line"))
        self.terrain = []
        self.refresh()
        self.sample_dem()
        self.save_project_state()

    def add_nearby_local_logs(self, points, radius):
        if not self.workspace or len(points) < 2:
            return 0
        from qgis.core import QgsGeometry

        line = QgsGeometry.fromPolylineXY([QgsPointXY(float(x), float(y)) for x, y in points])
        added = 0
        try:
            for entry in self.workspace.list_logs():
                if self.contains(f"local:{entry['id']}"):
                    continue
                row = self.workspace.load_log(entry["id"])
                trace = row.get("trace") or []
                x, y = number(row.get("x")), number(row.get("y"))
                if len(trace) >= 2:
                    geometry = QgsGeometry.fromPolylineXY([QgsPointXY(float(a), float(b)) for a, b in trace])
                elif x is not None and y is not None:
                    geometry = QgsGeometry.fromPointXY(QgsPointXY(x, y))
                else:
                    continue
                if 0 <= line.distance(geometry) <= radius:
                    self.add_snapshot(row)
                    added += 1
        except (SectionWorkspaceError, TypeError, ValueError) as error:
            self._workspace_error(error)
        return added

    def effective_line(self):
        if self.mode.currentData() == "line" and len(self.line) >= 2:
            return list(self.line)
        return line_from_items(self.items)

    def refresh(self):
        # Include disabled objects in the list while calculating the same
        # chainage order that the canvas uses for enabled objects.
        positioned = section_positions(
            [dict(item, enabled=True) for item in self.items],
            self.mode.currentData(), self.line,
        )
        by_key = {self.item_key(row): row for row in positioned}
        original_by_key = {
            self.item_key(item): index
            for index, item in enumerate(self.items)
        }
        ordered_indices = [
            original_by_key[self.item_key(row)]
            for row in positioned
            if self.item_key(row) in original_by_key
        ]
        # Defensive fallback for snapshots without a usable key.
        ordered_indices.extend(
            index for index in range(len(self.items))
            if index not in ordered_indices
        )
        was_updating = self._updating
        self._updating = True
        self.table.setRowCount(len(self.items))
        self._table_item_indices = ordered_indices
        for row_index, item_index in enumerate(ordered_indices):
            item = self.items[item_index]
            display = by_key.get(self.item_key(item), item)
            values = (
                "", item.get("source"), item.get("name"),
                item.get("elevation"), item.get("depth"),
                display.get("_station"), display.get("_offset"),
            )
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(
                    "" if value is None else
                    f"{value:g}" if isinstance(value, float) else str(value)
                )
                if column == 0:
                    table_item.setFlags(
                        table_item.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    table_item.setCheckState(
                        Qt.CheckState.Checked
                        if item.get("enabled", True)
                        else Qt.CheckState.Unchecked
                    )
                else:
                    table_item.setFlags(
                        table_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                    )
                self.table.setItem(row_index, column, table_item)
        self._updating = was_updating
        self.table.resizeColumnsToContents()
        self.canvas.set_model(
            items=self._current_drawing_items(),
            mode=self.mode.currentData(),
            line=self.line,
            terrain=self.terrain,
            horizontal_scale=self.horizontal_scale.value(),
            vertical_scale=self.vertical_scale.value(),
            display={
                key: checkbox.isChecked()
                for key, checkbox in self.display_checks.items()
            },
            style=self.section_style.currentData(),
            layout=self.section_layout,
            correlations=self.section_correlations,
            alignments=self.section_alignments,
        )
        missing_elevation = sum(
            number(item.get("elevation")) is None for item in self.items
        )
        self.status.setText(
            f"{len(self.items)} {self.plugin.t('objekti')}"
            + (
                f" · {missing_elevation} "
                + self.plugin.t("objektil puudub absoluutkõrgus")
                if missing_elevation else ""
            )
        )
        self.modelChanged.emit(len(self.items))
        self._map_line_changed()

    def _table_changed(self, item):
        if self._updating or item.column() != 0:
            return
        row = item.row()
        item_index = self._item_index_for_table_row(row)
        if 0 <= item_index < len(self.items):
            if self._outcrop_draft and self.items[item_index]["key"] == self._outcrop_draft["key"]:
                self._require_closed_outcrop_edit()
                self.refresh()
                return
            self.items[item_index]["enabled"] = (
                item.checkState() == Qt.CheckState.Checked
            )
            self.refresh()
            self.save_project_state()

    def _model_changed(self):
        if self._updating:
            return
        if self.mode.currentData() != "line":
            self.terrain = []
        self.refresh()
        if self.mode.currentData() in {"line", "order"}:
            self.sample_dem()
        self.save_project_state()

    def _display_changed(self):
        if self._updating:
            return
        self.refresh()
        self.save_project_state()

    def _map_line_changed(self):
        if self._updating:
            return
        self.plugin.update_cross_section_map_line(
            self.effective_line(), self.show_map_line.isChecked()
        )
        if hasattr(self.plugin, "update_local_section_outcrops"):
            self.plugin.update_local_section_outcrops(
                self.items if self.show_map_line.isChecked() else [],
            )

    def reload_rasters(self):
        previous = self.dem_layer.currentData() if self.dem_layer.count() else ""
        self.dem_layer.clear()
        self.dem_layer.addItem(self.plugin.t("DEM puudub"), "")
        for layer in QgsProject.instance().mapLayers().values():
            if (
                isinstance(layer, QgsRasterLayer)
                and layer.providerType().casefold() != "wms"
            ):
                self.dem_layer.addItem(layer.name(), layer.id())
        index = self.dem_layer.findData(previous)
        self.dem_layer.setCurrentIndex(max(0, index))

    def sample_dem(self):
        if self._updating:
            return
        layer = QgsProject.instance().mapLayer(self.dem_layer.currentData())
        line = self.effective_line()
        if not isinstance(layer, QgsRasterLayer) or len(line) < 2:
            self.terrain = []
            self.refresh()
            return
        length = polyline_length(line)
        if length <= 0:
            return
        count = max(2, min(800, round(length / 10) + 1))
        step = length / (count - 1)
        transform = QgsCoordinateTransform(
            METRIC_CRS, layer.crs(), QgsProject.instance()
        )
        terrain = []
        provider = layer.dataProvider()
        band = min(max(1, self.dem_band.value()), layer.bandCount())
        for index in range(count):
            station = index * step
            point = point_at_station(line, station)
            if not point:
                continue
            try:
                raster_point = transform.transform(
                    QgsPointXY(point[0], point[1])
                )
                value, valid = provider.sample(raster_point, band)
            except Exception:
                valid = False
                value = None
            terrain.append((station, float(value) if valid and number(value) is not None else None))
        self.terrain = terrain
        self.refresh()
        self.save_project_state()

    def _section_state(self):
        return self._json_safe({
            "version": 2,
            "name": self.name.text(),
            "mode": self.mode.currentData(),
            "line": self.line,
            "items": self.items,
            "terrain": self.terrain,
            "dem_layer_name": self.dem_layer.currentText(),
            "dem_band": self.dem_band.value(),
            "horizontal_scale": self.horizontal_scale.value(),
            "horizontal_scale_manual": self.canvas.horizontal_scale_manual,
            "vertical_scale": self.vertical_scale.value(),
            "display": {
                key: checkbox.isChecked()
                for key, checkbox in self.display_checks.items()
            },
            "show_map_line": self.show_map_line.isChecked(),
            "include_overview": self.include_overview.isChecked(),
            "objects_expanded": self.objects_toggle.isChecked(),
            "style": self.section_style.currentData(),
            "layout": self.section_layout,
            "correlations": self.section_correlations,
            "alignments": self.section_alignments,
        })

    def save_project_state(self):
        if self._updating:
            return False
        if self.workspace_unavailable:
            self.workspace_status.setText(self.plugin.t(
                "Töökaust pole kättesaadav. Ava olemasolev töökaust või taasta varukoopiast."
            ))
            return False
        state = self._section_state()
        if self.workspace:
            try:
                self.workspace.save_section(state, self.workspace_section_id)
            except SectionWorkspaceError as error:
                self._workspace_error(error)
                return False
            self._workspace_link_to_project()
            index = self.section_selector.findData(self.workspace_section_id)
            if index >= 0:
                self.section_selector.setItemText(index, state["name"])
            self._schedule_workspace_backup()
            return True
        QgsProject.instance().writeEntry(
            STATE_SCOPE,
            STATE_KEY,
            json.dumps(state, ensure_ascii=False),
        )
        return True

    def load_project_state(self, *_):
        if self._outcrop_draft:
            self._end_outcrop_edit(refresh=False)
        self._workspace_serial = uuid4()
        self._workspace_backup_timer.stop()
        self.workspace = None
        self.workspace_section_id = ""
        self.workspace_unavailable = False
        project = QgsProject.instance()
        payload, _ = project.readEntry(STATE_SCOPE, STATE_KEY, "")
        pointer, _ = project.readEntry(STATE_SCOPE, WORKSPACE_ENTRY, "")
        state = {}
        try:
            if pointer:
                link = json.loads(pointer)
                folder = project.pathResolver().readPath(link["folder"])
                workspace = SectionWorkspace.open(folder)
                state = workspace.load_section(link["section"])
                self.workspace = workspace
                self.workspace_section_id = link["section"]
            elif payload:
                state = json.loads(payload)
        except (TypeError, ValueError, KeyError, SectionWorkspaceError, OSError):
            self.workspace_unavailable = bool(pointer)
        self._apply_section_state(state if isinstance(state, dict) else {})
        self._update_workspace_controls()
        notify = getattr(self.plugin, 'local_workspace_changed', None)
        if notify:
            notify()

    def _apply_section_state(self, state):
        self._updating = True
        self.name.setText(state.get("name") or self.plugin.t("Koondläbilõige"))
        self.items = [section_record_ids(row) for row in state.get("items") or []
                      if isinstance(row, dict)]
        self.line = list(state.get("line") or [])
        self.terrain = [
            tuple(pair) for pair in (state.get("terrain") or [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        index = self.mode.findData(state.get("mode", "line"))
        self.mode.setCurrentIndex(max(0, index))
        self.horizontal_scale.setValue(
            float(state.get("horizontal_scale", 0.12))
        )
        self.canvas.horizontal_scale_manual = bool(
            state.get("horizontal_scale_manual", False)
        )
        self.vertical_scale.setValue(
            float(state.get("vertical_scale", 4.0))
        )
        for key, checkbox in self.display_checks.items():
            choices = state.get("display") or {}
            value = False if key == "biozones" and state.get("version", 1) == 1 else choices.get(key, key != "biozones")
            checkbox.setChecked(bool(value))
        self.show_map_line.setChecked(bool(state.get("show_map_line", True)))
        self.include_overview.setChecked(bool(
            state.get("include_overview", True)
        ))
        self.objects_toggle.setChecked(bool(
            state.get("objects_expanded", True)
        ))
        self._set_objects_expanded(self.objects_toggle.isChecked())
        self.dem_band.setValue(int(state.get("dem_band", 1)))
        dem_name = state.get("dem_layer_name")
        self.dem_layer.setCurrentIndex(max(0, self.dem_layer.findText(dem_name or "")))
        self.section_style.setCurrentIndex(max(0, self.section_style.findData(state.get("style"))))
        self.section_layout = dict(state.get("layout") or {})
        self.section_correlations = list(state.get("correlations") or [])
        self.section_alignments = dict(state.get("alignments") or {})
        self._updating = False
        self.refresh()

    def export(self, kind):
        if not self._require_closed_outcrop_edit():
            return
        if not self.items:
            QMessageBox.information(
                self, self.plugin.t("Eksport"),
                self.plugin.t("Koondläbilõikele pole objekte lisatud."),
            )
            return
        extension = f".{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, self.plugin.t("Eksport"),
            f"{self.name.text() or 'koondlabiloige'}{extension}",
            (
                "Scalable Vector Graphics (*.svg)"
                if kind == "svg" else "PDF (*.pdf)"
            ),
        )
        if not path:
            return
        if not path.casefold().endswith(extension):
            path += extension
        # Keep a readable natural-width document rather than squeezing dozens
        # of columns into A3. Coordinates retain a single uniform metric scale.
        width = max(1800, self.canvas.minimumWidth() + 50)
        height = max(1200, self.canvas.minimumHeight() + 500)
        if kind == "svg":
            generator = QSvgGenerator()
            generator.setFileName(path)
            generator.setSize(QSize(width, height))
            generator.setViewBox(QRectF(0, 0, width, height))
            generator.setTitle(self.name.text())
            painter = QPainter(generator)
            page = QRectF(0, 0, width, height)
        else:
            writer = QPdfWriter(path)
            from qgis.PyQt.QtCore import QSizeF
            writer.setPageSize(QPageSize(QSizeF(width * 25.4 / 150 + 20, height * 25.4 / 150 + 20), QPageSize.Unit.Millimeter))
            writer.setResolution(150)
            painter = QPainter(writer)
            page = QRectF(0, 0, writer.width(), writer.height())
        try:
            painter.fillRect(page, QColor("white"))
            painter.setPen(QColor("#20252a"))
            painter.setFont(QFont(painter.font().family(), 15, QFont.Weight.Bold))
            painter.drawText(
                QRectF(page.left() + 30, page.top() + 20, page.width() - 60, 36),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.name.text(),
            )
            overview_height = page.height() * 0.25 if self.include_overview.isChecked() else 0
            if overview_height:
                map_rect = QRectF(
                    page.right() - page.width() * 0.34 - 30,
                    page.top() + 65,
                    page.width() * 0.34,
                    overview_height - 20,
                )
                self._draw_overview(painter, map_rect)
            section_top = page.top() + 70 + overview_height
            section_rect = QRectF(
                page.left() + 25, section_top,
                page.width() - 50, page.bottom() - section_top - 25,
            )
            self.canvas.draw_section(
                painter, section_rect, fit=True, show_heading=False
            )
        finally:
            painter.end()
        self.status.setText(
            self.plugin.t("Eksporditud") + f": {path}"
        )

    def _draw_overview(self, painter, rect):
        line = self.effective_line()
        points = [
            (number(item.get("x")), number(item.get("y")))
            for item in self.items
            if number(item.get("x")) is not None
            and number(item.get("y")) is not None
        ]
        traces = [item["trace"] for item in self.items if item.get("enabled", True)
                  and item.get("role") == "local_section" and len(item.get("trace") or []) > 1]
        coordinates = list(line) + points + [point for trace in traces for point in trace]
        if not coordinates:
            return
        extent = QgsRectangle()
        extent.setMinimal()
        for x, y in coordinates:
            extent.include(QgsPointXY(x, y))
        buffer = max(100.0, max(extent.width(), extent.height()) * 0.18)
        extent.grow(buffer)
        image = QImage(
            max(10, round(rect.width())),
            max(10, round(rect.height())),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor("white"))
        settings = QgsMapSettings()
        settings.setLayers(self.plugin.iface.mapCanvas().layers())
        settings.setDestinationCrs(METRIC_CRS)
        settings.setExtent(extent)
        settings.setOutputSize(image.size())
        map_painter = QPainter(image)
        job = QgsMapRendererCustomPainterJob(settings, map_painter)
        job.start()
        job.waitForFinished()
        map_painter.end()
        painter.drawImage(rect, image)

        def map_point(point):
            x = rect.left() + (
                (point[0] - extent.xMinimum()) / max(1.0, extent.width())
            ) * rect.width()
            y = rect.bottom() - (
                (point[1] - extent.yMinimum()) / max(1.0, extent.height())
            ) * rect.height()
            return x, y

        painter.save()
        painter.setPen(QPen(QColor("#d04432"), 2))
        for first, second in zip(line, line[1:]):
            a, b = map_point(first), map_point(second)
            painter.drawLine(round(a[0]), round(a[1]), round(b[0]), round(b[1]))
        painter.setPen(QPen(QColor("#5c3f9d"), 2))
        for trace in traces:
            for first, second in zip(trace, trace[1:]):
                a, b = map_point(first), map_point(second)
                painter.drawLine(round(a[0]), round(a[1]), round(b[0]), round(b[1]))
        painter.setPen(QPen(QColor("#17242e"), 1))
        painter.setBrush(QColor("#ffd34e"))
        for point in points:
            x, y = map_point(point)
            painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#59636b"), 1))
        painter.drawRect(rect)
        painter.restore()

    @staticmethod
    def _json_safe(value):
        return json.loads(json.dumps(
            value, ensure_ascii=False, default=str
        ))


class CrossSectionWindow(QDialog):
    """Resizable, non-modal top-level window for the combined section."""

    visibilityChanged = pyqtSignal(bool)

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.setWindowTitle(plugin.t("Läbilõiked"))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(1400, 900)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.content = CrossSectionWidget(plugin)
        layout.addWidget(self.content)

    def closeEvent(self, event):
        if self.content._outcrop_draft:
            self.content._cancel_outcrop_edit()
            if self.content._outcrop_draft:
                event.ignore()
                return
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.visibilityChanged.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibilityChanged.emit(False)


class CrossSectionLauncher(QWidget):
    """Compact dock-page launcher for the separate section window."""

    def __init__(self, plugin, window):
        super().__init__()
        self.plugin = plugin
        self.window = window
        layout = QVBoxLayout(self)
        message = QLabel(plugin.t(
            "Koondläbilõige avaneb eraldi aknas, et Qeoloogi põhipaan "
            "jääks kompaktseks."
        ))
        message.setWordWrap(True)
        layout.addWidget(message)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle_window)
        layout.addWidget(self.toggle)
        layout.addStretch(1)
        window.visibilityChanged.connect(self._window_visibility_changed)
        window.content.modelChanged.connect(self._set_count)
        self._set_count(len(window.content.items))
        self._window_visibility_changed(window.isVisible())

    def _toggle_window(self, visible):
        if visible:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
        else:
            self.window.hide()

    def _window_visibility_changed(self, visible):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(bool(visible))
        self.toggle.setText(self.plugin.t(
            "Peida läbilõikeaken" if visible else "Ava läbilõikeaken"
        ))
        self.toggle.blockSignals(False)

    def _set_count(self, count):
        self.status.setText(
            f"{int(count)} {self.plugin.t('objekti')} "
            + self.plugin.t("koondläbilõikel")
        )
