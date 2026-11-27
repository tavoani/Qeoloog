"""Mouse editing for local outcrop drawings, separate from the source snapshots."""

from copy import deepcopy
from math import isfinite
from pathlib import Path
from uuid import uuid4

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QKeySequence, QPen, QPolygonF
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QWidget,
)

from .outcrop_features import OutcropDataError, is_outcrop, normalize_record
from .section_workspace import SectionWorkspaceError


POINT_TRACKS = {"biofinds", "outcrop_observations"}
EDIT_TRACKS = POINT_TRACKS | {"outcrop_coverage", "outcrop_shapes"}
TOOLS = (
    ("select", "Vali ja lohista"), ("biofind", "Biotsooni leiupunkt"),
    ("note", "Vaatlus"), ("sample", "Proov"), ("photo", "Foto"),
    ("cover", "Varjatud vahemik"), ("wall", "Seinaprofiil"), ("ledge", "Eend"),
    ("recess", "Süvend"), ("rockfall", "Varingurusu ala"),
)
SHAPE_TOOLS = {"wall", "ledge", "recess", "rockfall"}
COVER_TYPES = (
    ("rockfall_cover", "Varingurusuga kaetud"),
    ("obscured", "Varjatud"), ("unobserved", "Vaatlemata"),
)
OBSERVATION_TYPES = (
    ("note", "Vaatlus"), ("sample", "Proov"), ("photo", "Foto"), ("feature", "Tunnus"),
)
SHAPE_TYPES = tuple((key, label) for key, label in TOOLS if key in SHAPE_TOOLS)


def section_position(geometry, y):
    """Invert the painted log axis (also works for aligned and upturned logs)."""
    at = geometry["y_at"]
    step = at(1.0) - at(0.0)
    value = (y - at(0.0)) / step if step else None
    return None if value is None or not isfinite(value) else max(0.0, round(value, 4))


def _number(value):
    value = float(str(value).strip().replace(",", "."))
    if not isfinite(value):
        raise ValueError()
    return value


def _as_polyline(text):
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        offset, position = line.split(";")
        values.append([_number(offset), _number(position)])
    return values


