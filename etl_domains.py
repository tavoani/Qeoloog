"""Offline ETL code/label choices derived from the supplied template catalog."""

from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import re


_INTEGER_CELL = re.compile(r"[+-]?[0-9]{1,20}(?:[.,]0{1,10})?")
_CATALOG = Path(__file__).with_name("etl_domain_catalog.json")


def normalize_domain_code(value):
    """Normalize a lookup key only; never replace or write the input value."""
    if value is None:
        return ""
    key = str(value).strip().casefold()
    if _INTEGER_CELL.fullmatch(key):
        return str(int(Decimal(key.replace(",", "."))))
    return key


def _normalized_label(value):
    return " ".join(str(value).split()).casefold() if value is not None else ""


def _union(groups):
    """Drop options whose code has conflicting labels outside a known subtype."""
    choices = {}
    conflicts = set()
    for group in groups:
        for code, label in group:
            key = normalize_domain_code(code)
            if key in choices and choices[key][1] != label:
                conflicts.add(key)
            else:
                choices.setdefault(key, (code, label))
    return tuple(option for key, option in choices.items() if key not in conflicts)


@lru_cache(maxsize=1)
def _read_catalog():
    with _CATALOG.open(encoding="utf-8") as handle:
        content = json.load(handle)
    if content["schema"] != 1:
        raise ValueError("Unsupported ETL domain catalog schema")
    domains = {}
    for identity, domain in content["domains"].items():
        if "depends_on" in domain:
            groups = {key: tuple(map(tuple, options)) for key, options in domain["groups"].items()}
            domains[identity] = domain["depends_on"], groups, _union(groups.values())
        else:
            domains[identity] = None, {}, tuple(map(tuple, domain["choices"]))
    fields = {
        (sheet.casefold(), field.casefold()): domains[identity]
        for sheet, values in content["fields"].items() for field, identity in values.items()
    }
    return fields


def _field(sheet, field):
    return _read_catalog().get((str(sheet).casefold(), str(field).casefold()))


def has_domain(sheet, field):
    """Return whether this exact workbook field has a shipped classifier."""
    return _field(sheet, field) is not None


def domain_dependencies(sheet, field):
    """Return only template-confirmed row fields that change the choices."""
    domain = _field(sheet, field)
    return (domain[0],) if domain and domain[0] else ()


@lru_cache(maxsize=128)
def _lookup(options):
    codes, labels = {}, {}
    for option in options:
        code, label = normalize_domain_code(option[0]), _normalized_label(option[1])
        codes[code] = None if code in codes else option
        labels[label] = None if label in labels else option
    return codes, labels


def _match(options, value):
    key = normalize_domain_code(value)
    if not key:
        return None
    codes, labels = _lookup(options)
    return codes[key] if key in codes else labels.get(_normalized_label(value))


def domain_options(sheet, field, row=None, attrs=None):
    """Exact template codes and labels in source order, optionally by subtype.

    A supplied row determines its own subtype, even when it is blank, because
    the row's geology may differ from the object's general category. Use
    object attributes only when no row was supplied. With no known subtype
    the choices are the unambiguous union.
    """
    domain = _field(sheet, field)
    if domain is None:
        return ()
    parent, groups, choices = domain
    if not parent:
        return choices
    candidates = row if row is not None else attrs
    raw = (candidates or {}).get(parent)
    code = normalize_domain_code(raw)
    if code not in groups:
        parent_domain = _field(sheet, parent)
        if parent_domain:
            matched = _match(parent_domain[2], raw)
            if matched:
                code = normalize_domain_code(matched[0])
    return groups.get(code, choices)


def domain_match(sheet, field, raw, row=None, attrs=None):
    """Return the exact matching option or None for unknown/ambiguous values."""
    return _match(domain_options(sheet, field, row, attrs), raw)
