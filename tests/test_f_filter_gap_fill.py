"""`pbip-forge f-filters`: gap-fill f-<Category> measures and f-All gates.

Fixture: tests/fixtures/f_filters/Roastery.SemanticModel (fictional coffee
roastery):

* facts `Store Sales` (read by `Store Revenue`, on x-Selector 1 with group
  store_m) and `Web Sales` (read by `Web Revenue`; the x row is on
  `Web Total = [Web Revenue]`, group web_m, so the category reaches Web Sales
  only through another measure);
* z-Map rows: Spend <- store_m, Spend <- web_m,
  Email Marketing Campaigns <- email_m;
* f-Filters: `f-All` with paired temp_basic / temp_alt chains gating only
  the literal "Email Marketing", a fenced `f-Spend` reading Store Sales, and
  `f-Email_Marketing`.

So `Web Sales` is uncovered (category Spend -> extend f-Spend) and the z-Map
category Spend is not yet gated in f-All.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from forge_helpers import copy_fixture, forge, lazy_module, raw_deflate_b64, tree

f_filters = lazy_module("pbip_model_forge.f_filters")

GATE = "\t\t\t        "
BASIC_SPEND = '&& IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), TRUE())'
ALT_SPEND = '|| IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), FALSE())'
ZMAP_ROWS = [["Spend", "", "store_m"], ["Spend", "", "web_m"],
             ["Email Marketing Campaigns", "", "email_m"]]


@pytest.fixture
def model(tmp_path: Path) -> Path:
    return copy_fixture("f_filters/Roastery.SemanticModel", tmp_path)


# -- fixture builders -------------------------------------------------------------
def _tables(model: Path) -> Path:
    return model / "definition" / "tables"


def _ff(model: Path) -> Path:
    return _tables(model) / "f-Filters.tmdl"


def ff_text(model: Path) -> str:
    return _ff(model).read_text(encoding="utf-8")


def fact_tmdl(name: str, kind: str = "m", source: str = 'Csv.Document(File.Contents("x.csv"))',
              extra: str = "") -> str:
    return (f"table '{name}'\n\tlineageTag: {name.lower()}\n\n"
            f"\tcolumn Amount\n\t\tdataType: double\n\t\tlineageTag: {name.lower()}-amount\n"
            "\t\tsummarizeBy: none\n\t\tsourceColumn: Amount\n\n" + extra +
            f"\tpartition '{name}' = {kind}\n\t\tmode: import\n\t\tsource =\n"
            f"\t\t\t\tlet\n\t\t\t\t    Source = {source}\n\t\t\t\tin\n\t\t\t\t    Source\n\n"
            "\tannotation PBI_ResultType = Table\n")


def add_table(model: Path, name: str, text: str | None = None) -> None:
    (_tables(model) / f"{name}.tmdl").write_text(text or fact_tmdl(name), encoding="utf-8")


def add_measure(model: Path, name: str, expr: str, hidden: bool = False,
                table: str = "Sales Measures") -> None:
    path = _tables(model) / f"{table}.tmdl"
    block = f"\tmeasure '{name}' = {expr}\n" + ("\t\tisHidden\n" if hidden else "") + \
        f"\t\tlineageTag: {name.lower().replace(' ', '-')}\n\n"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\tpartition ", block + "\tpartition ", 1), encoding="utf-8")


def set_zmap(model: Path, rows: list[list]) -> None:
    zmap = _tables(model) / "z-Map Dimension-Measure Groupings.tmdl"
    b64 = raw_deflate_b64(json.dumps(rows, separators=(",", ":")).encode())
    zmap.write_text(re.sub(r'FromText\("[^"]+"', f'FromText("{b64}"',
                           zmap.read_text(encoding="utf-8")), encoding="utf-8")


def add_selector_row(model: Path, row: str, file: str = "x-Selector 1.tmdl") -> None:
    path = _tables(model) / file
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("\n\t\t\t\t}", ",\n\t\t\t\t    " + row + "\n\t\t\t\t}", 1),
                    encoding="utf-8")


def add_gift_cards(model: Path, group: str = "gift_m", selector: bool = True) -> None:
    """Fact `Gift Cards` reached by `Card Total = [Gift Total]`, mapped to Gifting."""
    add_table(model, "Gift Cards")
    add_measure(model, "Gift Total", "SUM('Gift Cards'[Amount])")
    add_measure(model, "Card Total", "[Gift Total]")
    set_zmap(model, ZMAP_ROWS + [["Gifting", "", group]])
    if selector:
        add_selector_row(model, f'("Card Total", NAMEOF(\'Sales Measures\'[Card Total]), 2, "{group}")')


def gate_spend_in_f_all(model: Path) -> None:
    text = ff_text(model)
    text = text.replace("\t\t\tVAR temp_alt", f"{GATE}{BASIC_SPEND}\n\t\t\tVAR temp_alt", 1)
    text = text.replace("\t\t\tRETURN", f"{GATE}{ALT_SPEND}\n\t\t\tRETURN", 1)
    _ff(model).write_text(text, encoding="utf-8")


def _chain(text: str, var: str) -> str:
    m = re.search(rf"VAR {var} =.*?(?=\n\s*(?:VAR |RETURN))", text, re.S)
    assert m, f"no {var} chain"
    return m.group(0)


def _measure(text: str, name: str) -> str:
    m = re.search(rf"^\tmeasure '{re.escape(name)}' =.*?(?=^\t(?:measure|partition|annotation|column) |\Z)",
                  text, re.S | re.M)
    assert m, f"measure {name} not found"
    return m.group(0)


# -- 1. fact tables ---------------------------------------------------------------
def test_dimension_on_the_one_side_is_still_a_fact(model):
    add_table(model, "Stores")
    (model / "definition" / "relationships.tmdl").write_text(
        "relationship r1\n\tfromColumn: 'Store Sales'.'Store Id'\n\ttoColumn: Stores.Amount\n",
        encoding="utf-8")
    add_measure(model, "Store Count", "COUNTROWS('Stores')")
    assert f_filters.uncovered_facts(model) == {"Stores": [], "Web Sales": ["Spend"]}
    run = forge("f-filters", "--model", model, "--no-backups", "--dry-run")
    assert "     SKIP    Stores\n" in run.out


@pytest.mark.parametrize("name, text", [
    ("w-Helper", fact_tmdl("w-Helper")),
    ("Q-Lookup", fact_tmdl("Q-Lookup")),
    ("_Staging", fact_tmdl("_Staging")),
    ("#Totals", fact_tmdl("#Totals")),
    ("Old Measures", fact_tmdl("Old Measures")),
    ("Measure Log", fact_tmdl("Measure Log")),
    ("Entered", fact_tmdl("Entered", source="Table.FromRows(Json.Document(x))")),
    ("Inline", fact_tmdl("Inline", source='#table({"a"}, {{1}})')),
    ("Lake", fact_tmdl("Lake", kind="entity")),
    ("Calc", fact_tmdl("Calc", kind="calculated")),
    ("Time Calc", fact_tmdl("Time Calc", extra="\tcalculationGroup\n\t\tcalculationItem A = 1\n\n")),
    ("Param", fact_tmdl("Param").replace("sourceColumn: Amount",
                                         "sourceColumn: [Value1]\n\t\tgroupByColumn: x")),
    ("Empty", "table Empty\n\tpartition Empty = m\n\t\tsource = 1\n"),
])
def test_tables_that_are_not_facts(model, name, text):
    assert not f_filters.is_fact_table(name, text)
    add_table(model, name, text)
    add_measure(model, f"Reads {len(name)}", f"COUNTROWS('{name}')")
    assert name not in f_filters.uncovered_facts(model)


@pytest.mark.parametrize("name", ["Store Sales", "Measurements", "9 Box", "Sales-2024"])
def test_tables_that_are_facts(name):
    assert f_filters.is_fact_table(name, fact_tmdl(name))


# -- 2. user-facing measures ------------------------------------------------------
@pytest.mark.parametrize("name, facing", [
    ("Revenue", True), ("# Orders", True), ("^Top", True), ("z-Sort Key", True),
    ("-Helper", False), ("_Base", False), ("i-Caption", False), ("f-Spend", False),
    ("Test Revenue", False), ("Revenue TEST", False), ("Revenue (testing)", False),
    ("Contest Entries", True),
])
def test_user_facing_is_decided_by_name(name, facing):
    assert f_filters.is_user_facing(name) is facing


def test_hidden_flag_is_ignored(model):
    add_table(model, "Cost Log")
    add_measure(model, "Hidden Cost", "SUM('Cost Log'[Amount])", hidden=True)
    assert f_filters.uncovered_facts(model)["Cost Log"] == []


def test_caption_measure_does_not_consume(model):
    add_table(model, "Promo Log")
    add_measure(model, "i-Promo Caption", "COUNTROWS('Promo Log') & \"\"")
    assert "Promo Log" not in f_filters.uncovered_facts(model)


# -- 3. reach ---------------------------------------------------------------------
def test_any_f_measure_in_any_table_covers(model):
    add_gift_cards(model)
    add_measure(model, "f-Extra", "int(not ISEMPTY('Gift Cards'))", hidden=True)
    assert "Gift Cards" not in f_filters.uncovered_facts(model)


def test_comments_and_strings_do_not_reach(model):
    add_table(model, "Gift Cards")
    add_measure(model, "Card Note", '"\'Gift Cards\'" // \'Gift Cards\'[Amount]')
    assert "Gift Cards" not in f_filters.uncovered_facts(model)


def test_bare_and_bracket_table_references(model):
    add_table(model, "Refunds")
    add_measure(model, "Refund Total", "SUM(Refunds[Amount])")
    assert "Refunds" in f_filters.uncovered_facts(model)


# -- 4. x-Selector entries -----------------------------------------------------------
def test_selector_row_categorises_the_fact_it_reaches(model):
    add_gift_cards(model)
    assert f_filters.uncovered_facts(model)["Gift Cards"] == ["Gifting"]


def test_plot_specific_rows_attribute_nothing(model):
    add_gift_cards(model, selector=False)
    sel = (_tables(model) / "x-Selector 1.tmdl").read_text(encoding="utf-8")
    (_tables(model) / "x-Plot Specific 1.tmdl").write_text(
        sel.replace("x-Selector 1", "x-Plot Specific 1").replace(
            '1, "web_m")', '1, "web_m"),\n\t\t\t\t    ("Card Total", NAMEOF(\'Sales Measures\'[Card Total]), 2, "gift_m")'),
        encoding="utf-8")
    assert f_filters.uncovered_facts(model)["Gift Cards"] == []


def test_unfenced_selector_attributes_nothing(model):
    add_gift_cards(model)
    sel = _tables(model) / "x-Selector 1.tmdl"
    text = sel.read_text(encoding="utf-8").replace("source = ```", "source =")
    sel.write_text(text.replace("\t\t\t\t}\n\t\t\t\t```\n", "\t\t\t\t}\n"), encoding="utf-8")
    assert f_filters.selector_entries(model) == []
    assert f_filters.uncovered_facts(model) == {"Gift Cards": [], "Web Sales": []}


def test_row_without_a_string_label_attributes_nothing(model):
    add_gift_cards(model, selector=False)
    add_selector_row(model, '([Card Label], NAMEOF(\'Sales Measures\'[Card Total]), 2, "gift_m")')
    assert f_filters.uncovered_facts(model)["Gift Cards"] == []


def test_commented_row_and_missing_measure_attribute_nothing(model):
    add_gift_cards(model, selector=False)
    add_selector_row(model, '// ("Card Total", NAMEOF(\'Sales Measures\'[Card Total]), 2, "gift_m")')
    add_selector_row(model, '("Ghost", NAMEOF(\'Sales Measures\'[Ghost]), 3, "gift_m")')
    assert f_filters.uncovered_facts(model)["Gift Cards"] == []
    assert ("Ghost", "gift_m") not in f_filters.selector_entries(model, {"Card Total"})


# -- 5. group map -------------------------------------------------------------------
def test_ignored_group_maps_to_nothing(model):
    add_gift_cards(model, group="Date_y")
    assert f_filters.uncovered_facts(model)["Gift Cards"] == []
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "f-Gifting" not in ff_text(model)


def test_zmap_decode_failure_gives_no_categories(model):
    zmap = _tables(model) / "z-Map Dimension-Measure Groupings.tmdl"
    zmap.write_text(re.sub(r'FromText\("[^"]+"', 'FromText("@@not-base64@@"',
                           zmap.read_text(encoding="utf-8")), encoding="utf-8")
    assert f_filters.registered_categories(model) == []
    assert f_filters.uncovered_facts(model) == {"Web Sales": []}


# -- 7. gated through the category mechanism ---------------------------------------
def test_direct_reader_on_an_x_row_is_already_gated(model):
    sel = _tables(model) / "x-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace(
        "NAMEOF('Sales Measures'[Web Total])", "NAMEOF('Sales Measures'[Web Revenue])"),
        encoding="utf-8")
    gate_spend_in_f_all(model)
    assert f_filters.uncovered_facts(model) == {}
    before = tree(model)
    run = forge("f-filters", "--model", model)
    assert run.code == 0, run.text
    assert tree(model) == before
    assert "created=0 extended=0 skipped=0 f-All=-  -> OK" in run.out


def test_transitive_reader_on_an_x_row_leaves_a_gap_that_is_filled(model):
    assert f_filters.uncovered_facts(model) == {"Web Sales": ["Spend"]}
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert "int(not ISEMPTY('Web Sales'))" in _measure(ff_text(model), "f-Spend")
    assert f_filters.uncovered_facts(model) == {}


def test_sensor_only_reader_does_not_gate(model):
    add_measure(model, "Web Flag", "IF(ISEMPTY('Web Sales'), 0, [Web Revenue])")
    sel = _tables(model) / "x-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace("[Web Total]", "[Web Flag]"),
                   encoding="utf-8")
    assert f_filters.uncovered_facts(model) == {"Web Sales": ["Spend"]}


@pytest.mark.parametrize("expr, table, reads", [
    ("SUM('Web Sales'[Amount])", "Web Sales", True),
    ("IF(ISFILTERED('Web Sales'[Amount]), 1)", "Web Sales", False),
    ("IF(hasonevalue('Web Sales'[Amount]), 1) + COUNTROWS('Web Sales')", "Web Sales", True),
    ("ISEMPTY(FILTER('Web Sales', [x] > (1)))", "Web Sales", False),
    ("1 // SUM('Web Sales'[Amount])", "Web Sales", False),
    ("1 /* 'Web Sales' */", "Web Sales", False),
    ("COUNTROWS(Refunds)", "Refunds", True),
    ("COUNTROWS(RefundsOld)", "Refunds", False),
    ('"--" & COUNTROWS(Refunds)', "Refunds", True),
])
def test_data_read(expr, table, reads):
    assert f_filters.data_reads(expr, table) is reads


# -- 9. registered categories ----------------------------------------------------------
def test_registered_categories_are_sorted_first_cells(model):
    assert f_filters.registered_categories(model) == ["Email Marketing Campaigns", "Spend"]


def test_two_payloads_skip_coverage_silently(model):
    zmap = _tables(model) / "z-Map Dimension-Measure Groupings.tmdl"
    text = zmap.read_text(encoding="utf-8")
    second = re.search(r"\tpartition .*?(?=\n\tannotation)", text, re.S).group(0)
    zmap.write_text(text.replace("\tannotation", second.replace("Groupings' = m", "Groupings 2' = m")
                                 + "\n\tannotation", 1), encoding="utf-8")
    assert f_filters.registered_categories(model) == []
    run = forge("f-filters", "--model", model, "--no-backups", "-v")
    assert run.code == 0, run.text
    assert "CONTAINSSTRING(all_cats, \"Spend\")" not in ff_text(model)
    assert "f-All coverage" not in run.out and "error" not in run.text.lower()


# -- 10/11. plan and created measures ---------------------------------------------------
def test_variant_spelling_does_not_stop_the_create(model):
    add_table(model, "Loyalty")
    add_measure(model, "Loyal Base", "COUNTROWS('Loyalty')")
    add_measure(model, "Loyal Members", "[Loyal Base]")
    set_zmap(model, ZMAP_ROWS + [["Loyalty Cohort", "", "loyal_m"]])
    add_selector_row(model, '("Members", NAMEOF(\'Sales Measures\'[Loyal Members]), 2, "loyal_m")')
    variant = "\tmeasure 'f-Loyalty_Cohort' = 0\n\t\tisHidden\n\t\tlineageTag: f-lc\n\n"
    _ff(model).write_text(ff_text(model).replace("\tmeasure 'f-Email_Marketing'",
                                                 variant + "\tmeasure 'f-Email_Marketing'"),
                          encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff_text(model)
    assert variant in after
    assert "\tmeasure 'f-Loyalty Cohort' = int(not ISEMPTY('Loyalty'))\n" in after
    assert "     CREATE  f-Loyalty Cohort\n" in run.out
    assert "warning" not in run.out.lower()


def test_created_block_single_fact():
    assert f_filters.new_measure_block("f-Gifting", ["Gift Cards"]) == (
        "\tmeasure 'f-Gifting' = int(not ISEMPTY('Gift Cards'))\n"
        "\t\tisHidden\n\t\tdisplayFolder: Visual-Level filters\n"
        "\t\tlineageTag: f-gifting-auto-generated\n\n"
        '\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}\n\n')


def test_created_block_three_facts_is_fenced():
    block = f_filters.new_measure_block(
        "f-Loyalty Cohort", ["Gift Cards", "Loyalty Points", "Store Credit Notes"])
    assert block == (
        "\tmeasure 'f-Loyalty Cohort' = ```\n"
        "\t\t\tint(not ISEMPTY('Gift Cards')) + int(not ISEMPTY('Loyalty Points')) + "
        "int(not ISEMPTY('Store Credit Notes'))\n"
        "\t\t```\n"
        "\t\tisHidden\n\t\tdisplayFolder: Visual-Level filters\n"
        "\t\tlineageTag: f-loyalty-cohort-auto-generated\n\n"
        '\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}\n\n')


def test_expression_of_exactly_100_characters_is_fenced():
    name80, name79 = "N" * 80, "N" * 79
    assert len(f"int(not ISEMPTY('{name80}'))") == 100
    assert f_filters.new_measure_block("f-X", [name80]).startswith("\tmeasure 'f-X' = ```\n")
    assert f_filters.new_measure_block("f-X", [name79]).startswith(
        f"\tmeasure 'f-X' = int(not ISEMPTY('{name79}'))\n")


def test_quotes_in_names_are_escaped():
    block = f_filters.new_measure_block("f-Bob's", ["Bob's Log"])
    assert block.startswith("\tmeasure 'f-Bob''s' = int(not ISEMPTY('Bob''s Log'))\n")


def test_create_places_the_block_before_the_table_annotation(model):
    add_gift_cards(model)
    before = ff_text(model)
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff_text(model)
    tail = ('\t\t\t\t    #"Removed Columns"\n\n'
            "\tmeasure 'f-Gifting' = int(not ISEMPTY('Gift Cards'))\n"
            "\t\tisHidden\n\t\tdisplayFolder: Visual-Level filters\n"
            "\t\tlineageTag: f-gifting-auto-generated\n\n"
            '\t\tannotation PBI_FormatHint = {"isGeneralNumber":true}\n\n\n'
            "\tannotation PBI_ResultType = Table\n")
    assert after.endswith(tail)
    head = before[:before.index("\tmeasure 'f-All'")]
    assert after.startswith(head)


def test_creates_follow_each_other_in_category_order(model):
    for fact, cat, group in (("Gift Cards", "Gifting", "gift_m"), ("Bean Orders", "Beans Club", "bean_m")):
        add_table(model, fact)
        add_measure(model, f"{fact} Base", f"COUNTROWS('{fact}')")
        add_measure(model, f"{fact} Total", f"[{fact} Base]")
        add_selector_row(model, f'("{fact}", NAMEOF(\'Sales Measures\'[{fact} Total]), 2, "{group}")')
    set_zmap(model, ZMAP_ROWS + [["Gifting", "", "gift_m"], ["Beans Club", "", "bean_m"]])
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    after = ff_text(model)
    assert after.index("'f-Beans Club'") < after.index("'f-Gifting'") < \
        after.index("\tannotation PBI_ResultType")


def test_block_goes_before_the_final_line_break_without_annotation():
    assert f_filters.insert_measure("table t\n", "B\n") == "table t\nB\n\n"
    assert f_filters.insert_measure("table t", "B\n") == "table t\nB\n"


# -- 12/13. extend ------------------------------------------------------------------
EXTEND_WARNING = (
    "\n   ⚠️  EXTENDED f-Spend by appending `+ int(not ISEMPTY('Web Sales'))`\n"
    "     If the existing measure is AGGREGATOR, SWITCH-ROUTER, or DISPLAY-STRING (per "
    "tmdl-preflight A005 f-measure-pattern), this append likely BROKE its semantics or DAX "
    "syntax. MANUAL VERIFY NOW before committing.\n")


def test_extend_fenced_measure_bytes_and_warning(model):
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert _measure(ff_text(model), "f-Spend") == (
        "\tmeasure 'f-Spend' = ```\n"
        "\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))\n"
        "\t\t```\n"
        "\t\tisHidden\n\t\tdisplayFolder: Visual-Level filters\n\t\tlineageTag: f-spend\n\n")
    assert EXTEND_WARNING in run.out
    assert EXTEND_WARNING in run.err


def test_extend_fenced_strips_trailing_blank_lines(model):
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tint(not ISEMPTY('Store Sales'))\n\t\t\t```",
        "\t\t\tint(not ISEMPTY('Store Sales'))   \n\n\t\t\t\n\t\t\t```"), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert ("\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))\n\t\t```\n"
            in ff_text(model))


def test_warning_lists_every_new_fact(model):
    add_table(model, "Web Refunds")
    add_measure(model, "Web Refund Base", "COUNTROWS('Web Refunds')")
    _ff(model)  # Web Total now reaches both web facts
    tables = _tables(model) / "Sales Measures.tmdl"
    tables.write_text(tables.read_text(encoding="utf-8").replace(
        "'Web Total' = [Web Revenue]", "'Web Total' = [Web Revenue] + [Web Refund Base]"),
        encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups", "--dry-run")
    assert ("EXTENDED f-Spend by appending `+ int(not ISEMPTY('Web Refunds'))` "
            "`+ int(not ISEMPTY('Web Sales'))`\n") in run.out
    assert "     EXTEND  f-Spend  (+ Web Refunds, Web Sales)\n" in run.out


@pytest.mark.parametrize("marker", ["//", "--"])
def test_extension_lands_before_a_trailing_comment(model, marker):
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tint(not ISEMPTY('Store Sales'))\n",
        f"\t\t\tint(not ISEMPTY('Store Sales')) {marker} in-store tills\n"), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    spend = _measure(ff_text(model), "f-Spend")
    assert (f"\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales')) "
            f"{marker} in-store tills\n\t\t```\n") in spend
    assert f_filters.uncovered_facts(model) == {}


def test_extension_skips_a_comment_only_last_line(model):
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tint(not ISEMPTY('Store Sales'))\n",
        "\t\t\tint(not ISEMPTY('Store Sales'))\n\t\t\t// web shop added later\n"), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    spend = _measure(ff_text(model), "f-Spend")
    assert ("\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))\n"
            "\t\t\t// web shop added later\n\t\t```\n") in spend
    assert f_filters.uncovered_facts(model) == {}


def test_extension_of_an_inline_measure(model):
    _ff(model).write_text(re.sub(r"\tmeasure 'f-Spend' = ```\n.*?```\n",
                                 "\tmeasure 'f-Spend' = int(not ISEMPTY('Store Sales'))  // tills\n",
                                 ff_text(model), flags=re.S), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert ("\tmeasure 'f-Spend' = int(not ISEMPTY('Store Sales')) + "
            "int(not ISEMPTY('Web Sales')) // tills\n") in ff_text(model)


def test_fact_in_two_categories_is_handled_for_each(model):
    set_zmap(model, ZMAP_ROWS + [["Online", "", "web_m"]])
    _ff(model).write_text(ff_text(model).replace(
        "\tmeasure 'f-Email_Marketing' = 1\n",
        "\tmeasure 'f-Online' = 0\n\t\tisHidden\n\n\tmeasure 'f-Email_Marketing' = 1\n"),
        encoding="utf-8")
    assert f_filters.uncovered_facts(model) == {"Web Sales": ["Online", "Spend"]}
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    after = ff_text(model)
    assert "\tmeasure 'f-Online' = 0 + int(not ISEMPTY('Web Sales'))\n" in after
    assert "int(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))" in after
    assert f_filters.uncovered_facts(model) == {}


# -- 14-18. f-All gate lines --------------------------------------------------------
F_ALL_ONE_RUN = (
    "\t\t\tVAR temp_basic = TRUE()\n"
    '\t\t\t    && IF(CONTAINSSTRING(all_cats, "Email Marketing"), IF([f-Email_Marketing] > 0, TRUE(), FALSE()), TRUE())\n'
    f"{GATE}{BASIC_SPEND}\n"
    "\t\t\t\n"
    "\t\t\tVAR temp_alt = FALSE()\n"
    '\t\t\t    || IF(CONTAINSSTRING(all_cats, "Email Marketing"), IF([f-Email_Marketing] > 0, TRUE(), FALSE()), FALSE())\n'
    f"{GATE}{ALT_SPEND}\n"
    "\t\t\t\n"
    "\t\t\tRETURN IF(temp_basic || temp_alt, 1, 0)\n")


def test_gate_lines_bytes_after_one_and_two_runs(model):
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert F_ALL_ONE_RUN in ff_text(model)

    set_zmap(model, ZMAP_ROWS + [["Gifting", "", "gift_m"]])
    _ff(model).write_text(ff_text(model).replace(
        "\tmeasure 'f-Email_Marketing' = 1\n",
        "\tmeasure 'f-Gifting' = 0\n\t\tisHidden\n\n\tmeasure 'f-Email_Marketing' = 1\n"),
        encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    gift_b = f'{GATE}&& IF(CONTAINSSTRING(all_cats, "Gifting"), IF([f-Gifting] > 0, TRUE(), FALSE()), TRUE())\n'
    gift_a = f'{GATE}|| IF(CONTAINSSTRING(all_cats, "Gifting"), IF([f-Gifting] > 0, TRUE(), FALSE()), FALSE())\n'
    two = (F_ALL_ONE_RUN
           .replace(f"{GATE}{BASIC_SPEND}\n\t\t\t\n", f"{GATE}{BASIC_SPEND}\n{gift_b}\t\t\t\n\t\t\t\n")
           .replace(f"{GATE}{ALT_SPEND}\n\t\t\t\n", f"{GATE}{ALT_SPEND}\n{gift_a}\t\t\t\n\t\t\t\n"))
    assert two in ff_text(model)


def test_created_category_is_gated_in_pass_one(model):
    add_gift_cards(model)
    run = forge("f-filters", "--model", model, "--no-backups", "-v")
    assert run.code == 0, run.text
    after = ff_text(model)
    basic = _chain(after, "temp_basic")
    assert basic.count('CONTAINSSTRING(all_cats, "Gifting")') == 1
    assert "f-All=+1  -> OK" in run.out
    assert "\n   f-All extended with 1 new categor(ies): Gifting\n" in run.out
    assert ("\n   f-All coverage: 3 z-Map categor(ies), 1 gate(s) added, 2 already gated, "
            "0 unresolved\n      + gate Spend -> [f-Spend]\n") in run.out
    # pass 1's batch, then pass 2's batch
    assert basic.index('"Gifting"') < basic.index('"Spend"')


def test_created_category_already_gated_is_counted_as_skip(model):
    add_gift_cards(model)
    set_zmap(model, ZMAP_ROWS + [["Gifting", "", "gift_m"], ["Gift", "", "x_m"]])
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tVAR temp_alt",
        '\t\t\t    && IF(CONTAINSSTRING(all_cats, "Gift"), IF([f-Gift] > 0, TRUE(), FALSE()), TRUE())\n'
        "\t\t\tVAR temp_alt", 1), encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups", "--dry-run", "-v")
    assert "f-All=+0/skip 1  -> OK" in run.out
    assert "     f-All   Gifting already gated, no new line added\n" in run.out
    assert ("   f-All skipped 1 already-gated categor(ies): Gifting\n"
            "     (these categories already have an un-commented CONTAINSSTRING(all_cats, ...) "
            "gate, possibly under a non-canonical f-measure name)\n") in run.out


@pytest.mark.parametrize("marker", ["//", "--"])
def test_commented_gate_line_contributes_no_literal(model, marker):
    commented = f'\t\t\t    {marker} {BASIC_SPEND}\n'
    _ff(model).write_text(ff_text(model).replace("\t\t\tVAR temp_alt", commented + "\t\t\tVAR temp_alt", 1),
                          encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    basic = _chain(ff_text(model), "temp_basic")
    assert basic.count(f"{GATE}{BASIC_SPEND}") == 1
    assert commented in ff_text(model)


def test_only_temp_basic_literals_count(model):
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tRETURN", f"{GATE}{ALT_SPEND}\n\t\t\tRETURN", 1), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert _chain(ff_text(model), "temp_alt").count(ALT_SPEND) == 2


def test_case2_f_measure_resolution_order():
    for declared, expected in [
        ({"f-Loyalty Cohort", "f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty Cohort"),
        ({"f-Loyalty_Cohort"}, "f-Loyalty_Cohort"),
        ({"f-LoyaltyCohort"}, "f-LoyaltyCohort"),
        ({"f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty_Cohort"),
        (set(), None),
    ]:
        assert f_filters.find_gate_measure("Loyalty Cohort", declared) == expected


def test_registered_category_without_measure_is_unresolved(model):
    set_zmap(model, ZMAP_ROWS + [["Gift Cards", "", "gift_m"]])
    run = forge("f-filters", "--model", model, "--no-backups", "-v")
    assert run.code == 0, run.text
    assert ("      ! Gift Cards: registered in z-Map but no f- measure exists to gate it "
            "— create one first\n") in run.out
    assert "Gift Cards" not in ff_text(model)


def test_gate_lines_go_into_f_all_only(model):
    debug = ("\tmeasure 'f-Debug' = ```\n\t\t\tVAR temp_basic = 1\n\t\t\tVAR temp_alt = 0\n"
             "\t\t\tRETURN temp_basic\n\t\t\t```\n\t\tisHidden\n\n")
    _ff(model).write_text(ff_text(model).replace("\tmeasure 'f-All' = ```",
                                                 debug + "\tmeasure 'f-All' = ```", 1), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    after = ff_text(model)
    assert debug in after
    f_all = _measure(after, "f-All")
    assert f_all.count(BASIC_SPEND) == 1 and f_all.count(ALT_SPEND) == 1


def test_duplicate_chain_writes_no_gate(model):
    _ff(model).write_text(ff_text(model).replace(
        "\t\t\tVAR temp_alt = FALSE()", "\t\t\tVAR temp_basic = TRUE()\n\t\t\tVAR temp_alt = FALSE()", 1),
        encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "more than once" in run.out
    assert 'CONTAINSSTRING(all_cats, "Spend")' not in ff_text(model)


def test_missing_temp_alt_writes_no_lines_at_all(model):
    _ff(model).write_text(re.sub(r"\t\t\tVAR temp_alt = FALSE\(\)\n.*?\n", "", ff_text(model)),
                          encoding="utf-8")
    assert "VAR temp_alt" not in ff_text(model)
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert 'CONTAINSSTRING(all_cats, "Spend")' not in ff_text(model)


def test_no_temp_basic_after_a_create_warns_on_stderr(model):
    add_gift_cards(model)
    _ff(model).write_text(re.sub(r"\tmeasure 'f-All' = ```.*?lineageTag: f-all\n\n", "",
                                 ff_text(model), flags=re.S), encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups", "-v")
    assert run.code == 0, run.text
    assert ("\n   ⚠️  f-All temp_basic block not found — created f-<Cat> measures but didn't "
            "extend the orchestrator. Either f-All is named/structured differently here or "
            "this model doesn't use one.\n") in run.err
    assert "f-All coverage: 3 z-Map categor(ies), 0 gate(s) added, 0 already gated, 3 unresolved" in run.out
    assert "CONTAINSSTRING" not in ff_text(model)
    assert "\tmeasure 'f-Gifting' = " in ff_text(model)


def test_gate_line_escapes_quotes_and_brackets():
    line = f_filters.gate_line('Say "Hi" Promos', "f-Promo]x", "basic")
    assert line == ('&& IF(CONTAINSSTRING(all_cats, "Say ""Hi"" Promos"), '
                    'IF([f-Promo]]x] > 0, TRUE(), FALSE()), TRUE())')
    assert f_filters.live_gate_names("\t\t\t" + line) == ['Say "Hi" Promos']


def test_category_with_a_quote_is_gated_once(model):
    set_zmap(model, ZMAP_ROWS + [['Say "Hi"', "", "hi_m"]])
    _ff(model).write_text(ff_text(model).replace(
        "\tmeasure 'f-Email_Marketing' = 1\n",
        "\tmeasure 'f-Say \"Hi\"' = 1\n\t\tisHidden\n\n\tmeasure 'f-Email_Marketing' = 1\n"),
        encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    once = _ff(model).read_bytes()
    assert once.count(b'CONTAINSSTRING(all_cats, "Say ""Hi""")') == 2
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert _ff(model).read_bytes() == once


