"""Named, portable sections and read-only links to public source records."""

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
from uuid import uuid4

from qgis.PyQt.QtCore import QTimer, QUrl, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QToolButton, QVBoxLayout,
)
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsCsException,
    QgsExpression, QgsFeatureRequest, QgsPointXY, QgsProject, QgsSettings,
)

from .identify import CrossSectionLineTool, FaktikaPointTool
from .local_section_editor import edit_local_section
from .section_workspace import SectionWorkspace, SectionWorkspaceError


WORKSPACE_ENTRY = "section_workspace_v1"
SOURCE_ROLES = {
    "boreholes": "EGT", "observations": "EGT",
    "sarv_drillcores": "SARV", "sarv_localities": "SARV", "sarv_sites": "SARV",
    "veka_boreholes": "VEKA",
}
TRACKS = ("units", "biofinds", "biozones", "stages", "isotopes",
          "outcrop_observations", "outcrop_coverage", "outcrop_shapes")
TRACK_LABELS = {
    "units": "Kihid", "biozones": "Tõlgendatud biotsoonide ulatus", "stages": "Lademed",
    "isotopes": "Isotoobid", "biofinds": "Biotsoonide leiupunktid",
    "outcrop_observations": "Paljandi vaatlused", "outcrop_coverage": "Varjatud vahemikud",
    "outcrop_shapes": "Seinaprofiil",
}


def _identifier(value):
    text = str(value if value is not None else "").strip()
    return "" if text.casefold() in {"", "none", "null", "<null>"} else text


def section_source_ref(snapshot, attributes=None):
    """Use native IDs, never a display name, nearest point or QGIS feature ID."""
    role = snapshot.get("role")
    if role not in SOURCE_ROLES or snapshot.get("faktika"):
        return {}
    attrs = attributes or {}
    def first(*names):
        return next((value for name in names for raw in (attrs.get(name), snapshot.get(name))
                     if (value := _identifier(raw))), "")
    ids = {}
    if SOURCE_ROLES[role] == "EGT":
        ids = {"globalid": first("esri_globalid", "global_id", "globalid"),
               "gea_id": first("gea_id")}
        legacy = first("id")
        if not ids["globalid"] and re.fullmatch(
            r"\{?[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}?", legacy
        ):
            ids["globalid"] = legacy
        elif not ids["gea_id"] and legacy.isdigit():
            ids["gea_id"] = legacy
    elif SOURCE_ROLES[role] == "SARV":
        ids = {"sarv_id": first("sarv_id", "id")}
        if not ids["sarv_id"].isdigit():
            ids = {}
    else:
        ids = {"eelis_id": first("eelis_id", "id"),
               "kkr_kood": first("kkr_kood")}
        if not ids["kkr_kood"] and re.fullmatch(r"PRK[0-9]+", first("nimi", "name").upper()):
            ids["kkr_kood"] = first("nimi", "name").upper()
        if not ids["eelis_id"].isdigit():
            ids["eelis_id"] = ""
    ids = {name: value for name, value in ids.items() if value}
    return {"provider": SOURCE_ROLES[role], "collection": role, **ids} if ids else {}


def source_url(ref):
    role = ref.get("collection")
    if SOURCE_ROLES.get(role) != ref.get("provider"):
        return ""
    if role in {"boreholes", "observations"}:
        gea_id = ref.get("gea_id", "")
        if re.fullmatch(r"[0-9]+", str(gea_id)):
            kind = "puurauk" if role == "boreholes" else "vaatluspunkt"
            return f"https://gis.egt.ee/auk/{kind}/{gea_id}/vaade"
    if role in {"sarv_drillcores", "sarv_localities", "sarv_sites"}:
        identifier = ref.get("sarv_id", "")
        if re.fullmatch(r"[0-9]+", str(identifier)):
            kind = {"sarv_drillcores": "drillcore", "sarv_localities": "locality",
                    "sarv_sites": "site"}[role]
            return f"https://geoloogia.info/{kind}/{identifier}"
    if role == "veka_boreholes":
        kkr = str(ref.get("kkr_kood", "")).upper()
        if re.fullmatch(r"PRK[0-9]+", kkr):
            return f"https://veka.eelis.ee/puurauk/{kkr}"
    return ""


