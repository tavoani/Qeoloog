"""Paginated, scaled lithology log for local Qeoloog records (native Qt)."""

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from math import ceil, floor, isfinite
from pathlib import Path
from statistics import median
from tempfile import NamedTemporaryFile

from qgis.PyQt.QtCore import QMarginsF, QPointF, QRect, QRectF, QSize, QSizeF, Qt
from qgis.PyQt.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize,
    QPainter, QPainterPath, QPdfWriter, QPen, QPolygonF,
)
from qgis.PyQt.QtSvg import QSvgGenerator

from . import section_tracks as tracks
from .etl_domains import domain_match
from .etl_lab import lab_key


POINTS_PER_MM = 72.0 / 25.4
MM_PER_METRE = 1000.0
A4 = (210 * POINTS_PER_MM, 297 * POINTS_PER_MM)
MARGIN = 28
HEADER_Y = 23
HEADER_H = 100
GOING = 8
ROW_H = 11
MAX_PAGES = 180
MAX_GAMMA = 250_000
INK = QColor("#172830")
MUTED = QColor("#475861")
LINE = QColor("#a9b4b9")
FAINT = QColor("#e8edef")
TEAL = QColor("#26645a")
BLUE = QColor("#24558e")
PURPLE = QColor("#854b6c")
PAPER = QColor("#ffffff")

ET_EN = {
    "Litotulp": "Lithology log",
    "Sügavus": "Depth",
    "Kõrgus": "Height",
    "Mõõtkava": "Scale",
    "Vahemik": "Interval",
    "Tulp": "Log",
    "Indeks": "Index",
    "Litoloogia": "Lithology",
    "Proovid": "Samples",
    "Analüüsid": "Analyses",
    "Kirjeldus": "Description",
    "Kirjelduste jätk": "Descriptions continued",
    "Sügavuseta kirjed": "Records without depths",
    "Pikkus": "Length",
    "Vertikaalne ulatus": "Vertical extent",
    "Valmis": "Completed",
    "Maapind": "Ground elevation",
    "Algkõrgus": "Base elevation",
    "Puurija": "Driller",
    "Koostas": "Prepared by",
    "Kuupäev": "Date",
    "Aruanne": "Report",
    "Teadmata": "Unknown",
    "Proov": "Sample",
    "Analüüs": "Analysis",
    "Paksus": "Thickness",
    "Väljatulek": "Recovery",
    "Koordinaadid": "Coordinates",
    "Gamma": "Gamma",
    "Andmelünk": "Data gap",
    "Punktkirje": "Point record",
    "Piirid vastuolus": "Reversed limits",
    "Alumine piir puudub": "Bottom limit missing",
    "Ülemine piir puudub": "Top limit missing",
    "Sügavus teadmata": "Depth unknown",
    "Kõrgus teadmata": "Height unknown",
    "Proovi sügavus": "Sample depth",
    "Karbonaatkivim": "Carbonate rock",
    "Liiv / liivakivi": "Sand / sandstone",
    "Savi / aleuriit": "Clay / silt",
    "Kruus / konglomeraat": "Gravel / conglomerate",
    "Orgaaniline sete": "Organic deposit",
    "Muu / määramata litoloogia": "Other / unspecified lithology",
}
PATTERN_SHORT = {
    "carbonate": ("Karbonaat", "Carbonate"),
    "sand": ("Liiv / lk", "Sand / ss"),
    "mud": ("Savi / aleuriit", "Clay / silt"),
    "gravel": ("Kruus", "Gravel"),
    "organic": ("Orgaaniline", "Organic"),
    "till": ("Moreen", "Till"),
    "other": ("Muu", "Other"),
}
DETAIL_FIELDS = (("kivim_nimetus", "Rock name"), ("genees", "Genesis"),
                 ("kihistik", "Member"), ("terasuurus", "Grain size"),
                 ("struktuur", "Structure"), ("tekstuur", "Texture"),
                 ("tekstuur_taiend", "Texture detail"), ("tekstuur_taiendav", "Texture detail"),
                 ("varvus_kirjeldus", "Colour"), ("alumine_kontaktpind", "Lower contact"))
UNKNOWN_LABELS = {
    "", "997", "998", "teadmata", "määramata", "ei kohaldu", "unknown",
    "undetermined", "not applicable", "n/a",
}


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    return tracks.finite_number(value)


def _text(value):
    if value is None:
        return ""
    return " ".join(str(value).split()) if isinstance(value, (int, float)) else str(value).strip()


def _get(row, *fields):
    for key in fields:
        value = row.get(key)
        if value is not None and value != "" and not isinstance(value, (dict, list, tuple)):
            return value
    return ""


def _code_or_label(row, *fields):
    fallback = ""
    for field in fields:
        for key in (f"{field}_label", f"klassif_{field}", field):
            value = _text(_get(row, key))
            if value and _number(value) is None:
                return value
            if value and not fallback:
                fallback = value
    return fallback


def _unit_label(row, field):
    text = _code_or_label(row, field)
    if _number(text) is not None:
        match = domain_match("geol_yksus_mall", field, text, row=row)
        match = match or domain_match("geol_yksus_mall", field, text)
        if match:
            return match[1]
    return text


def _index(row):
    code = _unit_label(row, "indeks") or _code_or_label(row, "indeks_orig")
    upper = _unit_label(row, "liityksus_indeks_ylemine")
    lower = _unit_label(row, "liityksus_indeks_alumine")
    invalid = {"", "997", "998", "ei kohaldu", "teadmata", "unknown", "not applicable"}
    ends = [v for v in (upper, lower) if v.casefold() not in invalid]
    if (code.casefold() in {"9999999", "liitüksus", "composite unit"} or not code and len(ends) == 2) and ends:
        return "-".join(dict.fromkeys(ends))
    return code


