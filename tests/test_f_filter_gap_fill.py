"""`pbip-forge f-filters`: gap-fill f-<Category> measures and f-All gates.

Spec F-f-filter-gap-fill, fictional cases 1-7 plus the create path of the
Fix section. Fixture: tests/fixtures/f_filters/Roastery.SemanticModel
(fictional coffee roastery):

* facts `Store Sales` (read by `Store Revenue`, group store_m) and
  `Web Sales` (read by `Web Revenue`, group web_m);
* z-Map rows: Spend <- store_m, Spend <- web_m,
  Email Marketing Campaigns <- email_m;
* f-Filters: `f-All` with paired temp_basic / temp_alt chains gating only
  the literal "Email Marketing", a fenced `f-Spend` reading Store Sales, and
  `f-Email_Marketing`.

So `Web Sales` is uncovered (category Spend -> extend f-Spend) and the z-Map
category Spend is not yet gated in f-All.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ported_helpers import copy_fixture, forge, lazy_module, tree

#: shared gap-fill library (proposed module), imported lazily so a missing
#: module fails each test that uses it instead of the whole file.
f_filters = lazy_module("pbip_model_forge.f_filters")

BASIC_SPEND = '&& IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), TRUE())'
ALT_SPEND = '|| IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), FALSE())'


@pytest.fixture
def model(tmp_path: Path) -> Path:
    return copy_fixture("f_filters/Roastery.SemanticModel", tmp_path)


def _ff(model: Path) -> Path:
    return model / "definition" / "tables" / "f-Filters.tmdl"


def _chain(text: str, var: str) -> str:
    """Lines of one VAR chain of f-All (from `VAR <var>` to the next VAR/RETURN)."""
    m = re.search(rf"VAR {var} =.*?(?=\n\s*(?:VAR |RETURN))", text, re.S)
    assert m, f"no {var} chain"
    return m.group(0)


def _measure(text: str, name: str) -> str:
    m = re.search(rf"^\tmeasure '{re.escape(name)}' =.*?(?=^\t(?:measure|partition|annotation|column) |\Z)",
                  text, re.S | re.M)
    assert m, f"measure {name} not found"
    return m.group(0)


# -- case 1 ----------------------------------------------------------------------
def test_case1_substring_literal_gates_category_and_spend_gets_paired_lines(model):
    before = _ff(model).read_text(encoding="utf-8")
    literals = f_filters.live_gate_names(before)
    assert set(literals) == {"Email Marketing"}
    assert f_filters.category_gated("Email Marketing Campaigns", literals)
    assert not f_filters.category_gated("Spend", literals)

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = _ff(model).read_text(encoding="utf-8")
    basic, alt = _chain(after, "temp_basic"), _chain(after, "temp_alt")
    assert basic.count(BASIC_SPEND) == 1
    assert alt.count(ALT_SPEND) == 1
    assert ALT_SPEND not in basic and BASIC_SPEND not in alt
    # the already-gated category gets no new line, existing lines untouched
    assert after.count('CONTAINSSTRING(all_cats, "Email Marketing")') == 2
    for line in before.splitlines():
        if "CONTAINSSTRING" in line:
            assert line in after.splitlines()


def test_case1_map_table_categories_are_decoded(model):
    assert sorted(f_filters.map_table_categories(model)) == ["Email Marketing Campaigns", "Spend"]


def test_zmap_decode_failure_skips_enforcement(model):
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    text = zmap.read_text(encoding="utf-8")
    zmap.write_text(re.sub(r'FromText\("[^"]+"', 'FromText("@@not-base64@@"', text), encoding="utf-8")
    assert f_filters.map_table_categories(model) == []


# -- case 2 ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "declared, expected",
    [
        ({"f-Loyalty Cohort", "f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty Cohort"),
        ({"f-Loyalty_Cohort"}, "f-Loyalty_Cohort"),
        ({"f-LoyaltyCohort"}, "f-LoyaltyCohort"),
        ({"f-Loyalty_Cohort", "f-LoyaltyCohort"}, "f-Loyalty_Cohort"),
    ],
)
def test_case2_f_measure_resolution_order(declared, expected):
    assert f_filters.find_gate_measure("Loyalty Cohort", declared) == expected


def test_declared_measures_reads_all_quoting_styles():
    text = ("table 'f-Filters'\n\tmeasure 'f-Spend' = 1\n\tmeasure \"f-Email\" = 1\n"
            "\tmeasure f-Web = 1\n")
    assert f_filters.declared_measures(text) == {"f-Spend", "f-Email", "f-Web"}


# -- case 3 ----------------------------------------------------------------------
def test_case3_category_without_measure_is_unresolved_and_never_gated(model):
    assert f_filters.find_gate_measure("Gift Cards", {"f-Spend"}) is None
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    from ported_helpers import raw_deflate_b64
    import json
    rows = [["Spend", "", "store_m"], ["Spend", "", "web_m"],
            ["Email Marketing Campaigns", "", "email_m"], ["Gift Cards", "", "gift_m"]]
    b64 = raw_deflate_b64(json.dumps(rows, separators=(",", ":")).encode())
    text = zmap.read_text(encoding="utf-8")
    zmap.write_text(re.sub(r'FromText\("[^"]+"', f'FromText("{b64}"', text), encoding="utf-8")

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "Gift Cards" in run.text            # listed as unresolved
    assert "unresolved" in run.text.lower()
    assert "Gift Cards" not in _ff(model).read_text(encoding="utf-8")


# -- case 4 ----------------------------------------------------------------------
@pytest.mark.parametrize("marker", ["//", "--"])
def test_case4_commented_gate_line_contributes_no_literal(model, marker):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8")
    commented = f'\t\t\t    {marker} && IF(CONTAINSSTRING(all_cats, "Spend"), IF([f-Spend] > 0, TRUE(), FALSE()), TRUE())\n'
    text = text.replace("\t\t\tVAR temp_alt", commented + "\t\t\tVAR temp_alt", 1)
    ff.write_text(text, encoding="utf-8")
    assert "Spend" not in set(f_filters.live_gate_names(text))

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    basic = _chain(ff.read_text(encoding="utf-8"), "temp_basic")
    active = [ln for ln in basic.splitlines() if ln.strip().startswith("&&")]
    assert sum(BASIC_SPEND in ln for ln in active) == 1
    assert commented.rstrip("\n") in ff.read_text(encoding="utf-8")  # never edited


# -- case 5 ----------------------------------------------------------------------
def test_case5_extend_fenced_measure_inside_fence_with_loud_warning(model):
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    spend = _measure(_ff(model).read_text(encoding="utf-8"), "f-Spend")
    fence = re.search(r"```(.*?)```", spend, re.S)
    assert fence, spend
    body = fence.group(1)
    assert "int(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))" in body
    assert spend.count("ISEMPTY('Web Sales')") == 1
    for stream in (run.out, run.err):
        assert "non-standard" in stream.lower(), stream


# -- create path (Fix section; acceptance stand-in of the preflight test) ----------
def test_create_missing_category_measure(model):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8")
    text = re.sub(r"\tmeasure 'f-Spend' = ```.*?lineageTag: f-spend\n\n", "", text, flags=re.S)
    ff.write_text(text, encoding="utf-8")

    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff.read_text(encoding="utf-8")
    spend = _measure(after, "f-Spend")
    assert "int(not ISEMPTY('Store Sales'))" in spend
    assert "int(not ISEMPTY('Web Sales'))" in spend
    assert re.search(r"^\t\tisHidden$", spend, re.M)
    assert "displayFolder: Visual-Level filters" in spend
    assert "lineageTag:" in spend
    # inserted right after the last measure (and its blank line), so before
    # the partition and the table's trailing annotations
    anchor = "\t\tlineageTag: f-email-marketing\n\n"
    assert after.index("\tmeasure 'f-Spend'") == after.index(anchor) + len(anchor)
    assert after.index("measure 'f-Spend'") < after.index("\tpartition ") < \
        after.index("annotation PBI_ResultType")
    # created and resolvable -> gated in both chains
    assert _chain(after, "temp_basic").count(BASIC_SPEND) == 1
    assert _chain(after, "temp_alt").count(ALT_SPEND) == 1


# -- case 6 ----------------------------------------------------------------------
def test_case6_model_without_f_filters_is_an_error(model):
    _ff(model).unlink()
    before = tree(model)
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 1, run.text
    assert tree(model) == before


# -- case 7 ----------------------------------------------------------------------
def test_case7_dry_run_writes_nothing_and_second_run_is_a_no_op(model):
    before = tree(model)
    dry = forge("f-filters", "--model", model, "--dry-run")
    assert dry.code == 0, dry.text
    assert "f-Spend" in dry.text
    assert tree(model) == before

    first = forge("f-filters", "--model", model, "--no-backups")
    assert first.code == 0, first.text
    once = tree(model)
    assert once != before
    second = forge("f-filters", "--model", model, "--no-backups")
    assert second.code == 0, second.text
    assert tree(model) == once


def test_no_backups_adds_no_files(model):
    names = set(tree(model))
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert set(tree(model)) == names


def test_default_run_keeps_a_backup_of_f_filters(model):
    names = set(tree(model))
    assert forge("f-filters", "--model", model).code == 0
    added = set(tree(model)) - names
    assert len(added) == 1 and "f-Filters" in next(iter(added))


# -- review fixes ----------------------------------------------------------------
def _to_crlf(model: Path) -> None:
    for f in model.rglob("*.tmdl"):
        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


def _bare_lf(data: bytes) -> int:
    return data.count(b"\n") - data.count(b"\r\n")


def test_crlf_file_stays_crlf_and_matches_the_lf_edit(tmp_path):
    lf = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path / "lf")
    crlf = copy_fixture("f_filters/Roastery.SemanticModel", tmp_path / "crlf")
    _to_crlf(crlf)
    assert forge("f-filters", "--model", lf, "--no-backups").code == 0
    assert forge("f-filters", "--model", crlf, "--no-backups").code == 0
    lf_bytes, crlf_bytes = _ff(lf).read_bytes(), _ff(crlf).read_bytes()
    assert _bare_lf(crlf_bytes) == 0 and b"\r" not in lf_bytes
    # same edit, only the terminators differ
    assert crlf_bytes == lf_bytes.replace(b"\n", b"\r\n")


def test_lines_outside_the_edit_keep_their_own_endings(model):
    ff = _ff(model)
    raw = ff.read_bytes().replace(b"\n", b"\r\n")
    # one odd LF-only line far from the edit (the partition's mode line)
    raw = raw.replace(b"\t\tmode: import\r\n", b"\t\tmode: import\n")
    ff.write_bytes(raw)
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    after = ff.read_bytes()
    assert b"\t\tmode: import\n\t\tsource =\r\n" in after
    assert _bare_lf(after) == 1
    # everything after the last inserted line is byte-identical
    tail = raw[raw.index(b"\tpartition"):]
    assert after.endswith(tail)


def test_backup_is_a_byte_copy_of_a_crlf_bom_file(model):
    ff = _ff(model)
    original = b"\xef\xbb\xbf" + ff.read_bytes().replace(b"\n", b"\r\n")
    ff.write_bytes(original)
    assert forge("f-filters", "--model", model).code == 0
    backups = list(ff.parent.glob("f-Filters.tmdl.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    after = ff.read_bytes()
    assert after.startswith(b"\xef\xbb\xbf") and _bare_lf(after) == 0


@pytest.mark.parametrize("marker", ["//", "--"])
def test_extension_lands_before_a_trailing_comment(model, marker):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8").replace(
        "\t\t\tint(not ISEMPTY('Store Sales'))\n",
        f"\t\t\tint(not ISEMPTY('Store Sales')) {marker} in-store tills\n")
    ff.write_text(text, encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    spend = _measure(ff.read_text(encoding="utf-8"), "f-Spend")
    assert (f"\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales')) "
            f"{marker} in-store tills\n") in spend
    # acceptance: the extended measure really gates the fact now
    assert f_filters.uncovered_facts(model) == {}


def test_extension_skips_a_comment_only_last_line(model):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8").replace(
        "\t\t\tint(not ISEMPTY('Store Sales'))\n",
        "\t\t\tint(not ISEMPTY('Store Sales'))\n\t\t\t// web shop added later\n")
    ff.write_text(text, encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    spend = _measure(ff.read_text(encoding="utf-8"), "f-Spend")
    assert "\t\t\tint(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))\n" in spend
    assert "\t\t\t// web shop added later\n" in spend
    assert f_filters.uncovered_facts(model) == {}


def test_extension_of_an_inline_measure_with_a_comment(model):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8")
    text = re.sub(r"\tmeasure 'f-Spend' = ```\n.*?```\n",
                  "\tmeasure 'f-Spend' = int(not ISEMPTY('Store Sales')) // tills\n", text, flags=re.S)
    ff.write_text(text, encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert ("\tmeasure 'f-Spend' = int(not ISEMPTY('Store Sales')) + "
            "int(not ISEMPTY('Web Sales')) // tills\n") in ff.read_text(encoding="utf-8")
    assert f_filters.uncovered_facts(model) == {}


def test_after_a_run_no_categorised_fact_is_uncovered(model):
    assert f_filters.uncovered_facts(model) == {"Web Sales": ["Spend"]}
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    assert f_filters.uncovered_facts(model) == {}


def test_gate_lines_go_into_f_all_only(model):
    ff = _ff(model)
    debug = ("\tmeasure 'f-Debug' = ```\n\t\t\tVAR temp_basic = 1\n\t\t\tVAR temp_alt = 0\n"
             "\t\t\tRETURN temp_basic\n\t\t\t```\n\t\tisHidden\n\n")
    ff.write_text(ff.read_text(encoding="utf-8").replace("\tmeasure 'f-All' = ```",
                                                         debug + "\tmeasure 'f-All' = ```", 1),
                  encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    after = ff.read_text(encoding="utf-8")
    assert debug in after
    f_all = _measure(after, "f-All")
    assert f_all.count(BASIC_SPEND) == 1 and f_all.count(ALT_SPEND) == 1


def test_duplicate_temp_basic_in_f_all_writes_no_gate(model):
    ff = _ff(model)
    text = ff.read_text(encoding="utf-8").replace(
        "\t\t\tVAR temp_alt = FALSE()", "\t\t\tVAR temp_basic = TRUE()\n\t\t\tVAR temp_alt = FALSE()", 1)
    ff.write_text(text, encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "temp_basic more than once" in run.out
    assert 'CONTAINSSTRING(all_cats, "Spend")' not in ff.read_text(encoding="utf-8")


def test_missing_chain_pair_warns_and_writes_no_gate(model):
    ff = _ff(model)
    text = re.sub(r"\tmeasure 'f-All' = ```.*?lineageTag: f-all\n\n", "",
                  ff.read_text(encoding="utf-8"), flags=re.S)
    ff.write_text(text, encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "WARNING: f-All has no temp_basic/temp_alt chain pair; no gate lines written" in run.out
    assert "CONTAINSSTRING" not in ff.read_text(encoding="utf-8")


def test_empty_gate_table_gets_the_measure_before_its_annotation(model):
    ff = _ff(model)
    ff.write_text("table 'f-Filters'\n\tlineageTag: f\n\n\tannotation PBI_ResultType = Table\n",
                  encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff.read_text(encoding="utf-8")
    assert after.startswith("table 'f-Filters'\n\tlineageTag: f\n\n\tmeasure 'f-Spend' = ")
    assert after.endswith("\n\n\tannotation PBI_ResultType = Table\n")
    assert "WARNING: f-All has no temp_basic/temp_alt chain pair" in run.out


def test_fact_without_a_category_is_skipped_with_a_reason(model):
    sel = model / "definition" / "tables" / "x-Selector 1.tmdl"
    sel.write_text(sel.read_text(encoding="utf-8").replace('"web_m"', '"orphan_m"'), encoding="utf-8")
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    assert "skipped  Web Sales: no analysis category reaches it" in run.out
    assert "Web Sales" not in ff_text(model)


def ff_text(model: Path) -> str:
    return _ff(model).read_text(encoding="utf-8")


def test_fact_in_two_categories_is_handled_for_each(model):
    from ported_helpers import raw_deflate_b64
    import json
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    rows = [["Spend", "", "store_m"], ["Spend", "", "web_m"],
            ["Email Marketing Campaigns", "", "email_m"], ["Online", "", "web_m"]]
    b64 = raw_deflate_b64(json.dumps(rows, separators=(",", ":")).encode())
    zmap.write_text(re.sub(r'FromText\("[^"]+"', f'FromText("{b64}"', zmap.read_text(encoding="utf-8")),
                    encoding="utf-8")
    ff = _ff(model)
    ff.write_text(ff.read_text(encoding="utf-8").replace(
        "\tmeasure 'f-Email_Marketing' = 1\n",
        "\tmeasure 'f-Online' = 0\n\t\tisHidden\n\n\tmeasure 'f-Email_Marketing' = 1\n"), encoding="utf-8")
    assert f_filters.uncovered_facts(model) == {"Web Sales": ["Spend", "Online"]}
    run = forge("f-filters", "--model", model, "--no-backups")
    assert run.code == 0, run.text
    after = ff_text(model)
    assert "\tmeasure 'f-Online' = 0 + int(not ISEMPTY('Web Sales'))\n" in after
    assert "int(not ISEMPTY('Store Sales')) + int(not ISEMPTY('Web Sales'))" in after
    assert f_filters.uncovered_facts(model) == {}
    assert _chain(after, "temp_basic").count('CONTAINSSTRING(all_cats, "Online")') == 1


def test_fleet_processes_every_model_and_fails_on_a_bad_one(tmp_path):
    fleet = tmp_path / "fleet"
    good = copy_fixture("f_filters/Roastery.SemanticModel", fleet)
    (fleet / "Broken.SemanticModel").mkdir()
    run = forge("f-filters", "--fleet", fleet, "--no-backups")
    assert run.code == 1, run.text
    assert "error: no tables folder" in run.out
    assert BASIC_SPEND in ff_text(good)
    empty = tmp_path / "empty"
    empty.mkdir()
    run = forge("f-filters", "--fleet", empty)
    assert run.code == 1 and "no semantic model" in run.out


def test_gate_line_escapes_quotes_and_brackets():
    line = f_filters.gate_line('Say "Hi" Promos', "f-Promo]x", "basic")
    assert line == ('&& IF(CONTAINSSTRING(all_cats, "Say ""Hi"" Promos"), '
                    'IF([f-Promo]]x] > 0, TRUE(), FALSE()), TRUE())')
    assert f_filters.live_gate_names("\t\t\t" + line) == ['Say "Hi" Promos']


def test_category_with_a_quote_is_gated_once(model):
    from ported_helpers import raw_deflate_b64
    import json
    zmap = model / "definition" / "tables" / "z-Map Dimension-Measure Groupings.tmdl"
    rows = [["Spend", "", "store_m"], ["Spend", "", "web_m"],
            ["Email Marketing Campaigns", "", "email_m"], ['Say "Hi"', "", "hi_m"]]
    b64 = raw_deflate_b64(json.dumps(rows, separators=(",", ":")).encode())
    zmap.write_text(re.sub(r'FromText\("[^"]+"', f'FromText("{b64}"', zmap.read_text(encoding="utf-8")),
                    encoding="utf-8")
    ff = _ff(model)
    ff.write_text(ff.read_text(encoding="utf-8").replace(
        "\tmeasure 'f-Email_Marketing' = 1\n",
        "\tmeasure 'f-Say \"Hi\"' = 1\n\t\tisHidden\n\n\tmeasure 'f-Email_Marketing' = 1\n"), encoding="utf-8")
    assert forge("f-filters", "--model", model, "--no-backups").code == 0
    once = ff.read_bytes()
    assert once.count(b'CONTAINSSTRING(all_cats, "Say ""Hi""")') == 2
    second = forge("f-filters", "--model", model, "--no-backups")
    assert "no change" in second.out and ff.read_bytes() == once


def test_result_names_the_combined_gates_added(model):
    ff = _ff(model)
    text = re.sub(r"\tmeasure 'f-Spend' = ```.*?lineageTag: f-spend\n\n", "",
                  ff.read_text(encoding="utf-8"), flags=re.S)
    ff.write_text(text, encoding="utf-8")
    res = f_filters.fill_gaps(model, dry_run=True)
    assert res.combined_gates_added == ["Spend"]
    assert not hasattr(res, "f_all_extended")
