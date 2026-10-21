"""Unit tests for the CLI help: -H, --HELP lists hidden options, -h does not."""

import unittest

import click
from click.testing import CliRunner

from pykmhelpers.cli.kmhelpers import cli


def _walk(cmd, path=()):
    yield path, cmd
    for name, sub in getattr(cmd, "commands", {}).items():
        yield from _walk(sub, path + (name,))


class TestFullHelp(unittest.TestCase):
    def test_full_help_lists_hidden_options(self):
        runner = CliRunner()
        short = runner.invoke(cli, ["design", "-h"])
        full = runner.invoke(cli, ["design", "-H"])
        self.assertEqual((short.exit_code, full.exit_code), (0, 0))
        self.assertNotIn("--shard-budget-bytes", short.output)
        self.assertIn("--shard-budget-bytes", full.output)
        self.assertIn("[hidden]", full.output)
        # the options are hidden again afterwards
        self.assertNotIn("[hidden]", runner.invoke(cli, ["design", "-h"]).output)

    def test_every_command_has_full_help(self):
        for path, cmd in _walk(cli):
            names = {o for p in cmd.params for o in getattr(p, "opts", [])}
            self.assertIn("-H", names, " ".join(path) or "root")
            self.assertIn("--HELP", names, " ".join(path) or "root")


class TestOptionCase(unittest.TestCase):
    """Uppercase short flags for global options only, except -H and kept capitals."""

    KEPT = {("compose", "-P"), ("design", "-P")}

    def test_command_options_are_lowercase(self):
        for path, cmd in _walk(cli):
            if not path:
                continue
            for p in cmd.params:
                if not isinstance(p, click.Option):
                    continue
                for o in p.opts + p.secondary_opts:
                    if o in ("-H", "--HELP") or (path[-1], o) in self.KEPT:
                        continue
                    if len(o) <= 5:  # short flags: -x, --xyz
                        self.assertEqual(o, o.lower(), f"{' '.join(path)} {o}")

    def test_global_short_flags_are_uppercase(self):
        for p in cli.params:
            for o in getattr(p, "opts", []) + getattr(p, "secondary_opts", []):
                if not o.startswith("--"):
                    self.assertEqual(o, o.upper(), o)


if __name__ == "__main__":
    unittest.main()
