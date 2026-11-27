"""Independent local detail view; never replaces the live detail state."""

from qgis.PyQt.QtCore import QSignalBlocker, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget,
)

from .i18n import field_label
from .local_object_sources import local_cross_section, public_object_ref

_RELATED_TITLES = {
    'geol_vahekiht_mall': 'Vahekihid', 'geol_mineraal_mall': 'Mineraalid',
    'geol_fos_det_mall': 'Fossiilid ja detriit', 'nahtus_mall': 'Nähtused',
    'mall_seeria': 'Prooviseeriad', 'mall_proov': 'Proovid',
    'mall_seos': 'Prooviseosed', 'mall_mootmine': 'Analüüsid',
    'mall_viitamine': 'Analüüside viited', 'mall_tulem': 'Analüüsitulemused',
}
_LAB_DEFAULTS = {
    'mall_seeria': ('ID_ajutine', 'nimi', 'protokolli_nr', 'markus'),
    'mall_proov': ('ID_ajutine', 'proov_tahis_alg', 'z_suht_ylemine', 'z_suht_alumine', 'proov_tyyp', 'eesmark', 'staatus'),
    'mall_seos': ('ID_ajutine', 'algne_id', 'markus'),
    'mall_mootmine': ('ID_ajutine', 'proov_id', 'analyys_kood', 'analyys_meetod', 'labor', 'kuupaev'),
    'mall_viitamine': ('ID_ajutine', 'egf_nr', 'kirjandus_viit', 'markus'),
    'mall_tulem': ('ID_ajutine', 'analyys_naitaja', 'erimark', 'tulem', 'yhik', 'alumine_maaramispiir', 'ylemine_maaramispiir'),
}
_LAB_DOMAIN_TABLES = {'mall_proov': 18, 'mall_mootmine': 3, 'mall_tulem': 4}

