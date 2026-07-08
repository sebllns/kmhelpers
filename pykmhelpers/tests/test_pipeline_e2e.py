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
        cmd = [sys.executable, "-m", CLI_MODULE] + [str(a) for a in args]
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
        """Merge every per-sub-index result JSON under ``results_dir``.

        Layout: ``<results_dir>/<query_stem>/result/<subindex>.json`` (the
        middle dir is named after the query file), each shaped
        ``{subindex: {query_header: {sample: fraction}}}``. Returns a flat dict
        ``{query_header: {sample: fraction}}`` merged across sub-indices.
        """
        base = self.tmp / results_dir
        self.assertTrue(base.is_dir(), f"query output dir not found: {base}")
        merged = {}
        json_files = sorted(
            p for p in base.rglob("*.json") if p.parent.name == "result"
        )
        self.assertTrue(json_files, f"no result JSON files under {base}")
        for jf in json_files:
            data = json.loads(jf.read_text())
            for per_query in data.values():
                for qheader, hits in per_query.items():
                    merged.setdefault(qheader, {}).update(hits)
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
