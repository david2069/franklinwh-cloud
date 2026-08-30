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


def _offenders(paths):
    """Sites matching the swept pattern: `x.get("literal", {})`.

    Scoped deliberately to **string-literal** keys, which is what the sweep
    covered and where the risk lives — those are API response fields, and the
    API is what returns present-but-null. Sites keyed on a variable
    (`catalog["agate_models"].get(str(hw_ver), {})`) read local catalog JSON
    that this project ships, so a null value there would be a packaging fault
    rather than an upstream surprise. Widening this guard to cover them would
    flag code the sweep intentionally left alone.

    Also skips calls already followed by `or {}` / `or []`, which are defended
    however the default is written.
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
                if len(node.args) != 2:
                    continue
                key = node.args[0]
                if not (isinstance(key, ast.Constant)
                        and isinstance(key.value, str)):
                    continue                      # variable key — out of scope
                if id(node) in guarded:
                    continue                      # already `... or {}`
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
