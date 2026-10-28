"""Unit tests for the shared confirmation prompt."""

import unittest
from unittest import mock

import click

from pykmhelpers.cli import shared


def _ctx(yes: bool = False) -> click.Context:
    return click.Context(click.Command("test"), obj={"yes": yes})


class TestConfirm(unittest.TestCase):
    def test_yes_answers_without_asking(self):
        with mock.patch("click.confirm") as ask:
            self.assertTrue(shared.confirm(_ctx(yes=True), "Overwrite?"))
        ask.assert_not_called()

    def test_no_terminal_refuses_with_hint(self):
        with mock.patch.object(shared, "interactive", return_value=False):
            with self.assertRaises(click.ClickException) as e:
                shared.confirm(_ctx(), "Overwrite?")
        self.assertIn("-Y", e.exception.message)

    def test_no_terminal_unattended_proceeds(self):
        with mock.patch.object(shared, "interactive", return_value=False):
            self.assertTrue(shared.confirm(_ctx(), "Build it?", unattended=True))

    def test_terminal_returns_the_answer(self):
        with mock.patch.object(shared, "interactive", return_value=True):
            for answer in (True, False):
                with mock.patch("click.confirm", return_value=answer) as ask:
                    self.assertIs(shared.confirm(_ctx(), "Overwrite?", default=True), answer)
                ask.assert_called_once_with("Overwrite?", default=True)

    def test_not_interactive_under_test_runner(self):
        """stdin is not a terminal under pytest: no prompt can be answered."""
        with mock.patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(shared.interactive())


if __name__ == "__main__":
    unittest.main()