# -- 19. writing ---------------------------------------------------------------------
def test_model_without_f_filters_fails(model):
    _ff(model).unlink()
    before = tree(model)
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert f"-> FAIL: f-Filters.tmdl not found: {_ff(model)}\n" in run.out
    assert tree(model) == before


def test_dry_run_writes_nothing_and_second_run_is_a_no_op(model):
    before = tree(model)
    dry = forge("f-filters", "--model", model, "--dry-run")
    assert dry.code == 0, dry.text
    assert "mode: DRY-RUN" in dry.out and "EXTEND  f-Spend" in dry.out
    assert tree(model) == before

    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    once = tree(model)
    assert once != before
    second = forge("f-filters", "--model", model, "--no-backups", "-v")
    assert second.code == 0, second.text
    assert "\n   No changes needed.\n" in second.out
    assert tree(model) == once


def test_backup_keeps_bytes_and_modification_time(model):
    ff = _ff(model)
    original = b"\xef\xbb\xbf" + ff.read_bytes().replace(b"\n", b"\r\n")
    ff.write_bytes(original)
    os.utime(ff, (1_600_000_000, 1_600_000_000))
    run = forge("f-filters", "--model", model, "-v")
    assert run.code == 0, run.text
    backups = list(ff.parent.glob("f-Filters.tmdl.backup_gapfill_*"))
    assert len(backups) == 1
    assert re.fullmatch(r"f-Filters\.tmdl\.backup_gapfill_\d{8}_\d{6}", backups[0].name)
    assert backups[0].read_bytes() == original
    assert backups[0].stat().st_mtime == 1_600_000_000
    assert f"\n   backup: {backups[0].name}\n\n   Wrote {ff}\n" in run.out
    after = ff.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf") and after.count(b"\n") == after.count(b"\r\n")