class OutcropCanvasEditMixin:
    def _init_outcrop_mouse(self):
        self.outcrop_edit_key = ""
        self.outcrop_tool = "select"
        self.outcrop_measured = True
        self._outcrop_geometry = {}
        self._outcrop_drag = None
        self._outcrop_vertices = []
        self._outcrop_hover = None
        self._outcrop_preview_panel = None
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_outcrop_mouse(self, key="", tool="select", measured=True):
        self.outcrop_edit_key = key
        self.outcrop_tool = tool
        self.outcrop_measured = measured
        self.cancel_outcrop_gesture()
        self.setMouseTracking(bool(key))
        self.setCursor(Qt.CursorShape.CrossCursor if key else Qt.CursorShape.ArrowCursor)

    def cancel_outcrop_gesture(self):
        self._outcrop_drag = None
        self._outcrop_vertices = []
        self._outcrop_hover = None
        self._outcrop_preview_panel = None
        self.update()

    def _pick_drawing_record(self, pos):
        for box, key, track, record in reversed(self._paint_hits):
            if (
                key == self.outcrop_edit_key and track.removesuffix("_label") in EDIT_TRACKS
                and isinstance(record, dict) and record.get("id") and box.contains(pos)
            ):
                return track, dict(record)
        return None, None

    def _finish_drawing_shape(self):
        points = self._outcrop_vertices[:]
        kind = self.outcrop_tool
        if len(points) < (3 if kind == "rockfall" else 2):
            self.drawingFeedback.emit(self.plugin.t("Lisa kujule rohkem tippe."))
            return
        self.cancel_outcrop_gesture()
        self.drawingAction.emit(self.outcrop_edit_key, "add", {
            "track": "outcrop_shapes",
            "record": {"points": points, "kind": kind, "measured": self.outcrop_measured},
        })

    def contextMenuEvent(self, event):
        if not self.outcrop_edit_key:
            return super().contextMenuEvent(event)
        if self.outcrop_tool in SHAPE_TOOLS:
            if self._outcrop_vertices:
                self._finish_drawing_shape()
                event.accept()
            return
        if self.outcrop_tool != "select":
            return
        track, record = self._pick_drawing_record(QPointF(event.pos()))
        if record is None:
            return
        menu = QMenu(self)
        edit = menu.addAction(self.plugin.t("Muuda kirjet…"))
        remove = menu.addAction(self.plugin.t("Eemalda kirje"))
        action = menu.exec(event.globalPos())
        if action in (edit, remove):
            self.drawingAction.emit(self.outcrop_edit_key, "details" if action is edit else "delete", {
                "track": track.removesuffix("_label"), "record": record,
            })
        event.accept()

    def mousePressEvent(self, event):
        if not self.outcrop_edit_key or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        geometry = self._outcrop_geometry.get(self.outcrop_edit_key)
        if not geometry:
            return
        pos = event.position()
        measured_pos = section_position(geometry, pos.y())
        if measured_pos is None:
            return
        tool = self.outcrop_tool
        if tool == "select":
            track, record = self._pick_drawing_record(pos)
            if record is not None:
                info = {"mode": "drag", "track": track, "record": record,
                        "at": QPointF(pos), "geometry": geometry,
                        "start": measured_pos}
                if track == "outcrop_coverage":
                    edge = record.get("_edge") or min(("top", "bottom"),
                                key=lambda k: abs(geometry["y_at"](record[k]) - pos.y()))
                    info["edge"] = edge
                if track == "outcrop_shapes":
                    if "_vertex" not in record:
                        return
                    panel = geometry["wall"].get(bool(record.get("measured", True)))
                    if panel is None:
                        return
                    info["panel"] = panel
                self._outcrop_drag = info
        elif tool in SHAPE_TOOLS:
            panel = geometry["wall"].get(self.outcrop_measured)
            if panel and panel.rect.contains(pos):
                new = [round(panel.offset(pos.x()), 4), measured_pos]
                if not self._outcrop_vertices or self._outcrop_vertices[-1] != new:
                    self._outcrop_vertices.append(new)
                self._outcrop_preview_panel = panel
                self._outcrop_hover = QPointF(pos)
                self.update()
        elif geometry["bar_rect"].contains(pos):
            if tool == "cover":
                self._outcrop_drag = {
                    "mode": "cover", "geometry": geometry, "at": QPointF(pos), "start": measured_pos,
                }
            else:
                track = "biofinds" if tool == "biofind" else "outcrop_observations"
                self.drawingAction.emit(self.outcrop_edit_key, "add", {
                    "track": track, "record": {"depth": measured_pos, "kind": tool},
                })
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.outcrop_edit_key:
            return super().mouseMoveEvent(event)
        geometry = (self._outcrop_drag or {}).get("geometry") or self._outcrop_geometry.get(self.outcrop_edit_key)
        if geometry is None:
            return
        pos = event.position()
        self._outcrop_hover = QPointF(pos)
        value = section_position(geometry, pos.y())
        if value is not None:
            text = f"{self.plugin.t('Asend')}: {value:.3f} m"
            if self.outcrop_tool in SHAPE_TOOLS:
                panel = geometry["wall"].get(self.outcrop_measured)
                if panel and panel.rect.contains(pos):
                    text += f" · {self.plugin.t('Nihe')}: {panel.offset(pos.x()):+.3f}"
                    text += " m" if panel.measured else f" ({self.plugin.t('Skemaatiline')})"
            self.drawingFeedback.emit(text)
        self.update()

    def mouseReleaseEvent(self, event):
        if not self.outcrop_edit_key or event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        drag = self._outcrop_drag
        if not drag:
            return
        self._outcrop_drag = None
        pos = event.position()
        delta = pos - drag["at"]
        if abs(delta.x()) + abs(delta.y()) < 2:
            self.update()
            return
        geometry = drag["geometry"]
        value = section_position(geometry, pos.y())
        if value is None:
            return
        if drag["mode"] == "cover":
            a, b = sorted((drag["start"], value))
            if b > a:
                self.drawingAction.emit(self.outcrop_edit_key, "add", {
                    "track": "outcrop_coverage",
                    "record": {"kind": "rockfall_cover", "top": a, "bottom": b},
                })
        else:
            track, record = drag["track"], drag["record"]
            if track.endswith("_label"):
                track = track.removesuffix("_label")
                record["label_dx"] = record.get("label_dx", 0) + delta.x()
                record["label_dy"] = record.get("label_dy", 0) + delta.y()
            elif track == "outcrop_coverage":
                record[drag["edge"]] = value
            elif track == "outcrop_shapes":
                vertex = int(record.pop("_vertex"))
                panel = drag["panel"]
                record["points"] = [list(pt) for pt in record["points"]]
                record["points"][vertex] = [round(panel.offset(pos.x()), 4), value]
            else:
                record["depth"] = value
            self.drawingAction.emit(self.outcrop_edit_key, "replace", {"track": track, "record": record})
        self.update()
        event.accept()

    def keyPressEvent(self, event):
        if self.outcrop_edit_key:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_outcrop_gesture()
                self.drawingFeedback.emit(self.plugin.t("Joonistustoiming katkestatud."))
                return
            if event.matches(QKeySequence.StandardKey.Undo):
                if self._outcrop_vertices:
                    self._outcrop_vertices.pop()
                    self.update()
                else:
                    self.drawingAction.emit(self.outcrop_edit_key, "undo", {})
                return
            if event.matches(QKeySequence.StandardKey.Redo):
                self.drawingAction.emit(self.outcrop_edit_key, "redo", {})
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.outcrop_tool in SHAPE_TOOLS:
                self._finish_drawing_shape()
                return
        super().keyPressEvent(event)

    def _draw_outcrop_edit_preview(self, painter):
        if not self.outcrop_edit_key:
            return
        painter.save()
        painter.setPen(QPen(QColor("#006dba"), 2, Qt.PenStyle.DashLine))
        geometry = self._outcrop_geometry.get(self.outcrop_edit_key)
        if self._outcrop_vertices and geometry and self._outcrop_preview_panel:
            panel = geometry["wall"].get(self.outcrop_measured) or self._outcrop_preview_panel
            points = [QPointF(panel.x(offset), geometry["y_at"](z)) for offset, z in self._outcrop_vertices]
            if self._outcrop_hover is not None and panel.rect.contains(self._outcrop_hover):
                points.append(self._outcrop_hover)
            if len(points) > 1:
                painter.drawPolyline(QPolygonF(points))
            for point in points[:-1] or points:
                painter.drawEllipse(point, 3, 3)
        if self._outcrop_drag and self._outcrop_hover is not None:
            drag = self._outcrop_drag
            if drag["mode"] == "cover":
                rect = drag["geometry"]["bar_rect"]
                y1, y2 = sorted((drag["at"].y(), self._outcrop_hover.y()))
                shade = QRectF(rect.left(), y1, rect.width(), y2 - y1)
                painter.fillRect(shade, QColor(0, 109, 186, 45))
                painter.drawRect(shade)
            else:
                painter.drawLine(drag["at"], self._outcrop_hover)
                painter.drawEllipse(self._outcrop_hover, 4, 4)
        painter.restore()


