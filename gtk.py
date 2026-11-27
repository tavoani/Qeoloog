"""Pure helpers for public Geological Survey of Finland services."""

from html.parser import HTMLParser


class _FeatureInfoTableParser(HTMLParser):
    """Collect cells from WMS GetFeatureInfo HTML without rendering HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None
        self._cell_kind = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []
            self._cell_kind = tag
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag in {"th", "td"} and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append((self._cell_kind, value))
            self._cell = None
            self._cell_kind = ""
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def parse_feature_info_html(payload):
    """Return attribute dictionaries from common WMS feature-info tables.

    GTK's ArcGIS WMS services return one header row followed by one or more
    value rows.  The alternative two-cell key/value layout is accepted too so
    this remains useful if the service changes its HTML template.
    """
    if not payload:
        return []
    parser = _FeatureInfoTableParser()
    try:
        parser.feed(str(payload))
        parser.close()
    except (ValueError, TypeError):
        return []

    features = []
    for table in parser.tables:
        if not table:
            continue
        header = [value for kind, value in table[0] if kind == "th"]
        if header:
            for row in table[1:]:
                values = [value for _kind, value in row]
                if values:
                    features.append(dict(zip(header, values)))
            continue
        pairs = {}
        for row in table:
            values = [value for _kind, value in row]
            if len(values) >= 2 and values[0]:
                pairs[values[0]] = values[1]
        if pairs:
            features.append(pairs)
    return features