def test_no_backups_adds_no_files(model):
    names = set(tree(model))
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert set(tree(model)) == names


def test_crlf_file_stays_crlf_and_matches_the_lf_edit(tmp_path):
    lf = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path / "lf")
    crlf = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path / "crlf")
    for f in crlf.rglob("*.tmdl"):
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    assert forge("f-filters", "--model", lf, "--no-backups").code == 0
    assert forge("f-filters", "--model", crlf, "--no-backups").code == 0
    assert _ff(crlf).read_bytes() == _ff(lf).read_bytes().replace(b"\n", b"\r\n")


def test_unexpected_error_fails_only_that_model(tmp_path, monkeypatch):
    fleet = tmp_path / "fleet"
    good = copy_fixture("f_filters/Roastery.SemanticModel", fleet)
    bad = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path / "x")
    bad = bad.rename(fleet / "Broken.SemanticModel")
    real = f_filters.uncovered_facts

    def flaky(model_dir):
        if "Broken" in str(model_dir):
            raise RuntimeError("index exploded")
        return real(model_dir)

    from pbip_model_forge import f_filters as module
    monkeypatch.setattr(module, "uncovered_facts", flaky)
    run = forge("f-filters", "--fleet", fleet, "--no-backups")
    assert run.code == 1, run.text
    assert "-> FAIL: index exploded\n" in run.out
    assert "Traceback" not in run.err
    assert BASIC_SPEND in ff_text(good)
    verbose = forge("f-filters", "--fleet", fleet, "--no-backups", "-v")
    assert "Traceback" in verbose.err and "RuntimeError: index exploded" in verbose.err