def _font(size=9, bold=False):
    font = QFont("Sans Serif")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def _wrap(text, width, font):
    """Keep the entire text, including very long tokens and paragraph breaks."""
    metrics = QFontMetricsF(font)
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = ""
        for word in words:
            candidate = f"{line} {word}" if line else word
            if metrics.horizontalAdvance(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            while metrics.horizontalAdvance(word) > width:
                left, right = 1, len(word)
                while left < right:
                    center = (left + right + 1) // 2
                    if metrics.horizontalAdvance(word[:center]) <= width:
                        left = center
                    else:
                        right = center - 1
                lines.append(word[:left])
                word = word[left:]
            line = word
        if line:
            lines.append(line)
    return lines


@dataclass
class Entry:
    kind: str
    top: float | None
    base: float | None
    row: dict
    label: str
    status: str = ""
    index: str = ""
    lithology: str = ""
    pattern: str = "other"
    note: str = ""
    xrd: tuple = ()

    @property
    def point(self):
        return self.top is not None and self.top == self.base


@dataclass
class Annotation:
    kind: str
    anchor: float | None
    x: float | None
    y: float
    lines: list


@dataclass
class Page:
    start: float
    end: float
    kind: str = "chart"
    entries: tuple = ()
    notes: tuple = ()


def _bounds(row):
    top = _number(_get(row, "z_suht_ylemine", "top", "depth_top", "depth_from"))
    base = _number(_get(row, "z_suht_alumine", "bottom", "depth_bottom", "depth_to"))
    if top is None and base is None:
        top = base = _number(_get(row, "depth", "position", "sygavus"))
    if top is None and base is None:
        return None, None, ""
    if top is None:
        return base, base, "Ülemine piir puudub"
    if base is None:
        return top, top, "Alumine piir puudub"
    if base < top:
        # Do not invent a stratigraphic interval from reversed values.
        return None, None, "Piirid vastuolus"
    return top, base, ""


def _has_bounds(row):
    return bool(_text(_get(
        row, "z_suht_ylemine", "top", "depth_top", "depth_from",
        "z_suht_alumine", "bottom", "depth_bottom", "depth_to",
        "depth", "position", "sygavus",
    )))


def _gamma_points(options):
    points = []
    for row in options.get("gamma") or ():
        if isinstance(row, dict):
            depth, value = row.get("depth"), row.get("value")
        elif isinstance(row, (tuple, list)) and len(row) >= 2:
            depth, value = row[:2]
        else:
            continue
        depth = _number(depth)
        if depth is not None:
            points.append((depth, _number(value)))
            if len(points) > MAX_GAMMA:
                raise ValueError("Too many gamma readings")
    return sorted(points, key=lambda row: row[0])


def _annotation_text(row, *fields):
    return "; ".join(dict.fromkeys(
        value for key in fields if (value := _text(_get(row, key)))
    ))


def _tables(related, *names):
    seen = set()
    for name in names:
        for row in related.get(name) or ():
            if isinstance(row, dict):
                key = id(row)
                if key not in seen:
                    seen.add(key)
                    yield row


def _xrd_parts(row, results, interval):
    """Use the verified ETL8 XRD (480) and percent (1) classifications only."""
    method = _code_or_label(row, "analyys_meetod").casefold()
    if (lab_key(row.get("analyys_meetod")) != "480" and method not in {
        "xrd", "x-ray diffraction", "röntgendifraktsioon",
    }):
        return ()
    parts = {}
    for result in results:
        unit = _code_or_label(result, "yhik").casefold()
        if lab_key(result.get("yhik")) != "1" and unit not in {"%", "protsent", "percent"}:
            continue
        condition = _code_or_label(result, "erimark").casefold()
        if condition and condition not in {"998", "ei kohaldu", "not applicable", "="}:
            continue  # e.g. detection limit, not a measured fraction
        name = _code_or_label(result, "analyys_naitaja")
        value = _number(_get(result, "tulem", "value"))
        if not name or name.casefold() in UNKNOWN_LABELS or value is None or not 0 <= value <= 100:
            continue
        if _has_bounds(result) and _bounds(result)[:2] != interval:
            return ()  # quantities from different horizons cannot form one stack
        if name in parts:
            return ()  # repeated mineral rows are not safe to add together
        parts[name] = value
    if sum(parts.values()) > 100.000001:
        return ()
    return tuple(sorted(parts.items()))


class LithologyReport:
    custom_paper = False

    def __init__(self, record, start, end, scale, language, options):
        self.en = language == "en"
        self.attrs = record.get("attributes") or record
        self.options = options
        self.size = A4[::-1] if options.get("landscape") else A4
        self.axis = record.get("axis") or self.attrs.get("axis") or "depth"
        self.axis_title = "Kõrgus" if self.axis == "height" else "Sügavus"
        self.scale = _number(scale)
        if self.scale is None or self.scale <= 0:
            raise ValueError(self._bi("Mõõtkava peab olema positiivne", "Scale must be positive"))
        self.per_m = MM_PER_METRE * POINTS_PER_MM / self.scale
        self.entries = self._entries(record)
        self.gamma = _gamma_points(options)
        self._gamma_depths = [depth for depth, value in self.gamma]
        self.depth_min = _number(start)
        self.depth_max = _number(end)
        data_min, data_max = self._automatic_depth_range()
        length = _number(_get(self.attrs, "pikkus", "depth", "length"))
        if self.depth_min is None:
            self.depth_min = data_min
        if self.depth_max is None:
            self.depth_max = max(data_max, 0 if length is None else length)
            if self.depth_max <= self.depth_min:
                self.depth_max = self.depth_min + 1
        if (not isfinite(self.per_m) or self.per_m <= 0
                or not isfinite(self.depth_max - self.depth_min)
                or self.depth_max <= self.depth_min):
            raise ValueError(self._bi("Vigane sügavusvahemik", "Invalid depth range"))
        self.title = _text(_get(self.attrs, "nimi", "name", "title")) or self.t("Teadmata")
        self.gamma_unit = " ".join(_text(options.get("gamma_unit")).split())[:54]
        self.gamma_range, self.gamma_gap = self._gamma_extent()
        minerals = sorted({
            name for entry in self.entries
            if entry.xrd and entry.top <= self.depth_max and entry.base >= self.depth_min
            for name, value in entry.xrd if value > 0
        })
        self.xrd_colors = {
            name: QColor.fromHsv((29 + 137 * i) % 360, 153 + (i % 2) * 36, 184 + (i % 3) * 22)
            for i, name in enumerate(minerals)
        } if len(minerals) <= 30 else {}
        self._configure_layout()
        self.columns = self._columns()
        self.pages = tuple(self._paginate())
        self.page_count = len(self.pages)

    def _automatic_depth_range(self):
        data_min = min((e.top for e in self.entries if e.top is not None), default=0)
        data_max = max((e.base for e in self.entries if e.base is not None), default=0)
        return min(0, data_min), max(data_max, self._gamma_depths[-1] if self.gamma else 0)

    def _configure_layout(self):
        self.xrd_legend = self._xrd_labels() if self.xrd_colors and self.options.get("legend", True) else ()
        self.body_top = HEADER_Y + HEADER_H + GOING + (24 if self.options.get("legend", True) else 0) + 26 + len(self.xrd_legend) * 13
        self.body_bottom = self.size[1] - 48
        self.body_height = self.body_bottom - self.body_top

    def t(self, word):
        return ET_EN.get(word, word) if self.en else word

    def _bi(self, et, en):
        return en if self.en else et

    def _fmt(self, number, decimals=3):
        if number is None:
            return "—"
        if not isfinite(number):
            return "—"
        value = f"{number:.{decimals}f}".rstrip("0").rstrip(".") if decimals else f"{number:.0f}"
        if value in ("-0", ""):
            value = "0"
        return value if self.en else value.replace(".", ",")

    def _measure(self, entry):
        if entry.top is None:
            return self._bi("kõrgus teadmata", "height unknown") if self.axis_title == "Kõrgus" else self._bi("sügavus teadmata", "depth unknown")
        if entry.point:
            return self._fmt(entry.top) + " m"
        return f"{self._fmt(entry.top)}–{self._fmt(entry.base)} m"

    def _entries(self, record):
        result = []
        for row in record.get("units") or ():
            if not isinstance(row, dict):
                continue
            top, base, status = _bounds(row)
            idx = _index(row)
            litho = (_unit_label(row, "litoloogia") or _code_or_label(row, "lito", "litoloogia_orig")
                     or _unit_label(row, "kivim_nimetus"))
            pattern = tracks.lithology_pattern({"litoloogia": litho})
            if any(word in litho.casefold() for word in ("moreen", "till")):
                # Use the gravel family motif as a till visual, but label it distinctly.
                pattern = "till"
            text = _annotation_text(row, "markus", "kirjeldus", "description", "note", "lito_vabatekst")
            extras = []
            for key, title_en in DETAIL_FIELDS:
                info = _unit_label(row, key)
                if info and info != litho and info.casefold() not in UNKNOWN_LABELS:
                    extras.append(f"{self._bi(key.replace('_', ' ').capitalize(), title_en)}: {info}")
            for key, title in (("paksus", "Paksus"), ("valjatulek", "Väljatulek")):
                value = _get(row, key)
                info = _text(value)
                if info.casefold() not in UNKNOWN_LABELS:
                    number = _number(value)
                    display = self._fmt(number) if number is not None else info
                    extras.append(f"{self.t(title)}: {display}" + (" m" if key == "paksus" and number is not None else ""))
            note = "\n".join(part for part in (text, "; ".join(extras)) if part)
            result.append(Entry("unit", top, base, row, "", status, idx, litho, pattern, note))

        related = record.get("related") or {}
        samples = {}
        for row in (*_tables(related, "mall_proov", "samples"), *(record.get("samples") or ())):
            if not isinstance(row, dict):
                continue
            top, base, status = _bounds(row)
            label = _text(_get(row, "proov_tahis_alg", "tahis", "sample_number", "number", "ID_ajutine", "id"))
            for identifier in {lab_key(row.get(key)) for key in ("ID_ajutine", "globalid", "esri_globalid")} - {""}:
                samples.setdefault(identifier, []).append((top, base, status, label))
            if self.options.get("samples", True):
                note = _annotation_text(row, "kivim_nimetus", "lito_vabatekst", "markus", "description", "note")
                result.append(Entry("sample", top, base, row, label, status, note=note))

        if self.options.get("measurements", True):
            measurements = [
                row
                for row in (*_tables(related, "mall_mootmine", "measurements"), *(record.get("measurements") or ()))
                if isinstance(row, dict)
            ]
            keys = Counter(lab_key(row.get("ID_ajutine")) for row in measurements)
            by_id = {}
            for row in _tables(related, "mall_tulem"):
                identifier = lab_key(row.get("ID_ajutine"))
                if identifier and keys[identifier] == 1:
                    by_id.setdefault(identifier, []).append(row)
            for row in measurements:
                top, base, status = _bounds(row)
                label = _text(_get(row, "labor_analyys_nr", "analyys_kood_label", "analyys_kood", "number", "ID_ajutine", "id"))
                fragments = [_annotation_text(row, "analyys_meetod_label", "meetod_markus", "markus", "description", "note")]
                candidates = samples.get(lab_key(row.get("proov_id")), ())
                if top is None and not _has_bounds(row) and len(candidates) == 1:
                    sample_top, sample_base, sample_status, sample_label = candidates[0]
                    if sample_top is not None:
                        top, base, status = sample_top, sample_base, sample_status
                        source = sample_label or _text(row.get("proov_id"))
                        fragments.append(f"{self.t('Proovi sügavus')}: {source}")
                results = by_id.get(lab_key(row.get("ID_ajutine")), ())
                for item in results:
                    if (value := _text(_get(item, "tulem", "value"))):
                        indicator = _code_or_label(item, "analyys_naitaja")
                        qualifier = _code_or_label(item, "erimark")
                        qualifier = {"10": "≤", "20": "≥", "30": "≠"}.get(qualifier, qualifier)
                        if qualifier.casefold() in UNKNOWN_LABELS:
                            qualifier = ""
                        unit = _code_or_label(item, "yhik")
                        if lab_key(item.get("yhik")) == "1":
                            unit = "%"
                        fragments.append(" ".join(part for part in (indicator, qualifier + value, unit) if part))
                parts = _xrd_parts(row, results, (top, base)) if self.options.get("xrd", True) and top is not None else ()
                result.append(Entry("measurement", top, base, row, label, status, note="; ".join(filter(None, fragments)), xrd=parts))
        return sorted(result, key=lambda e: (
            e.top is None, 0 if e.top is None else e.top,
            {"unit": 0, "sample": 1, "measurement": 2}[e.kind],
        ))

    def _gamma_extent(self):
        values = [value for depth, value in self.gamma
                  if self.depth_min <= depth <= self.depth_max and value is not None]
        if not values:
            return None, None
        low, high = min(values), max(values)
        if not isfinite(high - low):
            raise ValueError(self._bi("Gammalogi väärtuste vahemik on liiga suur", "Gamma range is too large"))
        if low == high:
            delta = max(1.0, abs(low) * 0.05)
            low, high = low - delta, high + delta
        diffs = [b[0] - a[0] for a, b in zip(self.gamma, self.gamma[1:]) if b[0] > a[0]]
        gap = _number(self.options.get("gamma_max_gap"))
        if gap is None or gap <= 0:
            gap = 5 * median(diffs) if len(diffs) >= 3 else None
        return (low, high), gap

    def _columns(self):
        compact = bool(self.xrd_colors)
        plans = [
            ("axis", 47), ("column", 34), ("gamma", 62 if self.gamma_range else 0),
            ("index", 57), ("litho", 61 if compact else 66),
            ("sample", (43 if compact else 52) if any(e.kind == "sample" for e in self.entries) else 0),
            ("measurement", (47 if compact else 59) if any(e.kind == "measurement" for e in self.entries) else 0),
            ("xrd", 58 if compact else 0),
        ]
        x = MARGIN
        columns = {}
        for key, width in plans:
            if width:
                columns[key] = (x, width)
                x += width
        columns["description"] = (x, self.size[0] - x - MARGIN)
        return columns

    def _entry_lines(self, entry, width, continued=False):
        position = self._measure(entry)
        if entry.kind == "unit":
            heading = " · ".join(part for part in (position, entry.index, entry.lithology or self.t("Teadmata")) if part)
        else:
            caption = self.t("Proov" if entry.kind == "sample" else "Analüüs")
            heading = " · ".join(part for part in (position, f"{caption} {entry.label}".strip()) if part)
        if entry.status:
            heading += " · " + self.t(entry.status)
        return [(line, True) for line in _wrap(heading, width, _font(9, True))] + [
            (line, False) for line in (_wrap(entry.note, width, _font()) if entry.note else ())
        ]

    def _fit_notes(self, entries, first, last, include_continuing=False):
        x, width = self.columns["description"]
        y = self.body_top + 4.0
        notes, remainder = [], []
        # Text is drawn visually next to the correct depth when at all possible;
        # moving it vertically uses a leader. Every overflow case is paginated.
        for entry in entries:
            if entry.top < first and not entry.point and not include_continuing:
                continue  # Full labels appear on the page where the interval starts.
            anchor = self.body_top + max(0.0, min(last, entry.top) - first) * self.per_m
            lines = self._entry_lines(entry, width - 17)
            text_h = len(lines) * ROW_H
            pos = max(y, min(anchor - 3, self.body_bottom - text_h - 2))
            if pos + text_h > self.body_bottom:
                remainder.append(entry)
                continue
            origin = self.columns["column" if entry.kind == "unit" else entry.kind]
            notes.append(Annotation(entry.kind, anchor, origin[0] + origin[1], pos, lines))
            y = pos + text_h + 4
        return tuple(notes), remainder

    def _continuations(self, entries, lo, hi, unknown=False):
        width = self.size[0] - 2 * MARGIN - 16
        fragments = []
        for entry in entries:
            fragments.extend(self._entry_lines(entry, width))
            fragments.append(("", False))
        page_size = max(1, int((self.body_height - 8) // ROW_H))
        for i in range(0, len(fragments), page_size):
            kind = "unknown" if unknown else "continued"
            yield Page(lo, hi, kind, notes=tuple(fragments[i:i + page_size]))

    def _paginate(self):
        span = self.body_height / self.per_m
        depth_range = self.depth_max - self.depth_min
        pages = depth_range / span if span > 0 else float("inf")
        if not isfinite(pages) or pages > MAX_PAGES:
            raise ValueError(self._bi("Selle mõõtkava jaoks on lehti liiga palju", "Too many pages at this scale"))
        count = max(1, ceil(pages - 1e-10))
        known = [entry for entry in self.entries if entry.top is not None]
        pending = []
        for i in range(count):
            first = self.depth_min + span * i
            last = self.depth_max if i == count - 1 else self.depth_min + span * (i + 1)
            entries = [
                entry for entry in known if (entry.top < last or (i == count - 1 and entry.top == last and entry.point))
                and (entry.base > first or (entry.point and entry.top >= first))
            ]
            # If the requested range starts inside an interval, label its
            # real boundaries once on page one without changing those values.
            notes, extra = self._fit_notes(entries, first, last, include_continuing=i == 0)
            pending.append(Page(first, last, entries=tuple(entries), notes=notes))
            pending.extend(self._continuations(extra, first, last))
            if len(pending) > MAX_PAGES:
                raise ValueError(self._bi("Kirjelduste jaoks on lehti liiga palju", "Too many description pages"))
        pending.extend(self._continuations(
            [e for e in self.entries if e.top is None],
            self.depth_min, self.depth_max, unknown=True,
        ))
        if len(pending) > MAX_PAGES:
            raise ValueError(self._bi("Kirjelduste jaoks on lehti liiga palju", "Too many description pages"))
        return pending

    @staticmethod
    def _text_at(painter, x, y, text, size=9, color=INK, bold=False, width=None):
        font = _font(size, bold)
        painter.setFont(font)
        painter.setPen(color)
        text = _text(text).replace("\n", " ")
        if width is not None:
            text = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QPointF(x, y), text)

    def _fit_text(self, painter, x, y, text, size, bold, width):
        if not text:
            return
        while size > 6 and QFontMetricsF(_font(size, bold)).horizontalAdvance(text) > width:
            size -= 1
        self._text_at(painter, x, y, text, size, bold=bold, width=width)

    @staticmethod
    def _line(painter, x0, y0, x1, y1, color=LINE, width=0.55):
        painter.setPen(QPen(color, width))
        painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def _header(self, painter, page, index):
        x, y, width = MARGIN, HEADER_Y, self.size[0] - 2 * MARGIN
        self._line(painter, x, y, x + width, y, TEAL, 2.0)
        self._text_at(painter, x + 8, y + 18, self.t("Litotulp").upper(), 10, TEAL, True, width - 12)
        self._text_at(painter, x + 8, y + 42, self.title, 20, INK, True, width - 146)
        report_id = _text(_get(self.attrs, "kande_alus_nr", "gea_id", "ID_ajutine"))
        tag = f"QEOLOOG  /  {report_id}" if report_id else "QEOLOOG"
        tag_width = min(137, QFontMetricsF(_font(9, True)).horizontalAdvance(tag))
        self._text_at(painter, x + width - tag_width - 8, y + 20, tag, 9, MUTED, True, 137)
        self._line(painter, x, y + 48, x + width, y + 48)
        self._line(painter, x, y + HEADER_H, x + width, y + HEADER_H, TEAL, 0.8)
        attrs = self.attrs
        east = _number(_get(attrs, "geom_x", "x"))
        north = _number(_get(attrs, "geom_y", "y"))
        absolute_z = _number(_get(attrs, "geom_z", "elevation"))
        length = _number(_get(attrs, "pikkus", "depth", "length"))
        vertical = _number(_get(attrs, "vertikaalne_ulatus"))
        coords = (f"E {self._fmt(east, 2)}   N {self._fmt(north, 2)} m" if east is not None or north is not None else "")
        datum = _text(_get(attrs, "vertical_datum", "korgussusteem"))
        z_label = self.t("Algkõrgus" if self.axis == "height" else "Maapind")
        groups = (
            (("Alias", _get(attrs, "alias", "asukoht", "location")), ("", coords),
             (z_label, f"{self._fmt(absolute_z, 2)} m" + (f" {datum}" if datum else "") if absolute_z is not None else "")),
            ((self.t("Pikkus"), f"{self._fmt(length)} m" if length is not None else ""),
             (self.t("Vertikaalne ulatus"), f"{self._fmt(vertical)} m" if vertical is not None else ""),
             (self.t("Valmis"), _get(attrs, "valmimise_kuupaev", "completion_date"))),
            ((self.t("Puurija"), _get(attrs, "puurimisfirma_label", "klassif_puurimisfirma", "puurimisfirma")),
             (self.t("Koostas"), self.options.get("author") or _get(attrs, "isik_nimi")),
             (self.t("Kuupäev"), self.options.get("report_date", ""))),
        )
        group_starts = (x, x + 0.36 * width, x + 0.69 * width, x + width)
        for idx, group in enumerate(groups):
            gx = group_starts[idx] + 8
            gw = group_starts[idx + 1] - gx - 6
            if idx:
                self._line(painter, gx - 8, y + 48, gx - 8, y + HEADER_H)
            items = [(key, _text(value)) for key, value in group if _text(value)]
            if not items:
                continue
            for j, (key, value) in enumerate(items):
                text = f"{key}: {value}" if key else value
                self._text_at(painter, gx, y + 62 + j * 14, text, 9, MUTED, False, gw)
        bottom = self.size[1] - 32
        self._line(painter, x, bottom, x + width, bottom, TEAL, 0.8)
        measurement = f"{self.t(self.axis_title)} {self._fmt(page.start)}–{self._fmt(page.end)} m"
        label = f"{measurement}   ·   {self.t('Mõõtkava')} 1:{self._fmt(self.scale)}"
        if page.kind != "chart":
            label = self.t("Sügavuseta kirjed" if page.kind == "unknown" else "Kirjelduste jätk")
        self._text_at(painter, x + 2, bottom + 14, label, 8, MUTED, False, width - 70)
        self._text_at(painter, x + width - 46, bottom + 14, f"{index + 1} / {self.page_count}", 8, MUTED, False, 45)

    def _legend(self, painter, page):
        if not self.options.get("legend", True):
            return
        y = HEADER_Y + HEADER_H + 8
        x = MARGIN
        used = {entry.pattern for entry in page.entries if entry.kind == "unit" and not entry.point}
        entries = [
            (category, PATTERN_SHORT[category][self.en])
            for category in PATTERN_SHORT if category in used
        ] if self.options.get("patterns", True) else []
        entries += [("gap", self.t("Andmelünk")), ("point", self.t("Punktkirje"))]
        width = self.size[0] - 2 * MARGIN
        metrics = QFontMetricsF(_font(8))
        # Equal scaled caps preserve the distinction between pattern keys while
        # keeping the legend inside the printable width on crowded pages.
        natural = sum(23 + metrics.horizontalAdvance(label) for _, label in entries)
        factor = min(1, (width - 23 * len(entries)) / max(1, natural - 23 * len(entries)))
        for key, label in entries:
            rect = QRectF(x, y, 13, 10)
            if key == "point":
                self._point(painter, x, y + 5, TEAL)
            elif key == "gap":
                self._gap(painter, rect)
            else:
                tracks.draw_lithology(painter, rect, "gravel" if key == "till" else key, PAPER)
                painter.setPen(QPen(LINE, 0.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
            available = factor * metrics.horizontalAdvance(label)
            self._text_at(painter, x + 17, y + 8, label, 8, MUTED, width=available + .1)
            x += 23 + available
        for offset, row in enumerate(self.xrd_legend):
            row_y = y + 15 + 13 * offset
            if offset == 0:
                self._text_at(painter, MARGIN, row_y + 7, "XRD:", 8, MUTED, True)
            for x, name, max_width in row:
                painter.fillRect(QRectF(x, row_y, 8, 8), self.xrd_colors[name])
                self._text_at(painter, x + 11, row_y + 7, name, 8, MUTED, width=max_width)

    def _xrd_labels(self):
        rows = [[]]
        metrics = QFontMetricsF(_font(8))
        x = MARGIN + 29
        right = self.size[0] - MARGIN
        for name in self.xrd_colors:
            width = min(120, metrics.horizontalAdvance(name))
            if x + width + 16 > right:
                rows.append([])
                x = MARGIN
            rows[-1].append((x, name, width + .1))
            x += width + 19
        return rows

    def _gap(self, painter, rect):
        painter.fillRect(rect, QColor("#f3f6f7"))
        if rect.height() <= 0:
            return
        path = QPainterPath()
        width, height = rect.width(), rect.height()
        for i in range(1, ceil((width + height) / 8.0)):
            d = i * 8.0
            a, b = max(0, d - height), min(width, d)
            if b > a:
                path.moveTo(rect.left() + a, rect.top() + d - a)
                path.lineTo(rect.left() + b, rect.top() + d - b)
        painter.setPen(QPen(QColor("#cbd6d9"), 0.5))
        painter.drawPath(path)

    def _point(self, painter, x, y, color):
        painter.setPen(QPen(color, 0.6))
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([QPointF(x, y - 2.8), QPointF(x + 5, y), QPointF(x, y + 2.8)]))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _tick(self, first, last):
        choices = (0.0001, 0.0002, 0.0005, .001, .002, .005, .01, .02, .05, .1, .2, .5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000)
        raw = 27 / self.per_m
        step = next((v for v in choices if v >= raw), raw)
        first_tick = ceil(first / step - 1e-8) * step
        count = floor((last - first_tick) / step + 1e-8) + 1
        return [first_tick + i * step for i in range(min(60, max(0, count)))]

    def _chart(self, painter, page):
        top = self.body_top
        bottom = top + (page.end - page.start) * self.per_m
        left = MARGIN
        end = self.size[0] - MARGIN
        descriptions = self.columns["description"][0]
        head = top - 24

        def y(value):
            return top + (value - page.start) * self.per_m

        column_headings = {
            "axis": self.t(self.axis_title), "column": self.t("Tulp"),
            "gamma": self.t("Gamma"), "index": self.t("Indeks"), "litho": self.t("Litoloogia"),
            "sample": self.t("Proovid"), "measurement": self.t("Analüüsid"),
            "xrd": "XRD",
            "description": self.t("Kirjeldus"),
        }
        painter.fillRect(QRectF(left, head, end - left, top - head), QColor("#edf2f3"))
        for key, (x, width) in self.columns.items():
            self._fit_text(painter, x + 4, head + 10, column_headings[key], 8, True, width - 7)
            self._line(painter, x, head, x, bottom if key != "description" else max(bottom, top))
        self._line(painter, end, head, end, max(bottom, max((note.y + len(note.lines) * ROW_H for note in page.notes), default=bottom)))
        self._line(painter, left, top, end, top, LINE)
        self._line(painter, left, bottom, descriptions, bottom, LINE)
        self._line(painter, left, head, end, head, LINE)
        ruler_x = self.columns["axis"][0] + self.columns["axis"][1] - 3
        self._text_at(painter, left + 4, head + 20, f"m  ·  1:{self._fmt(self.scale)}", 7, MUTED, False, 42)
        self._line(painter, ruler_x, top, ruler_x, bottom, MUTED, 0.6)
        ticks = self._tick(page.start, page.end)
        rendered = set()
        for value in [page.start, *ticks, page.end]:
            depth_y = y(value)
            if any(abs(depth_y - pos) < 8 for pos in rendered):
                continue
            rendered.add(depth_y)
            self._line(painter, ruler_x - 5, depth_y, ruler_x, depth_y, MUTED, 0.6)
            self._line(painter, ruler_x, depth_y, descriptions, depth_y, FAINT, 0.5)
            self._text_at(painter, left + 3, depth_y + 3, self._fmt(value, 4), 8, MUTED, False, 36)

        lith_left, lith_width = self.columns["column"]
        self._gap(painter, QRectF(lith_left, top, lith_width, bottom - top))
        from .cross_section_widget import _stratigraphic_color

        for entry in page.entries:
            a, b = y(max(entry.top, page.start)), y(min(entry.base, page.end))
            if entry.kind == "unit":
                if entry.point:
                    self._point(painter, lith_left + 1, a, TEAL)
                    continue
                rect = QRectF(lith_left, a, lith_width, max(0.0, b - a))
                color = _stratigraphic_color({**entry.row, "indeks": entry.index}) if self.options.get("colors", True) else PAPER
                if self.options.get("patterns", True):
                    tracks.draw_lithology(painter, rect, "gravel" if entry.pattern == "till" else entry.pattern, color)
                else:
                    painter.fillRect(rect, color)
                self._line(painter, lith_left, a, descriptions, a, LINE, 0.6)
                self._line(painter, lith_left, b, descriptions, b, LINE, 0.6)
                if b - a >= 10:
                    for key, label in (("index", entry.index), ("litho", entry.lithology)):
                        x, w = self.columns[key]
                        self._fit_text(painter, x + 4, (a + b) / 2 + 3, label, 8, key == "index", w - 8)
            else:
                x, w = self.columns[entry.kind]
                color = TEAL if entry.kind == "sample" else PURPLE
                if entry.point:
                    self._point(painter, x + 2, a, color)
                else:
                    self._line(painter, x + 4, a, x + 4, b, color, 1.2)
                    self._line(painter, x + 2, a, x + 7, a, color, 0.6)
                    self._line(painter, x + 2, b, x + 7, b, color, 0.6)
                if b - a > 10:
                    self._text_at(painter, x + 9, (a + b) / 2 + 3, entry.label, 8, color, width=w - 12)
        if self.gamma_range:
            self._paint_gamma(painter, page, y)
        if "xrd" in self.columns:
            self._paint_xrd(painter, page, y)

        for note in page.notes:
            color = TEAL if note.kind == "sample" else PURPLE if note.kind == "measurement" else INK
            # Mark the originating track, then place the leader bend in the
            # annotation gutter instead of covering the plotted columns.
            self._line(painter, note.x - 2, note.anchor, note.x + 1, note.anchor, color, 0.8)
            self._line(painter, descriptions, note.anchor, descriptions + 7, note.y + 5, LINE, 0.55)
            self._line(painter, descriptions + 7, note.y + 5, descriptions + 10, note.y + 5, LINE, 0.55)
            for i, (line, bold) in enumerate(note.lines):
                self._text_at(painter, descriptions + 12, note.y + i * ROW_H + 8, line, 9, color, bold)

    def _paint_xrd(self, painter, page, y):
        x, width = self.columns["xrd"]
        self._text_at(painter, x + 4, self.body_top - 4, "0–100%", 7, MUTED)
        for entry in page.entries:
            if not entry.xrd:
                continue
            a, b = y(max(entry.top, page.start)), y(min(entry.base, page.end))
            last_y = y(page.end)
            h = min(last_y - self.body_top, 8, max(2.5, b - a))
            top = max(self.body_top, min(last_y - h, (a + b - h) / 2))
            left = x + 2
            w = width - 4
            for name, value in entry.xrd:
                if value <= 0:
                    continue
                component_w = w * value / 100
                painter.fillRect(QRectF(left, top, component_w, h), self.xrd_colors[name])
                left += component_w
            painter.setPen(QPen(LINE, 0.45))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(x + 2, top, w, h))

    def _paint_gamma(self, painter, page, y, *, label=True, color=BLUE):
        x, width = self.columns["gamma"]
        low, high = self.gamma_range
        if label:
            caption = f"{self._fmt(low, 1)}–{self._fmt(high, 1)}"
            if self.gamma_unit:
                caption += f" {self.gamma_unit}"
            self._text_at(painter, x + 4, self.body_top - 4, caption, 7, color, False, width - 7)

        def gamma_x(value):
            return x + 3 + (max(low, min(high, value)) - low) * (width - 6) / (high - low)

        path = QPainterPath()
        previous = None
        a = max(0, bisect_left(self._gamma_depths, page.start) - 1)
        b = bisect_right(self._gamma_depths, page.end) + 1
        for depth, value in self.gamma[a:b]:
            if depth > page.end and previous is None:
                break
            if value is None:
                previous = None
                continue
            if previous is not None:
                last_depth, last_value = previous
                diff = depth - last_depth
                if (last_depth <= page.end and depth >= page.start and diff > 0
                        and (self.gamma_gap is None or diff <= self.gamma_gap)):
                    a, b = max(page.start, last_depth), min(page.end, depth)
                    va = last_value + (value - last_value) * (a - last_depth) / diff
                    vb = last_value + (value - last_value) * (b - last_depth) / diff
                    path.moveTo(gamma_x(va), y(a))
                    path.lineTo(gamma_x(vb), y(b))
            if page.start <= depth <= page.end:
                path.addEllipse(QPointF(gamma_x(value), y(depth)), 0.37, 0.37)
            if depth > page.end:
                break
            previous = (depth, value)
        painter.setPen(QPen(color, 0.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def render_page(self, painter, index=0, rect=None):
        page = self.pages[index]
        width, height = self.size
        painter.save()
        try:
            if rect is not None:
                rect = QRectF(rect)
                scale = min(rect.width() / width, rect.height() / height)
                painter.translate(rect.x() + (rect.width() - scale * width) / 2,
                                  rect.y() + (rect.height() - scale * height) / 2)
                painter.scale(scale, scale)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.fillRect(QRectF(0, 0, width, height), PAPER)
            self._header(painter, page, index)
            if page.kind == "chart":
                self._legend(painter, page)
                self._chart(painter, page)
            else:
                title = self.t("Sügavuseta kirjed" if page.kind == "unknown" else "Kirjelduste jätk")
                self._text_at(painter, MARGIN + 8, self.body_top - 8, title, 13, TEAL, True)
                self._line(painter, MARGIN, self.body_top, width - MARGIN, self.body_top, LINE)
                for j, (line, bold) in enumerate(page.notes):
                    self._text_at(painter, MARGIN + 8, self.body_top + 12 + j * ROW_H, line, 9, INK, bold)
        finally:
            painter.restore()

    def page_image(self, index=0, *, dpi=120):
        dpi = max(36, min(300, int(dpi)))
        width, height = self.size
        pixel_w, pixel_h = ceil(width * dpi / 72), ceil(height * dpi / 72)
        image = QImage(pixel_w, pixel_h, QImage.Format.Format_RGB32)
        image.fill(PAPER)
        painter = QPainter(image)
        try:
            self.render_page(painter, index, QRectF(0, 0, pixel_w, pixel_h))
        finally:
            painter.end()
        return image


def build_lithology_report(record, *, start=None, end=None, scale=100, language="et", options=None):
    """Build a deterministic lithology log without altering the source record."""
    options = dict(options or {})
    if options.get("layout") in {"lisa5-cover", "lisa5-basement"}:
        from .lithology_report_lisa5 import Lisa5LithologyReport

        return Lisa5LithologyReport(record, start, end, scale, language, options)
    return LithologyReport(record, start, end, scale, language, options)


def _export_atomically(path, render):
    path = Path(path)
    with NamedTemporaryFile(prefix=".qeoloog-report-", suffix=path.suffix, dir=path.parent, delete=False) as temporary:
        staged = Path(temporary.name)
    try:
        render(staged)
        if staged.stat().st_size <= 0:
            raise OSError("The report export is empty")
        staged.replace(path)
        return path
    finally:
        staged.unlink(missing_ok=True)


def export_lithology_pdf(report, path):
    """Export at the report's physical paper size and scale."""
    def render(staged):
        writer = QPdfWriter(str(staged))
        writer.setTitle(report.title)
        writer.setCreator("Qeoloog")
        # At 720 dpi a logical point is exactly ten printer units.
        writer.setResolution(720)
        if report.custom_paper:
            page_size = QPageSize(QSizeF(*report.size), QPageSize.Unit.Point,
                                  "Lisa 5", QPageSize.SizeMatchPolicy.ExactMatch)
            orientation = QPageLayout.Orientation.Portrait
        else:
            page_size = QPageSize(QPageSize.PageSizeId.A4)
            orientation = QPageLayout.Orientation.Landscape if report.options.get("landscape") else QPageLayout.Orientation.Portrait
        layout = QPageLayout(page_size, orientation, QMarginsF(0, 0, 0, 0))
        layout.setMode(QPageLayout.Mode.FullPageMode)
        if not writer.setPageLayout(layout):
            raise OSError("Could not configure PDF pages")
        painter = QPainter(writer)
        if not painter.isActive():
            raise OSError("Could not create PDF")
        try:
            painter.scale(10, 10)
            for i in range(report.page_count):
                if i and not writer.newPage():
                    raise OSError("Could not create PDF page")
                report.render_page(painter, i)
        finally:
            painter.end()

    return _export_atomically(path, render)


def export_lithology_svg(report, path):
    """Export the same pages as vertically stacked editable SVG vectors."""
    def render(staged):
        width, height = report.size
        gap = 12
        total_h = (height + gap) * report.page_count - gap
        generator = QSvgGenerator()
        generator.setFileName(str(staged))
        generator.setTitle(report.title)
        generator.setDescription("Qeoloog lithology log")
        generator.setResolution(72)
        generator.setSize(QSize(ceil(width), ceil(total_h)))
        generator.setViewBox(QRect(0, 0, ceil(width), ceil(total_h)))
        painter = QPainter(generator)
        if not painter.isActive():
            raise OSError("Could not create SVG")
        try:
            painter.fillRect(QRectF(0, 0, width, total_h), FAINT)
            for i in range(report.page_count):
                report.render_page(painter, i, QRectF(0, i * (height + gap), width, height))
        finally:
            painter.end()

    return _export_atomically(path, render)
