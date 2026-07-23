"""End-to-end pipeline tests driving the kmhelpers CLI.

These are *integration* tests: they invoke the real CLI (each command in a fresh
subprocess, ``python -m pykmhelpers.cli.kmhelpers``) which in turn shells out to
``kmindex`` and ``ntcard``. They assume those binaries are installed and
reachable (guaranteed in CI); there are no skip guards, so a missing binary
makes the tests fail loudly.

A subprocess per command is required (not click's ``CliRunner``): several
pipeline objects use process-global registries (e.g. ``IndexDB`` in
``pykmhelpers/pipeline/index_db.py`` keeps a class-level ``_instances`` dict),
so running multiple commands in one process leaks state across them (a second
command re-loading the same index definitions raises "already exists in
IndexDB"). A fresh process per command isolates that state.

Scenarios:
  * ``test_design_build_query_update_query`` -- the full super-command flow.
  * ``test_step_by_step_design_and_build``   -- list -> profile -> compose,
    then plan -> apply, mirroring docs/tutorials/ecoli_steps.md.
  * ``test_apply_chunks_and_merges_when_files_limit_too_low`` -- a low
    --limits open-files ceiling forces a chunked build+merge.
  * ``test_failures_exit_nonzero``           -- the failure paths exit non-zero.

Data is small random FASTA generated with a fixed seed. Queries are exact
substrings of an indexed sample, so a matching sample scores ~1.0 regardless of
the random content.
"""

import json
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Entry point for the CLI as a subprocess (module has a ``__main__`` guard).
CLI_MODULE = "pykmhelpers.cli.kmhelpers"

# Pipeline parameters kept small so the whole build runs in a few seconds.
SEED = 1234
N_SAMPLES = 5
SAMPLE_LEN = 2500
KMER_SIZE = 21
QUERY_START = 100
QUERY_LEN = 600
MIN_SCORE = 0.9