# -- 20/21. console output -------------------------------------------------------------
def test_fleet_labels_and_missing_tables_folder(tmp_path):
    fleet = tmp_path / "fleet"
    copy_fixture("f_filters/Roastery.SemanticModel", fleet)
    (fleet / "Broken.SemanticModel").mkdir()
    run = forge("f-filters", "--fleet", fleet, "--no-backups")
    assert run.code == 1, run.text
    assert run.out.startswith("f-filter update — 2 target(s); mode: APPLY\n")
    broken = fleet / "Broken.SemanticModel"
    assert (f"\n[SKIP] {fleet}/Broken.SemanticModel: {broken / 'definition' / 'tables'} not found\n"
            in run.err)
    roastery = fleet / "Roastery.SemanticModel"
    assert f"\n── {fleet}/Roastery.SemanticModel  ({roastery.resolve()})\n" in run.out
    assert BASIC_SPEND in ff_text(roastery)


def _snapshot_model(tmp_path: Path) -> Path:
    """One create (Gifting), one extend (f-Spend) and three skips."""
    model = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path)
    add_gift_cards(model)
    for fact, measure, hidden in (("Stores", "Store Count", False), ("Cost Log", "Hidden Cost", True),
                                  ("Returns", "Return Total", False)):
        add_table(model, fact)
        add_measure(model, measure, f"COUNTROWS('{fact}')", hidden=hidden)
    return model


