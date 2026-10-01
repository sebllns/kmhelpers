"""Unit tests for the index map (kmhelpers map)."""

import json
import os
import tempfile
import unittest

import yaml
from click.testing import CliRunner

from pykmhelpers.cli.map import map_cmd
from pykmhelpers.pipeline.index_map import (
    ACTIVE,
    BROKEN,
    EXTERNAL_SESSION,
    MISSING,
    ORPHAN,
    SUPERSEDED,
    build_map,
    render_text,
)


def make_index_dir(path, samples, k=21, parts=2, compressed=False):
    os.makedirs(os.path.join(path, "matrices"))
    with open(os.path.join(path, "options.txt"), "w") as f:
        f.write(f"Options: dir={path}, kmer_size={k}, nb_parts={parts}")
    with open(os.path.join(path, "kmtricks.fof"), "w") as f:
        f.writelines(f"{s}: /data/{s}.fa\n" for s in samples)
    for p in range(parts):
        name = f"blocks_{p}" if compressed else f"matrix_{p}.cmbf"
        with open(os.path.join(path, "matrices", name), "wb") as f:
            f.write(b"\0" * 100)


def write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


def write_session(compose_dir, session, indices):
    """indices: {name: (span, sample_count)}, one sub-index per name."""
    session_dir = os.path.join(compose_dir, "db", session)
    spans = {}
    for name, (span, count) in indices.items():
        sub = f"{name}_{session}"
        spans.setdefault(span, {"indices": {}})["indices"][name] = [sub]
        write_yaml(
            os.path.join(session_dir, f"{sub}.yaml"),
            {
                "type": "index",
                "data": {sub: {"parameters": {"kmer_size": "21"}, "infos": {"sample_count": count}}},
            },
        )
    write_yaml(os.path.join(session_dir, "db.yaml"), {"type": "span", "data": spans})


class TestIndexMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.build = os.path.join(root, "build")
        self.compose = os.path.join(root, "compose")
        data = os.path.join(self.build, "kmindex_data")

        # a: built in s1 then s2 (s2 active); b: built in s1, declared in s2 but not built
        make_index_dir(os.path.join(data, "s1", "a"), ["x1", "x2"])
        make_index_dir(os.path.join(data, "s2", "a"), ["x1", "x2", "x3"], compressed=True)
        make_index_dir(os.path.join(data, "s1", "b"), ["y1"])
        # c: built but never declared
        make_index_dir(os.path.join(data, "s1", "c"), ["z1"])
        os.symlink(os.path.join(data, "s2", "a"), os.path.join(self.build, "a"))
        os.symlink(os.path.join(data, "s1", "b"), os.path.join(self.build, "b"))
        os.symlink(os.path.join(root, "nowhere"), os.path.join(self.build, "d"))
        with open(os.path.join(self.build, "index.json"), "w") as f:
            json.dump({"index": {"a": {"nb_samples": 3}, "b": {}, "d": {}}}, f)

        write_session(self.compose, "s1", {"a": (80, 2), "b": (90, 1)})
        write_session(self.compose, "s2", {"a": (80, 1), "b": (90, 4)})

    def tearDown(self):
        self.tmp.cleanup()

    def status(self, index_map, name, session):
        return index_map.cells[(name, session)].status

    def test_statuses_with_compose(self):
        m = build_map(self.build, self.compose)
        self.assertEqual(self.status(m, "a", "s1"), SUPERSEDED)
        self.assertEqual(self.status(m, "a", "s2"), ACTIVE)
        self.assertEqual(self.status(m, "b", "s1"), ACTIVE)
        self.assertEqual(self.status(m, "b", "s2"), MISSING)
        self.assertEqual(self.status(m, "c", "s1"), ORPHAN)
        self.assertEqual(self.status(m, "d", EXTERNAL_SESSION), BROKEN)
        self.assertEqual(m.sessions[-1], EXTERNAL_SESSION)
        self.assertEqual(m.names[:2], ["a", "b"])

    def test_cell_details(self):
        m = build_map(self.build, self.compose)
        active = m.cells[("a", "s2")]
        self.assertEqual((active.samples, active.kmer_size, active.partitions), (3, 21, 2))
        self.assertEqual((active.size, active.compression), (200, "C"))
        self.assertEqual(m.cells[("a", "s1")].compression, "U")
        self.assertEqual(m.cells[("b", "s2")].samples, 4)
        self.assertEqual(m.cells[("b", "s2")].span, 90)

    def test_without_compose(self):
        m = build_map(self.build)
        self.assertEqual(self.status(m, "c", "s1"), SUPERSEDED)
        self.assertNotIn(("b", "s2"), m.cells)
        self.assertIn("superseded (2)", render_text(m))

    def test_missing_index_json(self):
        os.remove(os.path.join(self.build, "index.json"))
        with self.assertRaises(FileNotFoundError):
            build_map(self.build)

    def test_cli_outputs(self):
        out = os.path.join(self.tmp.name, "map.png")
        runner = CliRunner()
        result = runner.invoke(map_cmd, [self.build, "-c", self.compose, "-o", out])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("missing (4)", result.output)
        self.assertGreater(os.path.getsize(out), 0)

        result = runner.invoke(map_cmd, [self.build, "--json"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["sessions"][0], "s1")


if __name__ == "__main__":
    unittest.main()