class LocalObjectDetailMixin:
    def _init_local_detail_controls(self, outer):
        t = self.plugin.t
        toolbar = QWidget()
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(2, 0, 2, 0)
        self.local_version = QComboBox()
        self.local_version.setObjectName('qeoloogLocalObjectVersion')
        self.local_version.addItem(t('Originaal'), 'original')
        self.local_version.addItem(t('Muudetud'), 'local')
        self.local_version.currentIndexChanged.connect(self._switch_local_detail)
        row.addWidget(self.local_version)
        self.copy_local = QPushButton(t('Kopeeri kohalikuks'))
        self.copy_local.clicked.connect(lambda: self.plugin.copy_current_local_object())
        row.addWidget(self.copy_local)
        self.edit_local = QPushButton(t('Muuda kohalikku objekti'))
        self.edit_local.clicked.connect(self._manage_local_detail)
        row.addWidget(self.edit_local)
        self.local_lithology = QPushButton(t('Litotulp…'))
        self.local_lithology.clicked.connect(self._open_local_lithology)
        row.addWidget(self.local_lithology)
        row.addStretch(1)
        self.local_detail_toolbar = toolbar
        toolbar.hide()
        outer.addWidget(toolbar)
        self.local_detail_stack = QStackedWidget()
        self.local_detail_tabs = QTabWidget()
        self._local_detail_record = None
        self._local_detail_standalone = False
        self._local_detail_ref = None
        self._local_profile_status = ''
        self._local_detail_profile = None
        self._original_detail_title = ''
        outer.addWidget(self.local_detail_stack)

    def _local_detail_is_active(self):
        return self._local_detail_record is not None and (
            self._local_detail_standalone or self.local_version.currentData() == 'local'
        )

    def _manage_local_detail(self):
        if self._local_detail_record:
            self.plugin.open_local_object_list(self._local_detail_record['id'], edit=True)

    def _open_local_lithology(self):
        if self._local_detail_is_active():
            self.plugin.open_local_lithology_report(
                self._local_record_for_display(), editable=not self._showing_captured_original(),
            )

    def _begin_original_detail(self, role, attributes):
        ref = public_object_ref(role, attributes)
        keep_local = ref and ref == self._local_detail_ref and self._local_detail_is_active()
        if not keep_local:
            with QSignalBlocker(self.local_version):
                self.local_version.setCurrentIndex(0)
        self._local_detail_standalone = False
        self._local_detail_ref = ref
        self._local_profile_status = 'pending' if ref else ''
        self._local_profile_source = ''
        self.refresh_local_detail_match()

    def refresh_local_detail_match(self):
        """On workspace switch or save, re-resolve only the selected source ID."""
        if self._local_detail_standalone:
            getter = getattr(self.plugin, 'load_local_object', None)
            record = getter(self._local_detail_record['id']) if getter and self._local_detail_record else None
            if record is None:
                self._local_detail_standalone = False
                self._local_detail_ref = None
                self._local_detail_record = None
                self._current_detail_name = ''
                self._current_detail_attributes = {}
                self._original_detail_title = self.plugin.t('Klõpsa kaardil puuraugul või vaatluspunktil.')
                self.local_detail_stack.setVisible(False)
            else:
                self._set_local_detail_record(record)
                return
        resolver = getattr(self.plugin, 'find_local_object', None)
        record = resolver(self._local_detail_ref) if resolver and self._local_detail_ref else None
        self._set_local_detail_record(record)

    def _set_local_detail_record(self, record):
        if record != self._local_detail_record and self._local_detail_profile is not None:
            index = self.local_detail_tabs.currentIndex()
            self._local_detail_record = record
            self._fill_local_detail_tabs()
            self.local_detail_tabs.setCurrentIndex(max(0, min(index, self.local_detail_tabs.count() - 1)))
        else:
            self._local_detail_record = record
        self._switch_local_detail()

    def show_standalone_local_detail(self, record):
        if self._detail_dialog is not None and self._detail_dialog.isVisible():
            self._detail_dialog.close()
        self.local_detail_stack.setVisible(True)
        self._local_detail_standalone = True
        self._local_detail_ref = None
        self._local_profile_status = ''
        with QSignalBlocker(self.local_version):
            self.local_version.setCurrentIndex(1)
        self._set_local_detail_record(record)

    def _showing_captured_original(self):
        return bool(self._local_detail_standalone and self.local_version.currentData() == 'original'
                    and (self._local_detail_record or {}).get('source_original'))

    def _local_record_for_display(self):
        record = self._local_detail_record or {}
        if self._showing_captured_original():
            original = {**record, 'related': {}, **record['source_original']}
            original.pop('basement_measurements', None)
            return original
        return record

    def _switch_local_detail(self, *_):
        if not hasattr(self, '_current_detail_attributes'):
            return
        local = self._local_detail_is_active()
        original = not self._local_detail_standalone
        captured = self._showing_captured_original()
        self.local_version.setItemText(0, self.plugin.t('Originaal' if original else 'Originaal (salvestatud)'))
        self.local_version.setVisible(bool(self._local_detail_record and (original or self._local_detail_record.get('source_original'))))
        self.copy_local.setVisible(bool(original and self._local_detail_ref and not self._local_detail_record))
        self.edit_local.setVisible(local and not captured)
        self.local_lithology.setVisible(local)
        self.local_detail_toolbar.setVisible(bool(self._local_detail_ref or self._local_detail_standalone))
        showing = self.local_detail_stack.currentWidget()
        if local:
            if self._local_detail_standalone and self._local_detail_profile is not None:
                idx = self.local_detail_tabs.currentIndex()
                self._fill_local_detail_tabs()
                self.local_detail_tabs.setCurrentIndex(max(0, min(idx, self.local_detail_tabs.count() - 1)))
            if showing is not self.local_detail_tabs and self.tabs.currentIndex() in (0, 1):
                self.local_detail_tabs.setCurrentIndex(self.tabs.currentIndex())
            self.local_detail_stack.setCurrentWidget(self.local_detail_tabs)
            record = self._local_record_for_display()
            name = local_cross_section(record)['name']
            suffix = self.plugin.t('Kohalik')
            if captured:
                stamp = str(record.get('captured_at') or '')[:10]
                suffix = f"{self.plugin.t('Salvestatud originaal')} {stamp}".strip()
            self.header.setText(f"{name} — {suffix}")
        else:
            if showing is self.local_detail_tabs and self.local_detail_tabs.currentIndex() in (0, 1):
                idx = self.local_detail_tabs.currentIndex()
                if self.tabs.isTabVisible(idx):
                    self.tabs.setCurrentIndex(idx)
            self.local_detail_stack.setCurrentWidget(self.tabs)
            if self._original_detail_title:
                self.header.setText(self._original_detail_title)
        self.detail_view_button.setVisible(bool(local or self._current_detail_name))
        position = self._local_location_attributes() if local else self._current_detail_attributes
        self.go_to_location_button.setVisible(bool(local or self._current_detail_name))
        self.go_to_location_button.setEnabled(self.plugin.detail_location(position) is not None)
        self.sync_cross_section_button()
        if self._detail_dialog is not None and self._detail_dialog.isVisible():
            self._detail_dialog.refresh_data()

    def _local_location_attributes(self):
        attrs = self._local_record_for_display().get('attributes') or {}
        return {'_qeoloog_x_3301': attrs.get('geom_x'), '_qeoloog_y_3301': attrs.get('geom_y')}

    def _fill_local_detail_tabs(self):
        self._local_detail_profile.setParent(self.local_detail_tabs)
        while self.local_detail_tabs.count():
            widget = self.local_detail_tabs.widget(0)
            self.local_detail_tabs.removeTab(0)
            if widget is not self._local_detail_profile:
                widget.deleteLater()
        if not self._local_detail_record:
            return
        snapshot = self._local_detail_snapshot()
        for i, dataset in enumerate(snapshot['tables']):
            table = self._table(dataset['headers'])
            self._fill_rows(table, dataset['rows'])
            if i == 1:
                page = QWidget()
                layout = QVBoxLayout(page)
                profile = self._local_detail_profile
                profile.set_core_applicable(False)
                record = self._local_record_for_display()
                profile.set_total_depth(local_cross_section(record)['depth'])
                profile.set_units(record.get('units') or [])
                layout.addWidget(profile, 2)
                profile.show()
                layout.addWidget(table, 1)
                self.local_detail_tabs.addTab(page, self.plugin.t('Läbilõige'))
            else:
                self.local_detail_tabs.addTab(table, dataset['title'])

    def _local_detail_snapshot(self):
        t = self.plugin.t
        lang = getattr(self.plugin, 'language', 'et')
        record = self._local_record_for_display()
        attrs = record.get('attributes') or {}
        units = list(record.get('units') or ())
        labelled = [(field_label(key, lang), value) for key, value in attrs.items()
                    if not key.startswith('_') and value not in (None, '')]
        if record.get('source_ref'):
            ref = record['source_ref']
            labelled.append((t('Allikas'), f"{ref['source']} · {ref['id']}"))
        geol = ('z_suht_ylemine', 'z_suht_alumine', 'indeks', 'kihistik', 'genees', 'litoloogia')
        datasets = [
            {'key': 'local_overview', 'title': t('Üldandmed'), 'allow_extra_columns': False,
             'headers': (t('Väli'), t('Väärtus')), 'column_keys': ('field', 'value'), 'rows': labelled},
            {'key': 'local_geology', 'title': t('Geoloogilised üksused'),
             'headers': tuple(t(key) for key in ('Ülemine', 'Alumine', 'Indeks', 'Kihistik', 'Genees', 'Litoloogia')),
             'column_keys': geol, 'rows': [[row.get(key) for key in geol] for row in units], 'records': units},
        ]
        for name, rows in (record.get('related') or {}).items():
            if rows:
                keys = _LAB_DEFAULTS.get(name) or list(dict.fromkeys(
                    key for row in rows for key in row if not key.startswith('_')
                ))
                table_id = _LAB_DOMAIN_TABLES.get(name)
                domains = getattr(self.plugin, 'egt_domains', {})
                def display(row, key):
                    value = row.get(key)
                    return domains.get((table_id, key), {}).get(str(value), value) if table_id else value
                datasets.append({'key': f'local_{name}', 'title': t(_RELATED_TITLES.get(name, name)),
                                 'headers': [field_label(k, lang) for k in keys],
                                 'column_keys': keys,
                                 'rows': [[display(row, k) for k in keys] for row in rows],
                                 'records': [{**row, '_qeoloog_table_id': table_id} for row in rows],
                                 'allow_extra_columns': bool(name in _LAB_DEFAULTS)})
        name = str(attrs.get('nimi') or attrs.get('ID_ajutine') or record.get('id') or '')
        return {'name': name, 'heading': f"{name} — {t('Kohalik')}", 'tables': datasets}

    def _displayed_detail_snapshot(self):
        return self._local_detail_snapshot() if self._local_detail_is_active() else self.detail_view_snapshot()
