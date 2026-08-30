"""DEF-NULL-VALUE-GET-SWEEP — `.get(key, {})` does not defend against null.

`dict.get(key, default)` returns the default only when the key is **absent**.
The FranklinWH API returns many keys *present with a null value*, in which case
`.get(key, {})` hands back `None` and the next attribute access raises
"'NoneType' object has no attribute 'get'".

That is not hypothetical: it took out `diag`'s entire Gateway section on live
hardware (DEF-DIAG-GATEWAY-NONE-GUARD) and silently blanked the operating mode,
run status and SoC in the same report — those rendered as data, not as an error.

The sweep replaced every `x.get("k", {})` with `(x.get("k") or {})`. The
default value already declared the author's intent that the field is a dict or
a list, so the transform is correct by construction wherever it was written.
"""

import ast
import pathlib

import pytest

# Library core: parses gateway responses, so nulls arrive here first.
CORE = [
    "franklinwh_cloud/mixins",
    "franklinwh_cloud/discovery.py",
    "franklinwh_cloud/wrapper.py",
    "franklinwh_cloud/client.py",
    "franklinwh_cloud/heartbeat.py",
]

# CLI: renders those same responses, so the same nulls reach it second-hand.
CLI = [
    "franklinwh_cloud/cli.py",
    "franklinwh_cloud/cli_commands",
]


def _offenders(paths):
    """Sites passing an empty dict/list default to `.get()` — the unsafe form.

    Covers **any** key expression, not only string literals.

    The first version of this guard excluded variable keys, on the reasoning
    that those read local catalog JSON where a null would be a packaging fault.
    That reasoning was wrong, and a behavioural test caught it: `support.py`
    had `net.get(iface, {})` inside a `for iface in (...)` loop over an **API
    response**, which raised on a null exactly as the literal-keyed sites did.
    A lint scoped by the author's assumption cannot find the case the author
    did not think of.

    So every site is now swept and every site is guarded. For genuinely local
    tables the `or {}` is a harmless no-op; uniformity removes the judgement
    call rather than asking each reader to make it correctly.

    Calls already followed by `or {}` / `or []` are skipped — defended however
    the default is written.
    """
    found = []
    for entry in paths:
        p = pathlib.Path(entry)
        files = sorted(p.rglob("*.py")) if p.is_dir() else [p]
        for f in files:
            tree = ast.parse(f.read_text())
            guarded = {
                id(n.values[0]) for n in ast.walk(tree)
                if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or)
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if not (isinstance(fn, ast.Attribute) and fn.attr == "get"):
                    continue
                if len(node.args) != 2 or id(node) in guarded:
                    continue
                d = node.args[1]
                empty_dict = isinstance(d, ast.Dict) and not d.keys
                empty_list = isinstance(d, ast.List) and not d.elts
                if empty_dict or empty_list:
                    found.append(f"{f}:{node.lineno}")
    return found


def test_library_core_has_no_unsafe_get_defaults():
    offenders = _offenders(CORE)
    assert offenders == [], (
        "`.get(k, {})` returns None when the key is present-but-null. "
        f"Use `(x.get(k) or {{}})`. Offending sites: {offenders}"
    )


def test_cli_has_no_unsafe_get_defaults():
    offenders = _offenders(CLI)
    assert offenders == [], (
        "`.get(k, {})` returns None when the key is present-but-null. "
        f"Use `(x.get(k) or {{}})`. Offending sites: {offenders}"
    )


# ── the semantics the transform relies on ────────────────────────────

def test_get_with_default_does_not_defend_against_a_null_value():
    """The premise. If this ever changes, the sweep is unnecessary."""
    d = {"present_but_null": None}
    assert d.get("present_but_null", {}) is None
    assert d.get("absent", {}) == {}


def test_the_or_form_defends_against_both():
    d = {"present_but_null": None}
    assert (d.get("present_but_null") or {}) == {}
    assert (d.get("absent") or {}) == {}


@pytest.mark.parametrize("value", [{}, [], None])
def test_falsy_values_collapse_to_the_default_harmlessly(value):
    """The transform's only behaviour change, and why it is safe.

    `or` also replaces a legitimately-empty dict or list — with an equal one.
    For a field whose declared default is `{}` or `[]`, there is no value the
    substitution can destroy.
    """
    d = {"k": value}
    assert (d.get("k") or {}) == {}


def test_truthy_values_are_untouched():
    d = {"k": {"real": "data"}}
    assert (d.get("k") or {}) == {"real": "data"}


# ── behavioural: the renderers must survive an all-null payload ──────

def test_analyze_connectivity_survives_null_sections():
    """support.py held the largest concentration of the pattern (81 sites).

    A snapshot whose top-level sections are present but null is exactly the
    shape that broke diag's Gateway block.
    """
    from franklinwh_cloud.cli_commands.support import analyze_connectivity

    findings = analyze_connectivity({
        "connectivity": None,
        "network": None,
        "switches": None,
        "wifi_config": None,
    })
    assert isinstance(findings, list)


def test_analyze_connectivity_survives_null_nested_objects():
    from franklinwh_cloud.cli_commands.support import analyze_connectivity

    findings = analyze_connectivity({
        "connectivity": {"routerStatus": None, "netStatus": None,
                         "awsStatus": None},
        "network": {"currentNetType": None, "wifi": None, "eth0": None,
                    "eth1": None, "operator": None},
        "switches": {}, "wifi_config": {},
    })
    assert isinstance(findings, list)


def test_analyze_connectivity_survives_an_empty_snapshot():
    from franklinwh_cloud.cli_commands.support import analyze_connectivity

    assert isinstance(analyze_connectivity({}), list)
