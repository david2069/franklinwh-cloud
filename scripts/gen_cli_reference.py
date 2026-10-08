"""Generate the command tables in docs/CLI_COMMAND_REFERENCE.md from the CLI parser.

Usage:
    python scripts/gen_cli_reference.py          # rewrite the generated section
    python scripts/gen_cli_reference.py --check  # exit 1 if the doc is stale

tests/test_cli_reference.py runs the check, so the page can't drift from the CLI.
"""

import argparse
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC = os.path.join(REPO, "docs", "CLI_COMMAND_REFERENCE.md")
BEGIN = "<!-- BEGIN GENERATED: cli commands -->\n"
END = "<!-- END GENERATED: cli commands -->"

# Commands with a detailed guide of their own
GUIDES = {
    "energy": "cli-energy.md",
    "tou": "CLI_TOU_COMMAND.md",
    "schema": "CLI_SCHEMA_COMMAND.md",
    "raw": "cli-raw.md",
    "support": "CLI_SUPPORT_INFO.md",
}


def _cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _option_rows(parser):
    rows = []
    for a in parser._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        name = ", ".join(f"`{o}`" for o in a.option_strings) if a.option_strings else f"`{a.dest}` (positional)"
        if a.choices and not isinstance(a.choices, dict):
            value = "`" + "\\|".join(str(c) for c in a.choices) + "`"
        elif a.nargs == 0:
            value = "flag"
        else:
            value = f"`{a.metavar or a.dest.upper()}`"
        default = a.default
        default = "—" if default in (None, False, argparse.SUPPRESS) else f"`{default}`"
        rows.append(f"| {name} | {value} | {default} | {_cell(a.help)} |")
    return rows


def _table(parser):
    rows = _option_rows(parser)
    if not rows:
        return ["No options."]
    return ["| Option | Value | Default | Description |", "|---|---|---|---|", *rows]


def _subcommands(parser):
    """[(names, help, subparser)] in definition order, aliases grouped."""
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not actions:
        return []
    action = actions[0]
    helps = {c.dest: c.help for c in action._choices_actions}
    seen, out = {}, []
    for name, sp in action.choices.items():
        if id(sp) in seen:
            seen[id(sp)][0].append(name)
            continue
        entry = ([name], helps.get(name, ""), sp)
        seen[id(sp)] = entry
        out.append(entry)
    return out


def render():
    from franklinwh_cloud.cli import build_parser

    parser = build_parser()
    lines = ["## Global options", "",
             "These go before or after the command (e.g. `franklinwh-cli --json status` or "
             "`franklinwh-cli status --json`).", "", *_table(parser), "",
             "## Commands", "", "| Command | Aliases | What it does | Guide |", "|---|---|---|---|"]
    commands = _subcommands(parser)
    for names, help_, _ in commands:
        guide = f"[guide]({GUIDES[names[0]]})" if names[0] in GUIDES else "—"
        aliases = ", ".join(f"`{n}`" for n in names[1:]) or "—"
        lines.append(f"| [`{names[0]}`](#{names[0]}) | {aliases} | {_cell(help_)} | {guide} |")
    lines.append("")
    for names, help_, sp in commands:
        lines += [f"### {names[0]}", "", _cell(help_) + ".", "",
                  f"```\nfranklinwh-cli {names[0]} [options]\n```", ""]
        if names[0] in GUIDES:
            lines += [f"Detailed guide: [{GUIDES[names[0]]}]({GUIDES[names[0]]})", ""]
        lines += [*_table(sp), ""]
        for sub_names, sub_help, ssp in _subcommands(sp):
            lines += [f"#### {names[0]} {sub_names[0]}", "", _cell(sub_help) + ".", "",
                      *_table(ssp), ""]
    return "\n".join(lines)


def main():
    sys.path.insert(0, REPO)
    doc = open(DOC, encoding="utf-8").read()
    head, rest = doc.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    new = head + BEGIN + render() + "\n" + END + tail
    if "--check" in sys.argv:
        if new != doc:
            print("docs/CLI_COMMAND_REFERENCE.md is stale: run python scripts/gen_cli_reference.py")
            return 1
        return 0
    with open(DOC, "w", encoding="utf-8") as fh:
        fh.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