REVIEW = """
─── REVIEW REQUIRED ─────────────────────────────────────────────────────
This script only emits the STANDARD f-measure shape:
    int(not ISEMPTY('<FactTable>'))

Per tmdl-preflight A005 (f-measure-pattern), three other shapes exist:
  AGGREGATOR     [f-A] + [f-B]                       (combines refs)
  SWITCH-ROUTER  SWITCH(TRUE(), ...)                 (category dispatch)
  DISPLAY-STRING CONCATENATEX-based, in w-* tables   (visual labels)

The emitted STANDARD measures are CORRECT for any measure that should
existence-check a fact table. If any newly-created f-measure should
actually be one of the three non-STANDARD shapes, that emission is
WRONG and needs manual conversion.

Run the classifier:
  tmdl-preflight check <model> --select A005

Any measure flagged as unclassified is one this script emitted that needs
to be rewritten by hand.
─────────────────────────────────────────────────────────────────────────

"""
EXTENDED_BANNER = """
⚠️  ONE OR MORE EXISTING f-MEASURES WERE EXTENDED ABOVE.
    If any extended measure was AGGREGATOR / SWITCH-ROUTER /
    DISPLAY-STRING (not STANDARD), the append BROKE its
    semantics or DAX syntax. MANUAL VERIFY NOW.

"""
SKIP_REASON = ("             consumed by user-facing measures but no z-Map mapping for any "
               "x-Selector category_x_id that reaches it (missing z-Map row, or candidate for "
               "removal)\n")


