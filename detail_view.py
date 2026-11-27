"""Pure helpers used by the read-only object detail viewer."""

import json


DETAIL_COLUMNS_SETTINGS = "Qeoloog/detail_view_columns_v1"


def technical_column_name(field):
    """Accept source attribute names, not private render/link helpers."""
    return (
        isinstance(field, str) and bool(field.strip())
        and not field.casefold().startswith(("_", "vk_"))
    )


def detail_column_candidates(dataset):
    """Collect fields from raw records for which a visible row exists."""
    if not dataset.get("allow_extra_columns", True):
        return set()
    return {
        key
        for record in (dataset.get("records") or ())[:len(dataset.get("rows") or ())]
        if isinstance(record, dict)
        for key, value in record.items()
        if technical_column_name(key)
        and value is not None and value != "" and value != [] and value != {}
    }


def detail_column_preferences(value):
    """Load saved table preferences, preserving the chosen display order."""
    try:
        value = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    def names(items):
        return list(dict.fromkeys(
            field for field in items if technical_column_name(field)
        )) if isinstance(items, list) else []

    result = {}
    for key, fields in value.items():
        if isinstance(fields, list):
            fields = {"extra": fields}
        if not isinstance(fields, dict):
            continue
        choice = {"extra": names(fields.get("extra")), "hidden": names(fields.get("hidden"))}
        if choice["extra"] or choice["hidden"]:
            result[key] = choice
    return result


def default_detail_columns(dataset):
    """Return translation-independent IDs for the legacy visible columns."""
    headers = list(dataset.get("headers") or ())
    keys = dataset.get("column_keys") or ()
    if (
        len(keys) != len(headers)
        or not all(technical_column_name(key) for key in keys)
        or len(set(keys)) != len(keys)
    ):
        keys = [f"column-{index}" for index in range(len(headers))]
    return list(zip(keys, headers))


def project_detail_columns(dataset, choice, label, cell):
    """Hide selected defaults, then append optional source fields."""
    if not choice:
        return dataset
    selected = choice.get("extra") or ()
    hidden = set(choice.get("hidden") or ())
    candidates = detail_column_candidates(dataset) if selected else set()
    fields = list(dict.fromkeys(
        field for field in selected if isinstance(field, str) and field in candidates
    ))
    columns = default_detail_columns(dataset)
    shown = [index for index, (key, _) in enumerate(columns) if key not in hidden]
    if not fields and len(shown) == len(columns):
        return dataset
    records = dataset.get("records") or ()
    rows = []
    for index, row in enumerate(dataset.get("rows") or ()):
        record = records[index] if index < len(records) else None
        base = [row[column] if column < len(row) else "" for column in shown]
        rows.append(base + [
            cell(record, field) if isinstance(record, dict) else ""
            for field in fields
        ])
    return {
        **dataset,
        "headers": [columns[index][1] for index in shown] + [label(field) for field in fields],
        "rows": rows,
        "extra_column_count": len(fields),
    }


def cell_text(value):
    """Return the copyable text from a plain or link-cell value."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return "" if value is None else str(value)


def table_to_tsv(headers, rows):
    """Serialize one detail table to a clipboard-friendly TSV string."""
    lines = ["\t".join(str(value) for value in headers)]
    lines.extend(
        "\t".join(cell_text(value) for value in row)
        for row in rows
    )
    return "\n".join(lines)


def tables_to_tsv(tables):
    """Serialize titled detail tables into one inspectable text block."""
    sections = []
    for table in tables:
        title = str(table.get("title") or "")
        content = table_to_tsv(
            table.get("headers") or (), table.get("rows") or (),
        )
        sections.append(f"[{title}]\n{content}" if title else content)
    return "\n\n".join(sections)
