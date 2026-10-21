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
  * ``test_query_fasta_fastq_plain_and_gz`` -- query in every FASTA/FASTQ form.
  * ``test_failures_exit_nonzero``           -- the failure paths exit non-zero.

Data is small random FASTA generated with a fixed seed. Queries are exact
substrings of an indexed sample, so a matching sample scores ~1.0 regardless of
the random content.
"""

import gzip
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

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
            p for p in base.rglob("*.jsonl") if p.parent.name == "kmindex_output"
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

    def assert_in_place(self, build_dir):
        """Every registered index is a directory of BUILD_DIR; no session leftovers."""
        build = self.tmp / build_dir
        registry = json.loads((build / "index.json").read_text())["index"]
        self.assertTrue(registry, "nothing registered")
        for name in registry:
            entry = build / name
            self.assertTrue(
                entry.is_dir() and not entry.is_symlink(), f"{name} is not in place"
            )
        self.assertFalse((build / "kmindex_data").exists(), "kmindex_data created")
        self.assertFalse((build / "work").exists(), "work dir left")

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
        layout = self.tmp / "db" / "compose" / "idx" / "layout.yaml"
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.assertTrue(layout.is_file(), f"missing layout: {layout}")
        self.assertTrue(session_file.is_file(), f"missing session file: {session_file}")

        # 2. build (plan -> apply) the design directory: its only session
        self.run_cli("build", "db", "-o", "build")
        index_json = self.tmp / "build" / "index.json"
        self.assertTrue(index_json.is_file(), "build did not produce index.json")
        self.assert_in_place("build")

        # 3. query a substring of sample_0 -> perfect match
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")

        # 4. update: add a new sample, compose it against the existing layout
        #    (no --pf), and rebuild into the same work dir. The new sample must
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
        upd_session = self.tmp / "db" / "compose" / "idx" / "upd" / "index.yaml"
        self.assertTrue(upd_session.is_file(), f"update compose missing: {upd_session}")
        layout = (self.tmp / "db" / "compose" / "idx" / "layout.yaml").read_text()
        self.assertIn("- upd", layout)
        # build the session by name (it is also the last one)
        self.run_cli("build", "db", "-o", "build", "-S", "upd")
        # building the first session again changes nothing
        self.run_cli("build", "db", "-o", "build", "-S", "initial")

        # 5. the new sample is now queryable, and the original still matches.
        qn, qn_header = self.write_query("snew", sample_idx=N_SAMPLES)
        self.run_cli("query", qn, "-r", "build", "-o", "results_upd", "-f", "json")
        self.assert_query_hit("results_upd", qn_header, "sample_new")

        self.run_cli("query", q0, "-r", "build", "-o", "results_after", "-f", "json")
        self.assert_query_hit("results_after", q0_header, "sample_0")
        self.assert_in_place("build")


class TestAbundanceDesignBuildQuery(PipelineE2EBase):
    """design --ab 2 -> build -> query: the index stores 2 bits per sample."""

    def test_abundance_design_build_query(self):
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
            "--ab",
            "2",
        )
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        definition = (session_file.parent / "shards" / "idx_g0_p0.yaml").read_text()
        self.assertIn("bitw: '2'", definition)
        self.assertIn("kmindex-abundance", definition)

        self.run_cli("build", session_file, "-o", "build")
        self.assert_in_place("build")
        registry = json.loads((self.tmp / "build" / "index.json").read_text())
        for name, entry in registry["index"].items():
            self.assertEqual(entry["bw"], 2, f"{name} is not an abundance index")

        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        merged = self.load_query_results("results")
        self.assertIn(q0_header, merged)
        self.assertGreater(merged[q0_header].get("sample_0", 0), 0)

        # a presence/absence session cannot be merged into the abundance index
        self.run_cli(
            "compose",
            self.tmp / "db" / "list" / "samples_initial.jsonl",
            "-o",
            "db/compose",
            "-n",
            "idx",
            "-S",
            "pa",
            "--ab",
            "0",
            expect_success=False,
        )
        # without --ab, an update takes the layout's bitw
        self.run_cli(
            "compose",
            self.tmp / "db" / "list" / "samples_initial.jsonl",
            "-o",
            "db/compose",
            "-n",
            "idx",
            "-S",
            "same",
        )
        same = self.tmp / "db" / "compose" / "idx" / "same" / "index.yaml"
        self.assertEqual(yaml.safe_load(same.read_text())["parameters"]["bitw"], 2)


class UpdateSessionBase(PipelineE2EBase):
    """Helpers for tests building a session 'initial', then a session 'upd'."""

    def design_initial(self):
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
        return self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"

    def compose_update(self):
        """Compose session 'upd' adding one sample; return its session file."""
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
        return self.tmp / "db" / "compose" / "idx" / "upd" / "index.yaml"


class TestRerunAndOldLayout(UpdateSessionBase):
    """Rerunning a session is a no-op; an old symlinked build dir can be updated."""

    def test_rerun_then_update_old_layout(self):
        session_file = self.design_initial()
        self.run_cli("build", session_file, "-o", "build")
        build = self.tmp / "build"
        before = json.loads((build / "index.json").read_text())["index"]

        # 1. rerunning the finished session changes nothing
        log = self.run_cli("build", session_file, "-o", "build")
        self.assertIn("already in", log.stdout + log.stderr)
        after = json.loads((build / "index.json").read_text())["index"]
        self.assertEqual(
            {n: e["nb_samples"] for n, e in after.items()},
            {n: e["nb_samples"] for n, e in before.items()},
        )
        self.assert_in_place("build")

        # 2. turn the build dir into the old layout: symlinks to kmindex_data/initial/
        old_data = build / "kmindex_data" / "initial"
        old_data.mkdir(parents=True)
        for name in after:
            shutil.move(str(build / name), str(old_data / name))
            (build / name).symlink_to(old_data / name, target_is_directory=True)

        # 3. update it, with junk left in the run folders by an interrupted attempt
        upd_session = self.compose_update()
        shards = yaml.safe_load(upd_session.read_text())["shards"]
        # each shard of the session receives one part, named after the session
        updated = {t: [f"{t}_upd"] for t in shards}
        self.assertTrue(set(updated) & set(after), "the update creates a new shard")
        for parts in updated.values():
            for part in parts:
                junk = self.mkdirs("build", "work", "upd", "runs", part, "matrices")
                (junk / "matrix_0.cmbf").write_text("partial")
        self.run_cli("build", upd_session, "-o", "build")

        for name in after:
            if name in updated:
                # moved in place; its previous version is deleted
                self.assertTrue(
                    (build / name).is_dir() and not (build / name).is_symlink()
                )
                self.assertFalse((old_data / name).exists(), f"old {name} left")
            else:
                self.assertTrue((build / name).is_symlink(), f"{name} was touched")
        self.assertFalse((build / "work").exists(), "work dir left")

        # every sample, old and new, is queryable
        for idx, sample in [(0, "sample_0"), (N_SAMPLES, "sample_new")]:
            q, header = self.write_query(f"s{idx}", sample_idx=idx)
            self.run_cli("query", q, "-r", "build", "-o", f"res_{idx}", "-f", "json")
            self.assert_query_hit(f"res_{idx}", header, sample)


class TestInterruptedPublish(UpdateSessionBase):
    """An update stopped anywhere in its swap is finished by a rerun.

    The swap (under the registry lock) is: unregister, current version aside,
    new version in place, register. It is stopped after each of its first
    three commands, then the merge script or ``apply`` is run again.
    """

    def env(self):
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env["PATH"]
        return env

    def bash(self, script_or_cmd, workdir=None, cmd=False):
        env = self.env()
        if workdir:
            env["WORKDIR"] = str(workdir)
        args = ["bash", "-c", script_or_cmd] if cmd else ["bash", str(script_or_cmd)]
        proc = subprocess.run(args, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_swap_interrupted_after_each_command(self):
        session_file = self.design_initial()
        upd_session = None
        for stop, rerun in [(1, "script"), (2, "apply"), (3, "apply")]:
            with self.subTest(stop=stop):
                name = f"build{stop}"
                build = self.tmp / name
                self.run_cli("build", session_file, "-o", name)
                if upd_session is None:
                    upd_session = self.compose_update()
                target = next(iter(yaml.safe_load(upd_session.read_text())["shards"]))
                before = json.loads((build / "index.json").read_text())["index"]
                self.assertIn(target, before)

                # plan the update, build its runs, then stop the swap after `stop`
                self.run_cli("plan", upd_session, "-o", name)
                scripts = build / "assets" / "upd"
                merge_script = scripts / f"{target}_merge.sh"
                self.bash(scripts / f"{target}.sh")
                lines = merge_script.read_text().splitlines()
                publish = next(ln for ln in lines if ln.startswith("flock "))
                swap = shlex.split(publish)[3].split(" && ")
                self.assertEqual(len(swap), 4, swap)
                for ln in lines[: lines.index(publish)]:
                    if not ln.startswith(("#!", "set ", "export ", "cd ", "echo ")):
                        self.bash(ln, workdir=build, cmd=True)
                self.bash(" && ".join(swap[:stop]), workdir=build, cmd=True)

                registry = json.loads((build / "index.json").read_text())["index"]
                self.assertNotIn(target, registry, "target still registered")
                self.assertEqual((build / target).exists(), stop != 2)

                if rerun == "script":
                    self.bash(merge_script)
                else:
                    self.run_cli("apply", upd_session, "-o", name)

                registry = json.loads((build / "index.json").read_text())["index"]
                self.assertEqual(
                    registry[target]["nb_samples"], before[target]["nb_samples"] + 1
                )
                self.assert_in_place(name)
                for idx, sample in [(0, "sample_0"), (N_SAMPLES, "sample_new")]:
                    q, header = self.write_query(f"s{idx}", sample_idx=idx)
                    out = f"res{stop}_{idx}"
                    self.run_cli("query", q, "-r", name, "-o", out, "-f", "json")
                    self.assert_query_hit(out, header, sample)


class TestStepByStepDesignAndBuild(PipelineE2EBase):
    """Decomposed flow: list -> profile -> compose, then plan -> scripts -> apply."""

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
            "--pf",
            "db/profile/profile.yaml",
        )
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.assertTrue(session_file.is_file(), f"missing session file: {session_file}")

        # build, decomposed
        self.run_cli("plan", session_file, "-o", "build2")
        self.assertTrue(
            (
                self.tmp / "build2" / "assets" / "initial" / "kmhelpers_apply.sh"
            ).is_file(),
            "plan did not write the build script",
        )
        # parts are kmtricks runs in work/SESSION/, published under the lock
        # and checked before anything is deleted; plan touches no registry
        scripts = self.tmp / "build2" / "assets" / "initial"
        builds = "".join(
            p.read_text() for p in scripts.glob("*.sh") if not p.stem.endswith("_merge")
        )
        merges = "".join(p.read_text() for p in scripts.glob("*_merge.sh"))
        self.assertIn("kmtricks pipeline", builds)
        self.assertIn("${WORKDIR}/work/initial/runs/", builds)
        self.assertNotIn("kmindex build", builds)
        self.assertIn("flock", merges)
        self.assertIn("manage move-dir", merges)
        self.assertLess(merges.index("check --shard"), merges.index("cleanup"))
        registry = json.loads((self.tmp / "build2" / "index.json").read_text())
        self.assertEqual(registry["index"], {}, "plan registered something")
        # the written scripts build the index on their own
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env["PATH"]
        proc = subprocess.run(
            ["bash", str(scripts / "kmhelpers_apply.sh")],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assert_in_place("build2")
        built = json.loads((self.tmp / "build2" / "index.json").read_text())["index"]

        # apply on the same session finds everything published: nothing changes
        self.run_cli("apply", session_file, "-o", "build2")
        after = json.loads((self.tmp / "build2" / "index.json").read_text())["index"]
        self.assertEqual(
            {n: e["nb_samples"] for n, e in after.items()},
            {n: e["nb_samples"] for n, e in built.items()},
        )

        # query
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build2", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")


class TestPartitionCountStaysFixed(PipelineE2EBase):
    """An index keeps its partition count and minimizer size across sessions."""

    def test_update_reuses_the_stored_build_invariants(self):
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
        layout_file = self.tmp / "db" / "compose" / "idx" / "layout.yaml"
        designed = layout_file.read_bytes()
        layout = yaml.safe_load(designed)["data"]
        # the minimizer size is set at design, the partition count is left to the build
        self.assertEqual(layout["minim_size"], 10)
        self.assertFalse(any(s.get("partition_count") for s in layout["map"].values()))

        self.run_cli(
            "build",
            "db",
            "-o",
            "build",
            "--limits",
            '{"ram": 500000000, "files": 4096, "threads": 2}',
        )
        # building never writes the design
        self.assertEqual(layout_file.read_bytes(), designed)
        registry = json.loads((self.tmp / "build" / "index.json").read_text())["index"]
        for props in registry.values():
            self.assertGreater(props["nb_partitions"], 0)
            self.assertEqual(props["minim_size"], 10)

        # a second session on a very different machine profile: the built
        # shards keep their partition count, so the merge succeeds
        random.seed(SEED + 2)
        new_seq = "".join(random.choice("ACGT") for _ in range(SAMPLE_LEN - 400))
        self.sequences.append(new_seq)
        (self.tmp / "data" / "sample_new.fasta").write_text(f">sample_new\n{new_seq}\n")
        new_list = self.tmp / "new_samples.txt"
        new_list.write_text(
            str((self.tmp / "data" / "sample_new.fasta").resolve()) + "\n"
        )

        self.mkdirs("db", "list")
        self.run_cli("list", new_list, "-o", "db/list/upd.jsonl", "-k", KMER_SIZE)
        # another minimizer size cannot be merged: refused at design
        self.run_cli(
            "compose",
            "db/list/upd.jsonl",
            "-o",
            "db/compose",
            "-n",
            "idx",
            "-S",
            "upd",
            "--minim-size",
            "12",
            expect_success=False,
        )
        self.run_cli(
            "compose", "db/list/upd.jsonl", "-o", "db/compose", "-n", "idx", "-S", "upd"
        )
        composed = layout_file.read_bytes()
        log = self.run_cli(
            "build",
            "db",
            "-o",
            "build",
            "-S",
            "upd",
            "--limits",
            '{"ram": 512000000000, "files": 65536, "threads": 32}',
        )
        self.assertEqual(layout_file.read_bytes(), composed)

        updated = json.loads((self.tmp / "build" / "index.json").read_text())["index"]
        for name, props in registry.items():
            self.assertEqual(updated[name]["nb_partitions"], props["nb_partitions"])
            self.assertEqual(updated[name]["minim_size"], props["minim_size"])
        self.assertIn(
            "sample_new",
            [s for props in updated.values() for s in props["samples"]],
        )
        self.assertNotIn("Traceback", log.stdout + log.stderr)


class TestShardedBuild(PipelineE2EBase):
    """--shard-budget-bytes splits a span into independent shards, never merged together."""

    def test_design_build_query_with_shards(self):
        # -b 4 buckets every sample into one span; a shard size small enough
        # for the per-span limit to be the 8-sample floor then forces a second
        # shard (N_SAMPLES is 5, plus 4 added below).
        for extra in range(4):
            path = self.tmp / "data" / f"extra_{extra}.fasta"
            seq = "".join(random.choice("ACGT") for _ in range(SAMPLE_LEN))
            self.sequences.append(seq)
            path.write_text(f">extra_{extra}\n{seq}\n")

        self.run_cli(
            "design",
            self.tmp / "data",
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
            "--shard-budget-bytes",
            "1KB",
        )
        layout = yaml.safe_load(
            (self.tmp / "db" / "compose" / "idx" / "layout.yaml").read_text()
        )["data"]
        self.assertGreater(layout["shard_size"], 0)
        shards = [
            sh["name"] for entry in layout["map"].values() for sh in entry["shards"]
        ]
        self.assertGreater(len(shards), 1, f"expected several shards, got {shards}")

        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.run_cli("build", session_file, "-o", "build")

        registry = json.loads((self.tmp / "build" / "index.json").read_text())["index"]
        # every shard is registered on its own; nothing merges them together
        self.assertEqual(sorted(registry), sorted(shards))

        # one build script and one merge script per shard
        scripts = sorted(
            p.stem for p in (self.tmp / "build" / "assets" / "initial").glob("*.sh")
        )
        self.assertEqual(
            scripts,
            sorted(shards + [f"{s}_merge" for s in shards] + ["kmhelpers_apply"]),
        )

        # samples stay queryable through their shard
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")


class TestChunkedBuild(PipelineE2EBase):
    """A too-low --limits open-files ceiling splits a build into chunks.

    Chunks are built unregistered (kmtricks) in BUILD_DIR/work/, checked,
    merged in throwaway registries sized from --limits (in several levels when
    needed), and only the merged index ends up in the registry, in place.
    """

    def chunked_apply(self, limits: str) -> str:
        """Design one group of N_SAMPLES samples and apply it under ``limits``; return the log."""
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
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.assertTrue(session_file.is_file(), f"missing session file: {session_file}")
        # the same plan, written as scripts (apply runs it without writing them)
        self.run_cli("plan", session_file, "-o", "planned", "--limits", limits)
        result = self.run_cli("apply", session_file, "-o", "build", "--limits", limits)
        return result.stdout + result.stderr

    def assert_merged_and_clean(self):
        build = self.tmp / "build"
        index_json = build / "index.json"
        self.assertTrue(index_json.is_file(), "apply did not produce index.json")
        registry = json.loads(index_json.read_text())["index"]

        # only the merged index is registered: no chunk, no intermediate merge
        self.assertEqual(len(registry), 1, f"unexpected entries: {sorted(registry)}")
        name, merged = next(iter(registry.items()))
        self.assertEqual(merged["nb_samples"], N_SAMPLES)

        # the index is a directory of BUILD_DIR, not a symlink
        self.assertTrue((build / name).is_dir() and not (build / name).is_symlink())
        self.assertFalse((build / "kmindex_data").exists(), "kmindex_data created")

        # chunk runs, throwaway registries and intermediate merges are deleted
        self.assertFalse((build / "work").exists(), "work dir left")

        # builds and merges are recorded in separate scripts
        assets = self.tmp / "planned" / "assets"
        merge_scripts = list(assets.rglob("*_merge.sh"))
        self.assertTrue(merge_scripts, "no merge script written")
        text = merge_scripts[0].read_text()
        self.assertIn("incomplete run", text)
        self.assertIn("kmindex register --global-index", text)
        self.assertIn("--from-file", text)
        self.assertIn("kmindex merge", text)
        build_script = merge_scripts[0].with_name(
            merge_scripts[0].name.replace("_merge.sh", ".sh")
        )
        self.assertIn("kmtricks pipeline", build_script.read_text())
        self.assertNotIn("--register-as", build_script.read_text())

        # every original sample must still be queryable after the chunked merge
        for idx in range(N_SAMPLES):
            q, header = self.write_query(f"s{idx}", sample_idx=idx)
            self.run_cli(
                "query", q, "-r", "build", "-o", f"results_{idx}", "-f", "json"
            )
            self.assert_query_hit(f"results_{idx}", header, f"sample_{idx}")

    def test_apply_chunks_and_merges_when_files_limit_too_low(self):
        # files=5 can't fit N_SAMPLES=5 samples in one kmtricks build (merge
        # stage needs samples+1 open files), forcing a chunked build+merge;
        # the same limit caps a merge at 4 inputs: two levels.
        self.chunked_apply('{"files": 5}')
        self.assert_merged_and_clean()

    def test_run_builds_one_chunk_then_shard_merges(self):
        """apply --run builds one chunk without merging; --shard merges later."""
        limits = '{"files": 5}'
        self.run_cli(
            "design", self.samples_txt, "-o", "db", "-n", "idx", "-S", "initial",
            "-k", KMER_SIZE, "-b", "4", "-g", "1",
        )
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.run_cli("plan", session_file, "-o", "planned", "--limits", limits)
        self.run_cli(
            "apply", session_file, "-o", "build", "--limits", limits,
            "--run", "*_chunk0",
        )
        runs = sorted(p.name for p in (self.tmp / "build" / "work").rglob("*_chunk*"))
        self.assertEqual(len(runs), 1, f"unexpected runs: {runs}")
        self.assertTrue(runs[0].endswith("_chunk0"))
        self.assertFalse((self.tmp / "build" / "idx_g0").exists(), "merged too early")

        result = self.run_cli(
            "apply", session_file, "-o", "build", "--limits", limits,
            "--shard", "idx_g0*",
        )
        self.assertIn("Reusing complete run", result.stdout + result.stderr)
        self.assert_merged_and_clean()

    def test_unmatched_run_pattern_fails(self):
        self.run_cli(
            "design", self.samples_txt, "-o", "db", "-n", "idx", "-S", "initial",
            "-k", KMER_SIZE, "-b", "4", "-g", "1",
        )
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        result = self.run_cli(
            "apply", session_file, "-o", "build", "--run", "nope*",
            expect_success=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No kmtricks run matches nope*", result.stdout + result.stderr)

    def test_merge_split_into_sub_shards_by_max_map_count(self):
        # 2 mmaps above the reserved 1000: 2 inputs per merge, so the chunks
        # are merged in a tree of several levels.
        log = self.chunked_apply('{"files": 5, "maps": 1002}')
        self.assertIn("vm.max_map_count limit", log)
        self.assert_merged_and_clean()


class TestQueryFormats(PipelineE2EBase):
    """The same query as FASTA/FASTQ, plain or gzipped, matches its sample."""

    def test_query_fasta_fastq_plain_and_gz(self):
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
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.run_cli("build", session_file, "-o", "build")

        header = "q_fmt"
        seq = self.sequences[0][QUERY_START : QUERY_START + QUERY_LEN]
        fasta = f">{header}\n{seq}\n".encode()
        fastq = f"@{header}\n{seq}\n+\n{'I' * len(seq)}\n".encode()

        for ext in ("fasta", "fa", "fa.gz", "fastq", "fq", "fq.gz"):
            with self.subTest(ext=ext):
                data = fastq if ext.startswith(("fastq", "fq")) else fasta
                if ext.endswith(".gz"):
                    data = gzip.compress(data)
                name = ext.replace(".", "_")
                path = self.tmp / f"query_{name}.{ext}"
                path.write_bytes(data)
                out = f"results_{name}"
                self.run_cli("query", path, "-r", "build", "-o", out, "-f", "json")
                self.assert_query_hit(out, header, "sample_0")

        # Reads all shorter than s+z: kmindex writes no output
        short = seq[: KMER_SIZE - 1]
        path = self.tmp / "query_short.fq.gz"
        path.write_bytes(
            gzip.compress(f"@q_short\n{short}\n+\n{'I' * len(short)}\n".encode())
        )
        proc = self.run_cli(
            "query",
            path,
            "-r",
            "build",
            "-o",
            "results_short",
            "-f",
            "json",
            expect_success=False,
        )
        self.assertIn("no valid sequences", proc.stdout + proc.stderr)
        info = yaml.safe_load(
            (self.tmp / "results_short" / "query_short" / "info.yaml").read_text()
        )
        self.assertIn("no valid sequences", info["error"])
        self.assertIn("skipped", info["stderr"])


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
            "--pf",
            "db/profile/profile.yaml",
        )
        session_file = self.tmp / "db" / "compose" / "idx" / "initial" / "index.yaml"
        self.assertTrue(session_file.is_file(), f"missing session file: {session_file}")
        self.run_cli("build", session_file, "-o", "build")
        self.assertTrue(
            (self.tmp / "build" / "index.json").is_file(),
            "build did not produce index.json",
        )

        # 3. query a substring of sample_0 -> perfect match
        q0, q0_header = self.write_query("s0", sample_idx=0)
        self.run_cli("query", q0, "-r", "build", "-o", "results", "-f", "json")
        self.assert_query_hit("results", q0_header, "sample_0")

        # 4. update: scan a separate dir holding one new sample, compose against
        #    the existing layout (no --pf), and rebuild into the same work dir.
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
        upd_session = self.tmp / "db" / "compose" / "idx" / "upd" / "index.yaml"
        self.assertTrue(upd_session.is_file(), f"update compose missing: {upd_session}")
        self.run_cli("build", upd_session, "-o", "build")

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
            "list", grp_data, "-o", "db/list/grp.jsonl", "--lg", "-k", KMER_SIZE
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
        # Update mode (no --pf) with no existing <name>_layout.yaml -> non-zero.
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
