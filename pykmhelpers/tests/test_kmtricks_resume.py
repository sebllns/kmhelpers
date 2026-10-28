"""Tests of resuming an interrupted kmtricks run (``kmtricks_resume``)."""

import filecmp
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pykmhelpers.core.kmtricks_resume import (
    ResumePlan,
    RunResumer,
    RunSpec,
    plan_resume,
)

PARTITIONS = 4
OPTIONS = (
    "Options: dir=run, kmer_size=25, c_ab_min=1, minim_size=10, nb_parts=4, "
    "bloom_size=100000, lz4=1, bwidth=2, mode=bf, format=bin, count_format=hash, "
    "until=all\n"
)


class TestPlanResume(unittest.TestCase):
    """The plan read from a fake run directory, in the layout of kmtricks v1.6.0."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_resume_"))
        self.fof = self.tmp / "run.fof"
        self.fof.write_text("".join(f"S{i}: /data/S{i}.fa\n" for i in range(3)))
        self.spec = RunSpec(
            run_dir=self.tmp / "run",
            fof=self.fof,
            partitions=PARTITIONS,
            kmer_size=25,
            minim_size=10,
            bloom_size=100000,
            hard_min=1,
            compress=True,
        )
        run = self.spec.run_dir
        for d in ("superkmers", "partition_infos", "merge_infos", "matrices"):
            (run / d).mkdir(parents=True)
        for p in range(PARTITIONS):
            (run / "counts" / f"partition_{p}").mkdir(parents=True)
        (run / "options.txt").write_text(OPTIONS)
        shutil.copy(self.fof, run / "kmtricks.fof")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def superk(self, sample, done=True):
        d = self.spec.run_dir / "superkmers" / sample
        d.mkdir()
        for p in range(PARTITIONS):
            self.spec.skp_file(sample, p).touch()
        if done:
            self.spec.pinfo_file(sample).touch()

    def count(self, sample, p, keep_skp=False):
        self.spec.count_file(sample, p).touch()
        if not keep_skp:
            self.spec.skp_file(sample, p).unlink()

    def test_fresh_after_superk(self):
        for s in ("S0", "S1", "S2"):
            self.superk(s)
        plan, _ = plan_resume(self.spec)
        self.assertEqual(plan.superk, [])
        self.assertEqual(plan.count, {s: [0, 1, 2, 3] for s in ("S0", "S1", "S2")})
        self.assertEqual(plan.merge, [0, 1, 2, 3])

    def test_partial_states(self):
        self.superk("S0")
        for p in range(PARTITIONS):
            self.count("S0", p)  # done
        self.superk("S1")
        self.count("S1", 0)  # done
        self.count("S1", 1, keep_skp=True)  # possibly cut short
        self.superk("S2", done=False)  # superk cut short
        plan, _ = plan_resume(self.spec)
        self.assertEqual(plan.superk, ["S2"])
        self.assertEqual(plan.count, {"S1": [1, 2, 3], "S2": [0, 1, 2, 3]})

    def test_missing_count_and_skp_rebuilds_sample(self):
        self.superk("S0")
        self.spec.skp_file("S0", 2).unlink()
        for s in ("S1", "S2"):
            self.superk(s)
        plan, _ = plan_resume(self.spec)
        self.assertEqual(plan.superk, ["S0"])

    def test_merged_partitions_skipped(self):
        for s in ("S0", "S1", "S2"):
            self.superk(s)
            for p in range(PARTITIONS):
                self.count(s, p)
        for p in (0, 2):
            self.spec.merge_info_file(p).touch()
            for s in ("S0", "S1", "S2"):
                self.spec.count_file(s, p).unlink()  # deleted once merged
        plan, _ = plan_resume(self.spec)
        self.assertEqual((plan.superk, plan.count, plan.merge), ([], {}, [1, 3]))

    def test_not_resumable(self):
        plan, reason = plan_resume(self.spec)
        self.assertIsNone(plan)
        self.assertIn("repart", reason)
        self.superk("S0")
        self.fof.write_text("S0: /data/S0.fa\n")
        self.assertIn("sample list", plan_resume(self.spec)[1])
        shutil.copy(self.fof, self.spec.run_dir / "kmtricks.fof")
        other = RunSpec(**{**self.spec.__dict__, "bloom_size": 5})
        self.assertIn("bloom_size", plan_resume(other)[1])


class TestRunResumer(unittest.TestCase):
    def test_commands(self):
        tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_resume_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fof = tmp / "run.fof"
        fof.write_text("S0: /x\nS1: /y\n")
        spec = RunSpec(tmp / "run", fof, 2, 25, 10, 1000, 2, compress=False)
        calls = []

        def runner(cmd):
            calls.append(cmd[1:4])
            if cmd[1] == "count":  # what kmtricks writes
                p = int(cmd[cmd.index("--partition-id") + 1])
                spec.count_file(cmd[3], p).parent.mkdir(parents=True, exist_ok=True)
                spec.count_file(cmd[3], p).touch()

        spec.count_file("S0", 0).parent.mkdir(parents=True)
        spec.count_file("S0", 0).touch()  # counted before the interruption
        plan = ResumePlan(superk=["S1"], count={"S0": [1], "S1": [0, 1]}, merge=[0, 1])
        RunResumer(spec, threads=4, jobs=1, runner=runner).resume(plan)
        self.assertEqual(
            calls,
            [
                ["count", "--id", "S0"],
                ["superk", "--id", "S1"],
                ["count", "--id", "S1"],
                ["count", "--id", "S1"],
                ["merge", "--partition-id", "0"],
                ["merge", "--partition-id", "1"],
            ],
        )
        self.assertFalse(spec.count_file("S0", 0).exists())  # deleted once merged

    def test_merge_refuses_missing_counts(self):
        tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_resume_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fof = tmp / "run.fof"
        fof.write_text("S0: /x\n")
        spec = RunSpec(tmp / "run", fof, 1, 25, 10, 1000, 2)
        with self.assertRaises(RuntimeError):
            RunResumer(spec, threads=1, runner=lambda cmd: None).resume(
                ResumePlan(merge=[0])
            )


@unittest.skipUnless(shutil.which("kmtricks"), "kmtricks not in PATH")
class TestResumeWithKmtricks(unittest.TestCase):
    """A run left in a partial state resumes to the matrices of one pipeline call."""

    ARGS = (
        "--kmer-size",
        "25",
        "--hard-min",
        "1",
        "--bloom-size",
        "100000",
        "--minimizer-size",
        "10",
        "--nb-partitions",
        str(PARTITIONS),
        "--mode",
        "hash:bf:bin",
        "--static-repart",
        "--cpr",
        "-t",
        "2",
    )

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kmhelpers_resume_kmt_"))
        rng = random.Random(0)
        genome = "".join(rng.choice("ACGT") for _ in range(20000))
        lines = []
        for s in range(4):
            path = cls.tmp / f"S{s}.fa"
            with open(path, "w") as f:
                for i in range(2000):
                    p = rng.randrange(len(genome) - 100)
                    f.write(f">{i}\n{genome[p : p + 100]}\n")
            lines.append(f"S{s}: {path}\n")
        cls.fof = cls.tmp / "run.fof"
        cls.fof.write_text("".join(lines))
        cls.ref = cls.tmp / "ref"
        cls.pipeline(cls.ref)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def pipeline(cls, run, *extra):
        subprocess.run(
            ["kmtricks", "pipeline", "--file", str(cls.fof), "--run-dir", str(run)]
            + [*cls.ARGS, *extra],
            check=True,
            capture_output=True,
        )

    def spec(self, run):
        return RunSpec(run, self.fof, PARTITIONS, 25, 10, 100000, 1, compress=True)

    def kmt(self, *args):
        subprocess.run(["kmtricks", *args], check=True, capture_output=True)

    def assert_same_matrices(self, run):
        for p in range(PARTITIONS):
            name = Path("matrices") / f"matrix_{p}.cmbf"
            self.assertTrue(filecmp.cmp(run / name, self.ref / name, shallow=False))

    def test_resume_partial_samples(self):
        run = self.tmp / "partial"
        self.pipeline(run, "--until", "superk")
        spec = self.spec(run)
        common = ["--run-dir", str(run), "--mode", "hash", "--hard-min", "1", "--cpr"]
        self.kmt("count", "--id", "S0", *common)
        for p in range(PARTITIONS):
            spec.skp_file("S0", p).unlink()
        self.kmt("count", "--id", "S1", "--partition-id", "0", *common)
        spec.skp_file("S1", 0).unlink()
        spec.pinfo_file("S2").unlink()  # as if its superk was cut short
        plan, _ = plan_resume(spec)
        self.assertEqual(plan.superk, ["S2"])
        self.assertEqual(plan.count["S1"], [1, 2, 3])
        RunResumer(spec, threads=2, jobs=2).resume(plan)
        self.assert_same_matrices(run)
        self.assertEqual(plan_resume(spec)[0].merge, [])

    def test_resume_partial_merge(self):
        run = self.tmp / "merge"
        self.pipeline(run, "--until", "count")
        self.kmt(
            "merge",
            "--run-dir",
            str(run),
            "--partition-id",
            "2",
            "--mode",
            "hash:bf:bin",
            "--cpr",
        )
        (run / "matrices" / "matrix_0.cmbf").write_bytes(b"cut short")
        plan, _ = plan_resume(self.spec(run))
        self.assertEqual((plan.count, plan.merge), ({}, [0, 1, 3]))
        RunResumer(self.spec(run), threads=2).resume(plan)
        self.assert_same_matrices(run)


if __name__ == "__main__":
    unittest.main()
