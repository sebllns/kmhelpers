"""Unit tests for the open-files limit helpers (no limit is changed)."""

import resource
import unittest
from unittest import mock

from pykmhelpers.core import resources
from pykmhelpers.core.resources import (
    NOFILE_CEILING,
    get_max_open_files,
    maximize_nofile,
)

NOFILE = resource.RLIMIT_NOFILE


class TestMaxOpenFiles(unittest.TestCase):
    def test_uses_the_hard_limit(self):
        with mock.patch.object(resources, "get_ulimit", return_value=(1024, 131072)):
            self.assertEqual(get_max_open_files(), 131072)
            self.assertEqual(get_max_open_files(0.5), 65536)

    def test_unlimited_hard_limit_is_capped(self):
        limits = (1024, resource.RLIM_INFINITY)
        with mock.patch.object(resources, "get_ulimit", return_value=limits):
            self.assertEqual(get_max_open_files(), NOFILE_CEILING)


class TestMaximizeNofile(unittest.TestCase):
    def patch(self, limits, setrlimit):
        state = {"limits": limits}

        def getrlimit(kind):
            self.assertEqual(kind, NOFILE)
            return state["limits"]

        def set_limits(kind, value):
            setrlimit(value)
            state["limits"] = value

        return (
            mock.patch.object(resources.resource, "getrlimit", side_effect=getrlimit),
            mock.patch.object(resources.resource, "setrlimit", side_effect=set_limits),
        )

    @staticmethod
    def not_root(value):
        if value[1] == resource.RLIM_INFINITY:
            raise ValueError("not allowed to raise maximum limit")

    def test_raises_soft_to_hard_and_logs(self):
        get, set_ = self.patch((1024, 131072), self.not_root)
        with get, set_, self.assertLogs(resources.logger, level="DEBUG") as logs:
            self.assertEqual(maximize_nofile(), 131072)
        self.assertIn("open files: soft 1024 -> 131072 (hard 131072)", logs.output[0])

    def test_already_at_hard(self):
        get, set_ = self.patch((131072, 131072), self.not_root)
        with get, set_, self.assertLogs(resources.logger, level="DEBUG") as logs:
            self.assertEqual(maximize_nofile(), 131072)
        self.assertIn("soft already at hard (131072)", logs.output[0])

    def test_failure_is_a_warning(self):
        def refuse(value):
            raise ValueError("refused")

        get, set_ = self.patch((1024, 131072), refuse)
        with get, set_, self.assertLogs(resources.logger, level="WARNING") as logs:
            self.assertEqual(maximize_nofile(), 1024)
        self.assertIn("Could not raise the open-files limit", logs.output[0])


if __name__ == "__main__":
    unittest.main()