def test_dry_run_console_snapshot(tmp_path):
    model = _snapshot_model(tmp_path)
    before = tree(model)
    run = forge("f-filters", "--model", model, "--dry-run")
    assert run.code == 0
    assert tree(model) == before
    assert run.out == (
        "f-filter update — 1 target(s); mode: DRY-RUN\n"
        "\n"
        f"── {model}  ({model.resolve()})\n"
        + EXTEND_WARNING +
        "   created=1 extended=1 skipped=3 f-All=+1  -> OK\n"
        "     CREATE  f-Gifting\n"
        "     EXTEND  f-Spend  (+ Web Sales)\n"
        "     SKIP    Cost Log\n" + SKIP_REASON +
        "     SKIP    Returns\n" + SKIP_REASON +
        "     SKIP    Stores\n" + SKIP_REASON)
    assert run.err == EXTEND_WARNING + EXTENDED_BANNER + REVIEW


def test_verbose_console_snapshot(tmp_path):
    model = _snapshot_model(tmp_path)
    run = forge("f-filters", "--model", model, "--dry-run", "-v")
    assert run.code == 0
    ff = _ff(model)
    assert run.out == (
        "f-filter update — 1 target(s); mode: DRY-RUN\n"
        "\n"
        f"── {model}  ({model.resolve()})\n"
        "\n"
        f"── Loading model index from {model}\n"
        "   Uncovered fact tables: 5\n"
        "\n"
        "   Uncategorized (skipped): 3\n"
        "     - Cost Log\n"
        "     - Returns\n"
        "     - Stores\n"
        "\n"
        "   CREATE f-Gifting\n"
        "     dax: int(not ISEMPTY('Gift Cards'))\n"
        + EXTEND_WARNING +
        "\n"
        "   f-All extended with 1 new categor(ies): Gifting\n"
        "\n"
        "   f-All coverage: 3 z-Map categor(ies), 1 gate(s) added, 2 already gated, 0 unresolved\n"
        "      + gate Spend -> [f-Spend]\n"
        "\n"
        f"── DRY-RUN: would write {ff}\n"
        "   created=1 extended=1 skipped=3 f-All=+1  -> OK\n"
        "     CREATE  f-Gifting\n"
        "     EXTEND  f-Spend  (+ Web Sales)\n"
        "     SKIP    Cost Log\n" + SKIP_REASON +
        "     SKIP    Returns\n" + SKIP_REASON +
        "     SKIP    Stores\n" + SKIP_REASON)


def test_review_block_is_always_printed(model):
    gate_spend_in_f_all(model)
    sel = _tables(model) / "x-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace("[Web Total]", "[Web Revenue]"),
                   encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0
    assert run.err == REVIEW


def test_result_names_the_combined_gates_added(model):
    add_gift_cards(model)
    res = f_filters.fill_gaps(model, dry_run=True)
    assert res.combined_gates_added == ["Gifting"]
    assert res.created == {"f-Gifting": ["Gift Cards"]}
    assert res.extended == {"f-Spend": ["Web Sales"]}