def section_record_ids(item):
    """Supply stable anchor IDs for imported source records with no explicit ID."""
    for key in TRACKS:
        seen = {}
        used = set()
        for row in item.get(key, ()) or ():
            if not isinstance(row, dict):
                continue
            identifier = _identifier(row.get("id")) or _identifier(row.get("esri_globalid"))
            if identifier and identifier not in used:
                row["id"] = identifier
                used.add(identifier)
                continue
            signature = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
            digest = sha256(signature.encode("utf-8")).hexdigest()[:24]
            seen[digest] = seen.get(digest, 0) + 1
            row["id"] = f"{digest}-{seen[digest]}"
            used.add(row["id"])
    return item


def public_workspace_items(items):
    """Keep unsupported legacy/Portal records out of the portable workspace."""
    return [item for item in items if not item.get("faktika")
            and (item.get("role") in SOURCE_ROLES or item.get("role") == "local_section"
                 or not item.get("role"))]


class SectionWorkspaceMixin:
    def _init_section_workspace(self):
        self.workspace = None
        self.workspace_section_id = ""
        self.workspace_unavailable = False
        self.section_layout = {}
        self.section_correlations = []
        self.section_alignments = {}
        self._workspace_serial = uuid4()
        self._workspace_backup_timer = QTimer(self)
        self._workspace_backup_timer.setSingleShot(True)
        self._workspace_backup_timer.timeout.connect(self._auto_workspace_backup)
        self._cancel_section_pick = None

    def _workspace_controls(self, outer):
        t = self.plugin.t
        row = QHBoxLayout()
        self.section_selector = QComboBox()
        self.section_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.section_selector.setMinimumContentsLength(16)
        self.section_selector.currentIndexChanged.connect(self._switch_workspace_section)
        row.addWidget(self.section_selector, 1)
        for title, actions in (
            ("Tööruum", (
                ("Loo töökaust…", lambda: self._choose_workspace(True)),
                ("Ava olemasolev töökaust…", lambda: self._choose_workspace(False)),
                ("Ava töökaust Finderis / failihalduris", self._show_workspace_folder),
                ("Varundamise seaded…", self._workspace_backup_settings),
                ("Tee varukoopia kohe", self._backup_workspace),
                ("Taasta koopiast…", self._restore_workspace),
            )),
            ("Läbilõige", (
                ("Uus nimeline läbilõige…", lambda: self._new_workspace_section(False)),
                ("Tee läbilõikest koopia…", lambda: self._new_workspace_section(True)),
                ("Lisa korrelatsioon…", self._add_section_correlation),
                ("Halda korrelatsioone…", self._remove_section_correlation),
                ("Joonda valitud tulp…", self._align_section_item),
                ("Lähtesta joondus", self._clear_section_alignment),
                ("Kopeeri kujundus teisest läbilõikest…", self._copy_section_style),
            )),
            ("Tulbad", (
                ("Lisa kohalik tulp või paljand…", self._new_local_log),
                ("Lisa tulp tööruumist…", self._add_workspace_log),
                ("Redigeeri valitud tulpa…", self._edit_selected_log),
                ("Ava valitud tulba algkirje", self._open_selected_source),
                ("Mine valitud tulba asukohta", self._go_to_selected_log),
                ("Ava kohalik manus…", self._open_local_attachment),
            )),
        ):
            button = QToolButton()
            button.setText(t(title))
            menu = QMenu(button)
            for text, action in actions:
                menu.addAction(t(text), action)
            button.setMenu(menu)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            row.addWidget(button)
        outer.addLayout(row)
        self.workspace_status = QLabel()
        self.workspace_status.setWordWrap(True)
        outer.addWidget(self.workspace_status)
        self._update_workspace_controls()

    def _section_style_controls(self, options):
        t = self.plugin.t
        group = QGroupBox(t("Kujundus"))
        form = QFormLayout(group)
        self.section_style = QComboBox()
        self.section_style.addItem("Qeoloog", "classic")
        self.section_style.addItem(t("StrataPy-laadne"), "stratapy")
        self.section_style.currentIndexChanged.connect(self._display_changed)
        form.addRow(t("Stiil"), self.section_style)
        customize = QPushButton(t("Kohanda joonist…"))
        customize.clicked.connect(self._edit_section_layout)
        form.addRow(customize)
        options.addWidget(group)

    def _edit_section_layout(self):
        t = self.plugin.t
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Kohanda joonist…"))
        form = QFormLayout(dialog)
        controls = {}
        for key, label in (("title", "Pealkiri"), ("subtitle", "Alapealkiri"),
                           ("notes", "Märkus")):
            controls[key] = QLineEdit(str(self.section_layout.get(key, "")))
            form.addRow(t(label), controls[key])
        width = QDoubleSpinBox()
        width.setRange(20, 100)
        width.setValue(float(self.section_layout.get("column_width", 58)))
        form.addRow(t("Tulba laius (px)"), width)
        colored = QCheckBox(t("Säilita EGT indeksivärvid"))
        colored.setChecked(self.section_layout.get("pattern_colors", True))
        legend = QCheckBox(t("Kuva legend"))
        legend.setChecked(self.section_layout.get("legend", True))
        form.addRow(colored)
        form.addRow(legend)
        gap = QDoubleSpinBox()
        gap.setRange(0, 10000)
        gap.setDecimals(3)
        gap.setValue(float(self.section_layout.get("isotope_max_gap") or 0))
        form.addRow(t("Katkesta isotoobikõver, kui vahe ületab (m; 0 = väljas)"), gap)
        order = QComboBox()
        import itertools
        for keys in itertools.permutations(("isotopes", "biofinds", "biozones", "stages")):
            order.addItem(" → ".join(t(TRACK_LABELS[key]) for key in keys), list(keys))
        index = order.findData(self.section_layout.get("track_order", []))
        order.setCurrentIndex(max(0, index))
        form.addRow(t("Radade järjekord"), order)
        self._dialog_buttons(dialog, form)
        if dialog.exec():
            self.section_layout = {key: control.text() for key, control in controls.items()}
            self.section_layout.update(column_width=width.value(), pattern_colors=colored.isChecked(),
                                       legend=legend.isChecked(), track_order=order.currentData(),
                                       isotope_max_gap=gap.value() or None)
            self._display_changed()

    def _copy_section_style(self):
        if not self._require_closed_outcrop_edit() or not self._needs_workspace():
            return
        try:
            entries = {f"{item['name']} · {item['id']}": item["id"]
                       for item in self.workspace.list_sections()
                       if item["id"] != self.workspace_section_id}
            if not entries:
                return
            title, accepted = QInputDialog.getItem(
                self, self.plugin.t("Kopeeri kujundus teisest läbilõikest…"),
                self.plugin.t("Läbilõige"), list(entries), 0, False,
            )
            if not accepted:
                return
            state = self._section_state()
            other = self.workspace.load_section(entries[title])
            for key in ("style", "layout", "display"):
                state[key] = other.get(key)
            self._apply_section_state(state)
            self.save_project_state()
        except SectionWorkspaceError as error:
            self._workspace_error(error)

    @staticmethod
    def _dialog_buttons(dialog, layout):
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if isinstance(layout, QFormLayout):
            layout.addRow(buttons)
        else:
            layout.addWidget(buttons)

    def _workspace_error(self, error):
        message = self.plugin.t("Läbilõigete tööruumi toiming ebaõnnestus.")
        self.workspace_status.setText(f"{message} {error}")

    def _update_workspace_controls(self):
        t = self.plugin.t
        self.section_selector.blockSignals(True)
        self.section_selector.clear()
        self.section_selector.setEnabled(bool(self.workspace))
        if self.workspace:
            try:
                for entry in self.workspace.list_sections():
                    self.section_selector.addItem(entry["name"], entry["id"])
                self.section_selector.setCurrentIndex(
                    self.section_selector.findData(self.workspace_section_id))
                self.workspace_status.setText(f"{t('Töökaust')}: {self.workspace.folder}")
            except SectionWorkspaceError as error:
                self._workspace_error(error)
        else:
            self.section_selector.addItem(t("Projekti läbilõige"))
            self.workspace_status.setText(
                t("Töökaust pole kättesaadav. Ava olemasolev töökaust või taasta varukoopiast.")
                if self.workspace_unavailable else
                t("Nimeliste läbilõigete ja kohalike tulpade jaoks vali töökaust."))
        self.section_selector.blockSignals(False)

    def _workspace_link_to_project(self):
        project = QgsProject.instance()
        path = project.pathResolver().writePath(str(self.workspace.folder))
        project.writeEntry("Qeoloog", WORKSPACE_ENTRY, json.dumps({
            "folder": path, "section": self.workspace_section_id,
        }))

    def _choose_workspace(self, create):
        if not self._require_closed_outcrop_edit():
            return
        t = self.plugin.t
        path = QFileDialog.getExistingDirectory(self, t(
            "Loo töökaust…" if create else "Ava olemasolev töökaust…"))
        if path and (not self.workspace or self.save_project_state()):
            try:
                self._activate_workspace(SectionWorkspace.open(path, create=create),
                                         migrate=create)
            except (OSError, SectionWorkspaceError) as error:
                self._workspace_error(error)

    def _activate_workspace(self, workspace, *, migrate=False):
        entries = workspace.list_sections()
        if entries:
            reference = entries[0]["id"]
            state = workspace.load_section(reference)
        else:
            state = self._section_state() if migrate else {}
            state["items"] = public_workspace_items(state.get("items", []))
            state["name"] = state.get("name") or self.plugin.t("Koondläbilõige")
            reference = workspace.save_section(state)
        self._workspace_backup_timer.stop()
        self._workspace_serial = uuid4()
        self.workspace = workspace
        self.workspace_section_id = reference
        self.workspace_unavailable = False
        self._apply_section_state(state)
        self._workspace_link_to_project()
        self._update_workspace_controls()
        notify = getattr(self.plugin, 'local_workspace_changed', None)
        if notify:
            notify()

    def _switch_workspace_section(self, index):
        reference = self.section_selector.itemData(index)
        if not self.workspace or not reference or reference == self.workspace_section_id:
            return
        if not self._require_closed_outcrop_edit():
            self._update_workspace_controls()
            return
        try:
            if not self.save_project_state():
                self._update_workspace_controls()
                return
            state = self.workspace.load_section(reference)
            self._workspace_serial = uuid4()
            self.workspace_section_id = reference
            self._apply_section_state(state)
            self._workspace_link_to_project()
            self._update_workspace_controls()
        except SectionWorkspaceError as error:
            self._update_workspace_controls()
            self._workspace_error(error)

    def _new_workspace_section(self, duplicate):
        if not self._require_closed_outcrop_edit() or not self._needs_workspace():
            return
        t = self.plugin.t
        name, ok = QInputDialog.getText(self, t("Läbilõige"), t("Nimi"))
        if not ok or not name.strip() or not self.save_project_state():
            return
        try:
            state = self._section_state() if duplicate else {}
            state["name"] = name.strip()
            reference = self.workspace.save_section(state)
            self._workspace_serial = uuid4()
            self.workspace_section_id = reference
            self._apply_section_state(state)
            self._workspace_link_to_project()
            self._update_workspace_controls()
        except SectionWorkspaceError as error:
            self._workspace_error(error)

    def _needs_workspace(self):
        if not self.workspace:
            self.workspace_status.setText(self.plugin.t("Vali esmalt töökaust."))
            return False
        return True

    def _show_workspace_folder(self):
        if self._needs_workspace():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.workspace.folder)))

    def _workspace_backup_key(self, field):
        path_hash = sha256(str(self.workspace.folder).encode("utf-8")).hexdigest()
        return f"Qeoloog/section_workspace/{path_hash}/{field}"

    def _workspace_backup_destination(self):
        return QgsSettings().value(self._workspace_backup_key("folder"), "", type=str)

    def _workspace_backup_settings(self):
        if not self._needs_workspace():
            return
        t = self.plugin.t
        path = QFileDialog.getExistingDirectory(
            self, t("Vali varukoopiate kaust"), self._workspace_backup_destination())
        if not path:
            return
        work = self.workspace.folder.resolve()
        dest = Path(path).resolve()
        if dest == work or work in dest.parents:
            self._workspace_error(t("Varukoopiad peavad asuma väljaspool töökausta."))
            return
        settings = QgsSettings()
        settings.setValue(self._workspace_backup_key("folder"), path)
        auto = QMessageBox.question(
            self, t("Varundamise seaded…"),
            t("Varunda automaatselt pärast salvestamist (säilita viimased 10 koopiat)?"),
        ) == QMessageBox.StandardButton.Yes
        settings.setValue(self._workspace_backup_key("auto"), auto)
        self._workspace_backup_timer.stop()

    def _schedule_workspace_backup(self):
        if self.workspace and self._workspace_backup_destination() and QgsSettings().value(
            self._workspace_backup_key("auto"), False, type=bool,
        ):
            self._workspace_backup_timer.start(5000)

    def _auto_workspace_backup(self):
        if self.workspace and self._workspace_backup_destination():
            self._write_workspace_backup(self._workspace_backup_destination(), keep=10)

    def _backup_workspace(self):
        if not self._needs_workspace() or not self.save_project_state():
            return
        existing = self._workspace_backup_destination()
        path = existing or QFileDialog.getExistingDirectory(
            self, self.plugin.t("Vali varukoopiate kaust"))
        if path:
            self._workspace_backup_timer.stop()
            self._write_workspace_backup(path)

    def _write_workspace_backup(self, path, keep=None):
        try:
            result = self.workspace.backup(path, keep=keep)
            self.workspace_status.setText(f"{self.plugin.t('Varukoopia')}: {result}")
        except (OSError, SectionWorkspaceError) as error:
            self._workspace_error(error)

    def _restore_workspace(self):
        if not self._require_closed_outcrop_edit():
            return
        t = self.plugin.t
        source = QFileDialog.getExistingDirectory(self, t("Vali varukoopia kaust"))
        if not source:
            return
        destination = QFileDialog.getExistingDirectory(self, t("Vali taastatud töökausta ülemkaust"))
        if not destination:
            return
        if self.workspace and not self.save_project_state():
            return
        try:
            new = Path(destination) / f"Qeoloog-{t('Taastatud')}-{uuid4().hex[:8]}"
            self._activate_workspace(SectionWorkspace.restore(source, new))
        except (OSError, SectionWorkspaceError) as error:
            self._workspace_error(error)

    def _selected_section_item(self):
        index = self._item_index_for_table_row(self.table.currentRow())
        return self.items[index] if 0 <= index < len(self.items) else None

    def _new_local_log(self):
        self._edit_workspace_log(None)

    def _edit_selected_log(self):
        item = self._selected_section_item()
        if item is None:
            return
        if item.get("role") != "local_section" and not section_source_ref(item) and not (
            item.get("source_ref", {}).get("provider") in set(SOURCE_ROLES.values())
        ):
            self.workspace_status.setText(self.plugin.t("Toetatud allikad: EGT, SARV ja VEKA."))
            return
        self._edit_workspace_log(item)

    def _edit_workspace_log(self, item):
        if not self._require_closed_outcrop_edit() or not self._needs_workspace():
            return
        workspace, serial = self.workspace, self._workspace_serial
        draft = self._json_safe(item) if item else {}
        existing = draft.get("role") == "local_section"
        old_key = self.item_key(item or {})
        if item and not existing:
            draft["source_ref"] = draft.get("source_ref") or section_source_ref(draft)
            draft["source_original"] = {key: draft[key] for key in (
                "key", "name", "source", "role", "id", "x", "y", "depth", "elevation",
                "units", "source_ref") if key in draft}
            draft.pop("id", None)
            draft.pop("key", None)
            draft.pop("role", None)
        draft = section_record_ids(draft)
        try:
            revised = edit_local_section(
                self, self.plugin, draft, map_pick=self._pick_local_anchor,
                add_attachment=workspace.add_attachment, map_pick_line=self._pick_local_trace,
            )
            if revised is None or serial != self._workspace_serial:
                return
            index = next((i for i, row in enumerate(self.items) if self.item_key(row) == old_key), None) if item else None
            if item and index is None:
                return
            log_id = revised.get("id") or str(uuid4())
            revised.update(id=log_id, key=f"local:{log_id}", role="local_section")
            workspace.save_log(revised, log_id)
        except (OSError, SectionWorkspaceError) as error:
            self._workspace_error(error)
            return
        if item:
            revised["enabled"] = self.items[index].get("enabled", True)
            self.items[index] = revised
            if old_key and old_key != revised["key"]:
                anchor = self.section_alignments.pop(old_key, None)
                if anchor:
                    anchor["item_key"] = revised["key"]
                    self.section_alignments[revised["key"]] = anchor
                for link in self.section_correlations:
                    for endpoint in (link["left"], link["right"]):
                        if endpoint["item_key"] == old_key:
                            endpoint["item_key"] = revised["key"]
            self.refresh()
            self._select_item_key(revised["key"])
            self.save_project_state()
        else:
            self.add_snapshot(revised)

    def _add_workspace_log(self):
        if not self._require_closed_outcrop_edit() or not self._needs_workspace():
            return
        try:
            entries = self.workspace.list_logs()
            indexed = {f"{item['name']} · {item['id']}": item["id"] for item in entries}
            if not indexed:
                self.workspace_status.setText(self.plugin.t("Tööruumis pole veel kohalikke tulpi."))
                return
            title, ok = QInputDialog.getItem(self, self.plugin.t("Lisa tulp tööruumist…"),
                                             self.plugin.t("Tulp"), list(indexed), 0, False)
            if ok:
                self.add_snapshot(self.workspace.load_log(indexed[title]))
        except SectionWorkspaceError as error:
            self._workspace_error(error)

    def _open_selected_source(self):
        item = self._selected_section_item()
        if item:
            self._open_section_source(self.item_key(item))

    def _open_section_source(self, key):
        item = next((row for row in self.items if self.item_key(row) == key), None)
        if not item:
            return
        ref = item.get("source_ref") or section_source_ref(item)
        if self._open_source_in_qgis(ref, item.get("name")):
            self.window().hide()
            return
        url = source_url(ref)
        if url:
            QDesktopServices.openUrl(QUrl(url))
            return
        if ref:
            self.workspace_status.setText(
                f"{self.plugin.t('Algkirje ei ole avatud kihis')}: "
                + ", ".join(f"{key}={value}" for key, value in ref.items()))
        else:
            self.workspace_status.setText(self.plugin.t("Tulbal puudub algkirje viide."))

    def _open_source_in_qgis(self, ref, name):
        role = ref.get("collection")
        if SOURCE_ROLES.get(role) != ref.get("provider") or not role:
            return False
        matching = {
            "esri_globalid": "globalid", "globalid": "globalid", "gea_id": "gea_id",
            "sarv_id": "sarv_id", "eelis_id": "eelis_id", "kkr_kood": "kkr_kood",
        }
        for layer in self.plugin._role_layers(role):
            groups = {}
            for field, key in matching.items():
                if ref.get(key) and layer.fields().indexOf(field) >= 0:
                    quoted = QgsExpression.quotedString(str(ref[key]).lower())
                    groups.setdefault(key, []).append(f'lower(to_string("{field}")) = {quoted}')
            if not groups:
                continue
            features = layer.getFeatures(QgsFeatureRequest().setFilterExpression(
                " AND ".join("(" + " OR ".join(group) + ")" for group in groups.values())
            ).setLimit(2))
            feature = next(features, None)
            if feature is not None and next(features, None) is None:
                self.plugin.open_search_result({
                    "_layer_id": layer.id(), "_feature_id": feature.id(),
                    "_role": role, "name": name,
                })
                return True
        return False

    def _go_to_selected_log(self):
        item = self._selected_section_item()
        if item and self.plugin.go_to_detail_location(
            {"_qeoloog_x_3301": item.get("x"), "_qeoloog_y_3301": item.get("y")},
        ):
            self.window().hide()

    def _open_local_attachment(self):
        item = self._selected_section_item()
        if not self.workspace or not item or not item.get("attachments"):
            return
        paths = {f"{i + 1}. {ref.get('name', '')}": ref["path"]
                 for i, ref in enumerate(item["attachments"]) if ref.get("path")}
        title, ok = QInputDialog.getItem(self, self.plugin.t("Ava kohalik manus…"),
                                         self.plugin.t("Manus"), list(paths), 0, False)
        if ok and title in paths:
            try:
                filename = self.workspace.attachment_path(paths[title])
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(filename)))
            except SectionWorkspaceError as error:
                self._workspace_error(error)

    def _pick_local_anchor(self, callback):
        self._pick_section_geometry(callback, False)

    def _pick_local_trace(self, callback):
        self._pick_section_geometry(callback, True)

    def _pick_section_geometry(self, callback, line):
        if self._cancel_section_pick:
            self._cancel_section_pick()
        canvas = self.plugin.iface.mapCanvas()
        previous = canvas.mapTool()
        tool = CrossSectionLineTool(canvas) if line else FaktikaPointTool(canvas)
        window = self.window()
        hidden = window.isVisible()
        if hidden:
            window.hide()

        def finish(*args):
            if self._cancel_section_pick is None:
                return
            self._cancel_section_pick = None
            try:
                canvas.mapToolSet.disconnect(changed)
            except (TypeError, RuntimeError):
                pass
            if canvas.mapTool() is tool:
                canvas.setMapTool(previous) if previous else canvas.unsetMapTool(tool)
            if line:
                canvas.scene().removeItem(tool.band)
                canvas.scene().removeItem(tool.snap_marker)
            tool.deleteLater()
            if hidden:
                window.show()
                window.raise_()
            callback(*args)

        def changed(new, old):
            if old is tool and new is not tool:
                finish()

        def picked(raw):
            try:
                transform = QgsCoordinateTransform(
                    canvas.mapSettings().destinationCrs(),
                    QgsCoordinateReferenceSystem("EPSG:3301"), QgsProject.instance())
                if line:
                    points = [transform.transform(QgsPointXY(*p)) for p in raw]
                    finish([(p.x(), p.y()) for p in points])
                else:
                    point = transform.transform(QgsPointXY(raw))
                    finish(point.x(), point.y())
            except QgsCsException:
                finish()

        self._cancel_section_pick = finish
        (tool.lineFinished if line else tool.pointSelected).connect(picked)
        tool.cancelled.connect(finish)
        canvas.mapToolSet.connect(changed)
        canvas.setMapTool(tool)
        canvas.setFocus()
        self.plugin.message(self.plugin.t(
            "Märgi paljandi joon kaardil (Enter lõpetab, Esc katkestab)." if line
            else "Vali tulba asukoht kaardilt (Esc katkestab)."))

    def _anchors(self, items):
        choices = []
        for item in items:
            for track in ("units", "biofinds", "biozones", "stages", "isotopes"):
                for row in item.get(track, ()):
                    if not row.get("id"):
                        continue
                    if track == "isotopes" and row.get("value") is None:
                        continue
                    edges = [("point", row.get("depth"))] if track in {"isotopes", "biofinds"} else [
                        ("top", row.get("z_suht_ylemine")), ("base", row.get("z_suht_alumine")),
                    ]
                    label = (row.get("name") or row.get("indeks") or row.get("litoloogia")
                             or row.get("analyte") or row.get("taxon") or row.get("zone") or "")
                    for edge, depth in edges:
                        try:
                            pos = float(depth)
                        except (ValueError, TypeError):
                            continue
                        if not isfinite(pos):
                            continue
                        ref = {"item_key": self.item_key(item), "track": track,
                               "id": str(row["id"]), "boundary": edge}
                        edge_label = self.plugin.t({"top": "Algus", "base": "Lõpp", "point": "Punkt"}[edge])
                        text = f"{item.get('name')} · {self.plugin.t(TRACK_LABELS[track])} · {label} · {edge_label} {pos:g} m"
                        choices.append((text, ref))
        return choices

    def _add_section_correlation(self):
        t = self.plugin.t
        choices = self._anchors(self.items)
        if len({ref["item_key"] for _, ref in choices}) < 2:
            self.workspace_status.setText(t("Korrelatsiooniks on vaja kahe tulba piire või mõõtepunkte."))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Lisa korrelatsioon…"))
        form = QFormLayout(dialog)
        a, b = QComboBox(), QComboBox()
        for text, ref in choices:
            a.addItem(text, ref)
        def update_right():
            b.clear()
            left = a.currentData()
            for text, ref in choices:
                if ref["item_key"] != left["item_key"]:
                    b.addItem(text, ref)
        a.currentIndexChanged.connect(update_right)
        update_right()
        label = QLineEdit()
        inferred = QCheckBox(t("Oletuslik ühendus"))
        inferred.setChecked(True)
        form.addRow(t("Algus"), a)
        form.addRow(t("Lõpp"), b)
        form.addRow(t("Nimi"), label)
        form.addRow(inferred)
        self._dialog_buttons(dialog, form)
        if dialog.exec() and b.currentData():
            self.section_correlations.append({
                "id": str(uuid4()), "left": a.currentData(), "right": b.currentData(),
                "label": label.text(), "inferred": inferred.isChecked(),
            })
            self._display_changed()

    def _remove_section_correlation(self):
        if not self.section_correlations:
            return
        t = self.plugin.t
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Halda korrelatsioone…"))
        form = QVBoxLayout(dialog)
        checks = []
        for i, link in enumerate(self.section_correlations):
            box = QCheckBox(f"{t('Eemalda')} {i + 1}: {link.get('label') or link['left']['item_key']}")
            form.addWidget(box)
            checks.append(box)
        self._dialog_buttons(dialog, form)
        if dialog.exec():
            self.section_correlations = [
                link for link, check in zip(self.section_correlations, checks) if not check.isChecked()]
            self._display_changed()

    def _align_section_item(self):
        item = self._selected_section_item()
        choices = self._anchors([item]) if item else []
        if not choices:
            return
        indexed = {f"{i + 1}. {text}": ref for i, (text, ref) in enumerate(choices)}
        title, accepted = QInputDialog.getItem(
            self, self.plugin.t("Joonda valitud tulp…"), self.plugin.t("Punkt"), list(indexed), 0, False)
        if accepted:
            self.section_alignments[self.item_key(item)] = indexed[title]
            self.mode.setCurrentIndex(self.mode.findData("correlation"))
            self._display_changed()

    def _clear_section_alignment(self):
        self.section_alignments = {}
        self._display_changed()

    def _show_section_record(self, key, track, record):
        item = next((row for row in self.items if self.item_key(row) == key), {})
        if not isinstance(record, dict):
            return
        box = QMessageBox(self)
        box.setWindowTitle(self.plugin.t(TRACK_LABELS.get(track, "Läbilõige")))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(str(item.get("name") or key))
        fields = (
            ("analyte", "Isotoop"), ("value", "Väärtus"), ("unit", "Ühik"),
            ("reference", "Võrdlusskaala"), ("uncertainty", "Mõõtemääramatus"),
            ("depth", "Sügavus / kõrgus (m)"), ("name", "Nimi"),
            ("scheme", "Skeem"), ("sample_ref", "Proovi viide"), ("source_ref", "Allika viide"),
            ("z_suht_ylemine", "Algus"), ("z_suht_alumine", "Lõpp"),
            ("indeks", "Indeks"), ("litoloogia", "Litoloogia"), ("note", "Märkus"),
            ("taxon", "Takson"), ("zone", "Biotsoon"), ("text", "Märkus"),
            ("top", "Vahemiku algus (m)"), ("bottom", "Vahemiku lõpp (m)"),
            ("attachment_name", "Manus"),
        )
        box.setInformativeText("\n".join(
            f"{self.plugin.t(label)}: {record[field]}"
            for field, label in fields if record.get(field) not in (None, "")
        ))
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addButton(QMessageBox.StandardButton.Close)
        original = box.addButton(self.plugin.t("Ava valitud tulba algkirje"), QMessageBox.ButtonRole.ActionRole)
        original.setEnabled(bool(item.get("source_ref") or section_source_ref(item)))
        link = next((QUrl(str(record[field])) for field in ("sample_ref", "source_ref")
                     if record.get(field) and QUrl(str(record[field])).scheme() in {"https", "http"}
                     and QUrl(str(record[field])).host()), None)
        reference = box.addButton(self.plugin.t("Ava mõõtmise viide"), QMessageBox.ButtonRole.ActionRole) if link else None
        attachment = (
            box.addButton(self.plugin.t("Ava kohalik manus…"), QMessageBox.ButtonRole.ActionRole)
            if track == "outcrop_observations" and self.workspace and record.get("attachment") else None
        )
        box.exec()
        if box.clickedButton() is original:
            self._open_section_source(key)
        elif reference is not None and box.clickedButton() is reference:
            QDesktopServices.openUrl(link)
        elif attachment is not None and box.clickedButton() is attachment:
            try:
                path = self.workspace.attachment_path(record["attachment"])
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            except SectionWorkspaceError as error:
                self._workspace_error(error)