class OutcropDrawingWidgetMixin:
    def _init_outcrop_drawing(self):
        self._outcrop_draft = None
        self._outcrop_baseline = None
        self._outcrop_undo = []
        self._outcrop_redo = []

    def _build_outcrop_controls(self, layout, start_layout):
        t = self.plugin.t
        self.start_drawing = QPushButton(t("Muuda joonisel"))
        self.start_drawing.clicked.connect(self._start_outcrop_edit)
        start_layout.addWidget(self.start_drawing)
        self.drawing_panel = QWidget()
        panel = QHBoxLayout(self.drawing_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.addWidget(QLabel(t("Paljandi redigeerimine")))
        self.drawing_tools = QComboBox()
        for key, label in TOOLS:
            self.drawing_tools.addItem(t(label), key)
        self.drawing_tools.currentIndexChanged.connect(self._change_outcrop_tool)
        panel.addWidget(self.drawing_tools)
        self.drawing_measured = QCheckBox(t("Mõõdetud"))
        self.drawing_measured.setChecked(True)
        self.drawing_measured.toggled.connect(self._change_outcrop_tool)
        panel.addWidget(self.drawing_measured)
        for attr, label, action in (
            ("drawing_undo", "Võta tagasi", self._undo_outcrop_edit),
            ("drawing_redo", "Tee uuesti", self._redo_outcrop_edit),
            ("drawing_save", "Salvesta paljand", self._save_outcrop_edit),
            ("drawing_cancel", "Katkesta", self._cancel_outcrop_edit),
        ):
            button = QPushButton(t(label))
            button.clicked.connect(action)
            panel.addWidget(button)
            setattr(self, attr, button)
        self.drawing_note = QLabel()
        self.drawing_note.setWordWrap(True)
        self.drawing_note.setMinimumWidth(90)
        panel.addWidget(self.drawing_note, 1)
        layout.addWidget(self.drawing_panel)
        self.drawing_panel.hide()

    def _current_drawing_items(self):
        if not self._outcrop_draft:
            return self.items
        return [self._outcrop_draft if row.get("key") == self._outcrop_draft["key"] else row
                for row in self.items]

    def _start_outcrop_edit(self):
        if self._outcrop_draft or not self._needs_workspace():
            return
        row = self._selected_section_item()
        if not is_outcrop(row or {}) or not row.get("enabled", True) or not row.get("key"):
            self.workspace_status.setText(self.plugin.t("Vali objektide tabelist kuvatav kohalik paljand."))
            return
        if not any(self.item_key(visible) == self.item_key(row) for visible in self.canvas._plot_rows()):
            self.mode.setCurrentIndex(self.mode.findData("relative"))
        self._outcrop_baseline = deepcopy(row)
        self._outcrop_draft = deepcopy(row)
        self._outcrop_undo.clear()
        self._outcrop_redo.clear()
        self.drawing_tools.setCurrentIndex(0)
        self.drawing_panel.show()
        self.start_drawing.setEnabled(False)
        self._change_outcrop_tool()
        self._update_outcrop_actions()

    def _change_outcrop_tool(self, *_):
        if not self._outcrop_draft:
            return
        tool = self.drawing_tools.currentData()
        if tool == "biofind" and not self.display_checks["biofinds"].isChecked():
            self.display_checks["biofinds"].setChecked(True)
        self.drawing_measured.setVisible(tool in SHAPE_TOOLS)
        self.canvas.set_outcrop_mouse(self._outcrop_draft["key"], tool, self.drawing_measured.isChecked())
        self.drawing_note.setText(self.plugin.t(
            "Klõpsa seinaprofiili rajal; Enter lõpetab, Esc katkestab."
            if tool in SHAPE_TOOLS else "Lohista piire, punkte, tippe või silte; paremklõps avab kirje."
            if tool == "select" else "Lohista üle varjatud vahemiku."
            if tool == "cover" else "Klõpsa paljandi tulbal soovitud kõrgusel."))
        self.refresh()
        self.canvas.setFocus()

    def _update_outcrop_actions(self):
        self.drawing_undo.setEnabled(bool(self._outcrop_undo))
        self.drawing_redo.setEnabled(bool(self._outcrop_redo))
        self.drawing_save.setEnabled(self._outcrop_draft != self._outcrop_baseline)

    def _notify_outcrop_edit(self, text):
        if self._outcrop_draft:
            self.drawing_note.setText(text)

    def _receive_drawing_action(self, key, action, payload):
        if not self._outcrop_draft or key != self._outcrop_draft["key"]:
            return
        if action in {"undo", "redo"}:
            (self._undo_outcrop_edit if action == "undo" else self._redo_outcrop_edit)()
            return
        track = payload.get("track")
        if track not in EDIT_TRACKS:
            return
        row = dict(payload["record"])
        row.pop("_vertex", None)
        row.pop("_edge", None)
        original = self._outcrop_draft.get(track) or []
        previous = next((item for item in original if item.get("id") == row.get("id")), None)
        if action != "add" and previous is None:
            return
        if action in {"add", "details"}:
            row = self._drawing_record_dialog(track, row)
            if row is None:
                return
        if action != "delete":
            row["id"] = row.get("id") or uuid4().hex
            row = self._validate_drawing_record(track, row)
            if row is None:
                return
        next_rows = ([item for item in original if item is not previous] if action == "delete"
                     else [row if item is previous else item for item in original]
                     if previous is not None else [*original, row])
        if next_rows == original:
            return
        self._outcrop_undo.append(deepcopy(self._outcrop_draft))
        self._outcrop_undo = self._outcrop_undo[-50:]
        self._outcrop_redo.clear()
        self._outcrop_draft[track] = next_rows
        self._update_outcrop_actions()
        self.refresh()

    def _validate_drawing_record(self, track, row):
        try:
            if track == "biofinds":
                position = _number(row.get("depth"))
                if position < 0 or not (str(row.get("taxon") or "").strip() or str(row.get("zone") or "").strip()):
                    raise ValueError()
                result = dict(row, depth=position)
                result.pop("kind", None)
                for field in ("label_dx", "label_dy"):
                    if field in result:
                        result[field] = _number(result[field])
                return result
            pending = row.get("_chosen_attachment")
            row = dict(row)
            for field in (("depth",) if track == "outcrop_observations"
                          else ("top", "bottom") if track == "outcrop_coverage" else ()):
                row[field] = _number(row.get(field))
            result = normalize_record(track, row)
            if pending:
                result["_chosen_attachment"] = pending
            return result
        except (TypeError, ValueError, OutcropDataError) as error:
            self._notify_outcrop_edit(
                self.plugin.t("Kirje väärtused ei sobi.") + (
                    f" {self.plugin.t(str(error))}" if str(error) else ""))
            return None

    def _drawing_record_dialog(self, track, row):
        t = self.plugin.t
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Muuda kirjet…"))
        form = QFormLayout(dialog)
        data = dict(row)
        edits = {}
        kinds = {
            "outcrop_observations": OBSERVATION_TYPES,
            "outcrop_coverage": COVER_TYPES, "outcrop_shapes": SHAPE_TYPES,
        }.get(track)
        if kinds:
            kind = QComboBox()
            for key, label in kinds:
                kind.addItem(t(label), key)
            kind.setCurrentIndex(max(0, kind.findData(row.get("kind"))))
            form.addRow(t("Tüüp"), kind)
        fields = {
            "biofinds": (("depth", "Asend (m)"), ("taxon", "Takson"),
                         ("zone", "Biotsoon"), ("sample_ref", "Proovi viide"),
                         ("source_ref", "Allika viide"), ("note", "Märkus")),
            "outcrop_observations": (("depth", "Asend (m)"), ("text", "Märkus"),
                                     ("sample_ref", "Proovi viide"), ("source_ref", "Allika viide")),
            "outcrop_coverage": (("top", "Vahemiku algus (m)"), ("bottom", "Vahemiku lõpp (m)"),
                                 ("text", "Märkus")),
            "outcrop_shapes": (("text", "Märkus"),),
        }[track]
        if track == "outcrop_shapes":
            points = QPlainTextEdit("\n".join(f"{x:g}; {y:g}" for x, y in row.get("points") or ()))
            form.addRow(t("Tipud: nihe; asend (üks paar real)"), points)
            form.addRow(QLabel(t("Samu kõrgusi võib kasutada mitu korda. Jäta tippude järjekord alles.")))
            measured = QCheckBox(t("Mõõdetud"))
            measured.setChecked(bool(row.get("measured", True)))
            form.addRow(measured)
        for key, label in fields:
            edit = QLineEdit(str(row.get(key) if row.get(key) is not None else ""))
            edits[key] = edit
            form.addRow(t(label), edit)
        if track == "outcrop_observations":
            attach_btn = QPushButton(t("Vali foto või manus…"))
            attachment_note = QLabel(str(row.get("_chosen_attachment") or row.get("attachment") or ""))
            def attach():
                chosen, _ = QFileDialog.getOpenFileName(dialog, t("Vali foto või manus…"))
                if chosen:
                    data["_chosen_attachment"] = chosen
                    attachment_note.setText(Path(chosen).name)
            attach_btn.clicked.connect(attach)
            form.addRow(attach_btn, attachment_note)
        self._dialog_buttons(dialog, form)
        while dialog.exec():
            data.update({field: edit.text().strip() for field, edit in edits.items()})
            if kinds:
                data["kind"] = kind.currentData()
            if track == "outcrop_shapes":
                try:
                    data["points"] = _as_polyline(points.toPlainText())
                    data["measured"] = measured.isChecked()
                except (TypeError, ValueError):
                    QMessageBox.warning(dialog, t("Muuda kirjet…"), t("Sisesta igale reale kaks arvu: nihe; asend."))
                    continue
            result = self._validate_drawing_record(track, data)
            if result is not None:
                return result
            QMessageBox.warning(dialog, t("Muuda kirjet…"), self.drawing_note.text())
        return None

    def _undo_outcrop_edit(self):
        if self._outcrop_undo:
            self._outcrop_redo.append(self._outcrop_draft)
            self._outcrop_draft = self._outcrop_undo.pop()
            self._update_outcrop_actions()
            self.refresh()

    def _redo_outcrop_edit(self):
        if self._outcrop_redo:
            self._outcrop_undo.append(self._outcrop_draft)
            self._outcrop_draft = self._outcrop_redo.pop()
            self._update_outcrop_actions()
            self.refresh()

    def _end_outcrop_edit(self, refresh=True):
        self._outcrop_undo.clear()
        self._outcrop_redo.clear()
        self._outcrop_draft = self._outcrop_baseline = None
        self.canvas.set_outcrop_mouse()
        self.drawing_panel.hide()
        self.start_drawing.setEnabled(True)
        if refresh:
            self.refresh()

    def _cancel_outcrop_edit(self):
        if not self._outcrop_draft:
            return
        t = self.plugin.t
        if self._outcrop_draft == self._outcrop_baseline or QMessageBox.question(
            self, t("Katkesta"), t("Kas loobuda salvestamata joonise muudatustest?")
        ) == QMessageBox.StandardButton.Yes:
            self._end_outcrop_edit()

    def _require_closed_outcrop_edit(self):
        if self._outcrop_draft:
            self._notify_outcrop_edit(self.plugin.t("Salvesta või katkesta esmalt paljandi redigeerimine."))
            return False
        return True

    def _save_outcrop_edit(self):
        if not self.workspace or not self._outcrop_draft:
            return False
        draft = deepcopy(self._outcrop_draft)
        index = next((i for i, row in enumerate(self.items) if row.get("key") == draft["key"]), None)
        if index is None or not is_outcrop(self.items[index]):
            return False
        try:
            for record in draft.get("outcrop_observations") or []:
                chosen = record.pop("_chosen_attachment", None)
                if chosen:
                    record["attachment"] = self.workspace.add_attachment(Path(chosen))
                    record["attachment_name"] = Path(chosen).name
            state = self._section_state()
            state["items"][index] = draft
            self.workspace.save_log_and_section(
                draft, draft["id"], state, self.workspace_section_id
            )
        except (KeyError, OSError, SectionWorkspaceError) as error:
            self._workspace_error(error)
            return False
        self.items[index] = draft
        self._workspace_link_to_project()
        self._schedule_workspace_backup()
        self._end_outcrop_edit()
        self._select_item_key(draft["key"])
        return True
