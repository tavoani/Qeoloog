"""Apply the archived Faktika geology rules to offline ETL10 choices."""

from .etl_domains import domain_match, domain_options
from .faktika import COMPOUND_INDEX, hierarchical_coded_values


UNIT_SHEET = "geol_yksus_mall"
FORMATION_PARENTS = {
    "kihistik": "indeks",
    "liityksus_kihistik_ylemine": "liityksus_indeks_ylemine",
    "liityksus_kihistik_alumine": "liityksus_indeks_alumine",
}
COMPOUND_COMPONENTS = frozenset((
    "liityksus_indeks_ylemine", "liityksus_indeks_alumine",
))
CATEGORY_FIELDS = {"genees": 1, "kivim_nimetus": 2}
UNIT_RULE_FIELDS = frozenset((*FORMATION_PARENTS, *COMPOUND_COMPONENTS, *CATEGORY_FIELDS))
UNIT_RULE_PARENTS = frozenset(("yksus_kood", *FORMATION_PARENTS.values()))


def unit_field_options(field, row):
    """Return applicable code/label pairs for a rule-controlled cell."""
    if field in CATEGORY_FIELDS:
        category = domain_match(UNIT_SHEET, "yksus_kood", row.get("yksus_kood"))
        if not category or category[0] != CATEGORY_FIELDS[field]:
            return ()
    compound = domain_match(UNIT_SHEET, "indeks", row.get("indeks"))
    is_compound = compound is not None and compound[0] == COMPOUND_INDEX
    if field in COMPOUND_COMPONENTS:
        if not is_compound:
            return ()
        options = domain_options(UNIT_SHEET, field, row=row)
        return tuple(option for option in options if option[0] != COMPOUND_INDEX)
    if field in FORMATION_PARENTS:
        parent_field = FORMATION_PARENTS[field]
        if is_compound != (parent_field in COMPOUND_COMPONENTS):
            return ()
        parent = domain_match(UNIT_SHEET, parent_field, row.get(parent_field), row=row)
        if not parent or parent[0] == COMPOUND_INDEX:
            return ()
        options = domain_options(UNIT_SHEET, field, row=row)
        return tuple(hierarchical_coded_values(options, parent[0]))
    return domain_options(UNIT_SHEET, field, row=row)