class PipelineE2EBase(unittest.TestCase):
    """Shared fixture: generate a tiny random dataset and drive the CLI."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_e2e_"))

        # Deterministic random sequences.
        random.seed(SEED)
        self.sequences = []
        data_dir = self.tmp / "data"
        data_dir.mkdir()
        sample_paths = []
        for i in range(N_SAMPLES):
            seq = "".join(random.choice("ACGT") for _ in range(SAMPLE_LEN))
            self.sequences.append(seq)
            path = data_dir / f"sample_{i}.fasta"
            path.write_text(f">sample_{i}\n{seq}\n")
            sample_paths.append(str(path.resolve()))

        # Sample list file (one path per line), like the tutorial's coli_10.txt.
        self.samples_txt = self.tmp / "samples.txt"
        self.samples_txt.write_text("\n".join(sample_paths) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers -----------------------------------------------------------

    def run_cli(self, *args, expect_success=True):
        """Run one CLI command in a fresh subprocess; assert the exit code."""
        # -v is a top-level group option, so it precedes the subcommand.
        cmd = [sys.executable, "-m", CLI_MODULE, "-v"] + [str(a) for a in args]
        proc = subprocess.run(cmd, cwd=self.tmp, capture_output=True, text=True)
        pretty = "kmhelpers " + " ".join(str(a) for a in args)
        if expect_success:
            self.assertEqual(
                proc.returncode,
                0,
                msg=(
                    f"`{pretty}` failed (exit {proc.returncode}).\n"
                    f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
                ),
            )
        else:
            self.assertNotEqual(
                proc.returncode,
                0,
                msg=(
                    f"`{pretty}` was expected to fail but exited 0.\n"
                    f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
                ),
            )
        return proc

    def mkdirs(self, *relparts):
        """Create a directory (and parents) under the temp workdir."""
        d = self.tmp.joinpath(*relparts)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_query(self, name, sample_idx, start=QUERY_START, length=QUERY_LEN):
        """Write a query FASTA that is an exact substring of ``sample_idx``.

        Returns (query_path, query_header).
        """
        header = f"q_{name}"
        seq = self.sequences[sample_idx][start : start + length]
        path = self.tmp / f"query_{name}.fa"
        path.write_text(f">{header}\n{seq}\n")
        return path, header

    def load_query_results(self, results_dir):
        """Merge every per-sub-index result JSONL under ``results_dir``.

        Layout: ``<results_dir>/<query_stem>/result/<subindex>.jsonl`` (the
        middle dir is named after the query file), one record per line shaped
        ``{"index": ..., "query": query_header, "samples": {sample: fraction}}``.
        Returns a flat dict ``{query_header: {sample: fraction}}`` merged across
        sub-indices.
        """
        base = self.tmp / results_dir
        self.assertTrue(base.is_dir(), f"query output dir not found: {base}")
        merged = {}
        jsonl_files = sorted(
            p for p in base.rglob("*.jsonl") if p.parent.name == "result"
        )
        self.assertTrue(jsonl_files, f"no result JSONL files under {base}")
        for jf in jsonl_files:
            for line in jf.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                merged.setdefault(record["query"], {}).update(record["samples"])
        return merged

    def assert_query_hit(self, results_dir, query_header, sample, min_score=MIN_SCORE):
        merged = self.load_query_results(results_dir)
        self.assertIn(query_header, merged, f"query {query_header} absent from results")
        self.assertIn(
            sample,
            merged[query_header],
            f"{sample} not matched for {query_header}; got {merged[query_header]}",
        )
        self.assertGreaterEqual(merged[query_header][sample], min_score)


class TestDesignBuildQueryUpdateQuery(PipelineE2EBase):
    """Full super-command flow: design -> build -> query -> update -> query."""

    def test_design_build_query_update_query(self):
        # 1. design (list -> profile -> compose)
        self.run_cli(
            "design",
            self.samples_txt,
            "-o",
            "db",
            "-n",
            "idx",
            "-S",
            "initial",
            "-k",
            KMER_SIZE,
            "-b",
            "1.1",
            "-g",
            "1",
        )
        layout = self.tmp / "db" / "compose" / "idx_layout.yaml"
        span_reg = self.tmp / "db" / "compose" / "idx" / "initial" / "idx.yaml"
        self.assertTrue(layout.is_file(), f"missing layout: {layout}")
        self.assertTrue(span_reg.is_file(), f"missing span registry: {span_reg}")

        # 2. build (plan -> apply)
        self.run_cli("build", span_reg, "-o", "build")
        index_json = self.tmp / "build" / "index.json"
        self.assertTrue(index_json.is_file(), "build did not produce index.json")
        self.assertTrue(
            any((self.tmp / "build" / "kmindex_data").iterdir()),
            "kmindex_data is empty",
        )

        # 3. query a substring of sample_0 -> perfect match
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")

        # 4. update: add a new sample, compose it against the existing layout
        #    (no -pf), and rebuild into the same work dir. The new sample must
        #    fit an existing span bucket, so keep it a bit smaller than the
        #    initial samples (ntcard k-mer estimates are noisy, so leave margin).
        random.seed(SEED + 1)
        new_seq = "".join(random.choice("ACGT") for _ in range(SAMPLE_LEN - 400))
        self.sequences.append(new_seq)  # index N_SAMPLES == "sample_new"
        new_path = self.tmp / "data" / "sample_new.fasta"
        new_path.write_text(f">sample_new\n{new_seq}\n")
        new_list = self.tmp / "new_samples.txt"
        new_list.write_text(str(new_path.resolve()) + "\n")

        self.mkdirs("db", "list")
        self.run_cli("list", new_list, "-o", "db/list/upd.jsonl", "-k", KMER_SIZE)
        self.run_cli(
            "compose", "db/list/upd.jsonl", "-o", "db/compose", "-n", "idx", "-S", "upd"
        )
        upd_reg = self.tmp / "db" / "compose" / "idx" / "upd" / "idx.yaml"
        self.assertTrue(upd_reg.is_file(), f"update compose missing: {upd_reg}")
        self.run_cli("build", upd_reg, "-o", "build")

        # 5. the new sample is now queryable, and the original still matches.
        qn, qn_header = self.write_query("snew", sample_idx=N_SAMPLES)
        self.run_cli("query", qn, "-r", "build", "-o", "results_upd", "-f", "json")
        self.assert_query_hit("results_upd", qn_header, "sample_new")

        self.run_cli("query", q0, "-r", "build", "-o", "results_after", "-f", "json")
        self.assert_query_hit("results_after", q0_header, "sample_0")


class TestStepByStepDesignAndBuild(PipelineE2EBase):
    """Decomposed flow: list -> profile -> compose, then plan -> apply."""

    def test_step_by_step_design_and_build(self):
        # design, decomposed (list does not create its output parent dir)
        self.mkdirs("db", "list")
        self.run_cli(
            "list", self.samples_txt, "-o", "db/list/idx.jsonl", "-k", KMER_SIZE
        )
        jsonl = self.tmp / "db" / "list" / "idx.jsonl"
        self.assertTrue(jsonl.is_file(), "list did not produce the jsonl")
        # one record per sample (plus a header line)
        record_lines = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
        self.assertGreaterEqual(len(record_lines), N_SAMPLES)

        self.run_cli("profile", jsonl, "-o", "db/profile", "-g", "1", "-b", "1.1")
        self.assertTrue(
            (self.tmp / "db" / "profile" / "profile.yaml").is_file(),
            "profile.yaml missing",
        )

        self.run_cli(
            "compose",
            jsonl,
            "-o",
            "db/compose",
            "-n",
            "idx",
            "-S",
            "initial",
            "-pf",
            "db/profile/profile.yaml",
        )
        span_reg = self.tmp / "db" / "compose" / "idx" / "initial" / "idx.yaml"
        self.assertTrue(span_reg.is_file(), f"missing span registry: {span_reg}")

        # build, decomposed
        self.run_cli("plan", span_reg, "-o", "build2")
        self.assertTrue(
            (self.tmp / "build2" / "assets" / "kmhelpers_apply.sh").is_file(),
            "plan did not write the build script",
        )
        self.run_cli("apply", span_reg, "-o", "build2")
        self.assertTrue(
            (self.tmp / "build2" / "index.json").is_file(),
            "apply did not produce index.json",
        )

        # query
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build2", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")


class TestChunkedBuild(PipelineE2EBase):
    """A too-low --limits open-files ceiling splits a build into chunks."""

    def test_apply_chunks_and_merges_when_files_limit_too_low(self):
        # A wide span base (-b 4) buckets all N_SAMPLES samples into one
        # group, so the group's build is what gets constrained by --limits.
        self.run_cli(
            "design",
            self.samples_txt,
            "-o",
            "db",
            "-n",
            "idx",
            "-S",
            "initial",
            "-k",
            KMER_SIZE,
            "-b",
            "4",
            "-g",
            "1",
        )
        span_reg = self.tmp / "db" / "compose" / "idx" / "initial" / "idx.yaml"
        self.assertTrue(span_reg.is_file(), f"missing span registry: {span_reg}")

        # files=5 can't fit N_SAMPLES=5 samples in one kmtricks build (merge
        # stage needs samples+1 open files), forcing a chunked build+merge.
        self.run_cli("apply", span_reg, "-o", "build", "--limits", '{"files": 5}')

        index_json = self.tmp / "build" / "index.json"
        self.assertTrue(index_json.is_file(), "apply did not produce index.json")
        registry = json.loads(index_json.read_text())["index"]

        chunk_names = [name for name in registry if "__chunk" in name]
        self.assertFalse(
            chunk_names, f"transient chunk sub-indexes left registered: {chunk_names}"
        )
        merged = next(iter(registry.values()))
        self.assertEqual(merged["nb_samples"], N_SAMPLES)

        # every original sample must still be queryable after the chunked merge
        for idx in range(N_SAMPLES):
            q, header = self.write_query(f"s{idx}", sample_idx=idx)
            self.run_cli(
                "query", q, "-r", "build", "-o", f"results_{idx}", "-f", "json"
            )
            self.assert_query_hit(f"results_{idx}", header, f"sample_{idx}")


class TestDirectoryScanBuildQueryUpdateQuery(PipelineE2EBase):
    """Directory-scan flow: scan a dir -> build -> query -> update -> query.

    Samples live in subdirectories, so the JSONL stores paths *relative* to the
    scanned root (e.g. ``s1/sample_1.fasta``); every stage must resolve them
    against the header ``root_path`` regardless of cwd.
    """

    def _write_tree(self, root, indices):
        """Write ``sample_{i}.fasta`` under ``root/s{i}/`` for each i in indices."""
        for i in indices:
            d = self.mkdirs(*root, f"s{i}")
            (d / f"sample_{i}.fasta").write_text(f">sample_{i}\n{self.sequences[i]}\n")
        return self.tmp.joinpath(*root)

    def test_scan_dir_build_query_update_query(self):
        # 1. list by scanning a directory tree (default: one sample per file).
        scan_data = self._write_tree(("scan_data",), range(N_SAMPLES))
        self.mkdirs("db", "list")
        self.run_cli("list", scan_data, "-o", "db/list/idx.jsonl", "-k", KMER_SIZE)

        jsonl = self.tmp / "db" / "list" / "idx.jsonl"
        lines = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
        header = json.loads(lines[0])
        self.assertEqual(header.get("root_path"), str(scan_data.resolve()))
        records = [json.loads(ln) for ln in lines[1:]]
        self.assertEqual(len(records), N_SAMPLES)
        # Stored paths are relative to the scanned root (not absolute).
        for rec in records:
            for f in rec["files"]:
                self.assertFalse(f.startswith("/"), f"expected relative path: {f}")

        # 2. profile -> compose -> build
        self.run_cli("profile", jsonl, "-o", "db/profile", "-g", "1", "-b", "1.1")
        self.run_cli(
            "compose",
            jsonl,
            "-o",
            "db/compose",
            "-n",
            "idx",
            "-S",
            "initial",
            "-pf",
            "db/profile/profile.yaml",
        )
        span_reg = self.tmp / "db" / "compose" / "idx" / "initial" / "idx.yaml"
        self.assertTrue(span_reg.is_file(), f"missing span registry: {span_reg}")
        self.run_cli("build", span_reg, "-o", "build")
        self.assertTrue(
            (self.tmp / "build" / "index.json").is_file(),
            "build did not produce index.json",
        )

        # 3. query a substring of sample_0 -> perfect match
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")

        # 4. update: scan a separate dir holding one new sample, compose against
        #    the existing layout (no -pf), and rebuild into the same work dir.
        #    Keep the new sample smaller so it fits an existing span bucket.
        random.seed(SEED + 1)
        new_seq = "".join(random.choice("ACGT") for _ in range(SAMPLE_LEN - 400))
        self.sequences.append(new_seq)  # index N_SAMPLES == "sample_new"
        upd_dir = self.mkdirs("scan_upd", "snew")
        (upd_dir / "sample_new.fasta").write_text(f">sample_new\n{new_seq}\n")

        self.run_cli(
            "list", self.tmp / "scan_upd", "-o", "db/list/upd.jsonl", "-k", KMER_SIZE
        )
        self.run_cli(
            "compose", "db/list/upd.jsonl", "-o", "db/compose", "-n", "idx", "-S", "upd"
        )
        upd_reg = self.tmp / "db" / "compose" / "idx" / "upd" / "idx.yaml"
        self.assertTrue(upd_reg.is_file(), f"update compose missing: {upd_reg}")
        self.run_cli("build", upd_reg, "-o", "build")

        # 5. the new sample is queryable, and the original still matches.
        qn, qn_header = self.write_query("snew", sample_idx=N_SAMPLES)
        self.run_cli("query", qn, "-r", "build", "-o", "results_upd", "-f", "json")
        self.assert_query_hit("results_upd", qn_header, "sample_new")

        self.run_cli("query", q0, "-r", "build", "-o", "results_after", "-f", "json")
        self.assert_query_hit("results_after", q0_header, "sample_0")


class TestListLeafGrouping(PipelineE2EBase):
    """`list --leaf-grouping` alone: each leaf folder becomes one grouped sample."""

    def test_scan_dir_leaf_grouping_groups_by_folder(self):
        # Two leaf folders, two files each.
        groups = {"g0": (0, 1), "g1": (2, 3)}
        for folder, idxs in groups.items():
            d = self.mkdirs("grp_data", folder)
            for i in idxs:
                (d / f"sample_{i}.fasta").write_text(
                    f">sample_{i}\n{self.sequences[i]}\n"
                )
        grp_data = self.tmp / "grp_data"

        self.mkdirs("db", "list")
        self.run_cli(
            "list", grp_data, "-o", "db/list/grp.jsonl", "-lg", "-k", KMER_SIZE
        )

        lines = [
            ln
            for ln in (self.tmp / "db" / "list" / "grp.jsonl").read_text().splitlines()
            if ln.strip()
        ]
        header = json.loads(lines[0])
        self.assertEqual(header.get("root_path"), str(grp_data.resolve()))

        records = {r["name"]: r for r in (json.loads(ln) for ln in lines[1:])}
        self.assertEqual(set(records), set(groups), f"unexpected samples: {records}")
        for folder, idxs in groups.items():
            rec = records[folder]
            files = sorted(rec["files"])
            self.assertEqual(
                files, [f"{folder}/sample_{i}.fasta" for i in sorted(idxs)]
            )
            # Counting resolved the relative paths against root_path.
            self.assertGreater(rec.get("kmer_count", 0), 0)


class TestPipelineFailuresExitNonzero(PipelineE2EBase):
    """The fixed exit-code contract: failures must exit non-zero."""

    def test_compose_update_without_layout_fails(self):
        # First produce a jsonl to feed compose.
        self.mkdirs("db", "list")
        self.run_cli(
            "list", self.samples_txt, "-o", "db/list/idx.jsonl", "-k", KMER_SIZE
        )
        # Update mode (no -pf) with no existing <name>_layout.yaml -> non-zero.
        self.run_cli(
            "compose",
            "db/list/idx.jsonl",
            "-o",
            "db/compose",
            "-n",
            "idx",
            expect_success=False,
        )

    def test_list_nonexistent_input_fails(self):
        self.run_cli(
            "list",
            "does/not/exist.txt",
            "-o",
            "out.jsonl",
            "-k",
            KMER_SIZE,
            expect_success=False,
        )


if __name__ == "__main__":
    unittest.main()
