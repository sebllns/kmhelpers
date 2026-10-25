"""Unit tests for the --cluster file and the SLURM files written from it."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from pykmhelpers.pipeline.index_ops.cluster import (
    limits_for,
    load_cluster,
    mem_bytes,
    write_slurm,
    write_submission,
)
from pykmhelpers.pipeline.index_ops.plan_file import job_names

CLUSTER = {
    "type": "slurm",
    "partition": "compute",
    "time": "2-00:00:00",
    "exclude": ["node01"],
    "max_parallel": 8,
    "setup": "export PATH=/opt/kmhelpers/bin:$PATH\n",
    "jobs": {
        "build": {"cpus": 24, "mem": "120G"},
        "publish": {"cpus": 8, "mem": "64G", "partition": "mem"},
        "check": {"time": "1:00:00"},
    },
    "limits": {"files": 131072, "maps": 65530},
}


class ClusterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def load(self, data):
        path = self.tmp / "cluster.yaml"
        path.write_text(yaml.safe_dump(data))
        return load_cluster(str(path))


class TestLoadCluster(ClusterCase):
    def test_job_kinds_inherit_the_top_level(self):
        cluster = self.load(CLUSTER)
        build, publish, check = (cluster["jobs"][k] for k in ("build", "publish", "check"))
        self.assertEqual((build["partition"], build["time"]), ("compute", "2-00:00:00"))
        self.assertEqual(publish["partition"], "mem")
        self.assertEqual((check["cpus"], check["mem"], check["time"]), (1, "4G", "1:00:00"))
        self.assertEqual(build["exclude"], ["node01"])

    def test_limits_from_the_job_resources(self):
        cluster = self.load(CLUSTER)
        build = json.loads(limits_for(cluster, "build", 0.5))
        self.assertEqual(build, {"ram": 60 << 30, "threads": 24, "files": 131072, "maps": 65530})
        self.assertEqual(json.loads(limits_for(cluster, "publish"))["threads"], 8)

    def test_errors(self):
        for data, msg in [
            ({**CLUSTER, "nope": 1}, "unknown key"),
            ({**CLUSTER, "type": "pbs"}, "cluster type 'pbs' is not supported \\(supported: slurm\\)"),
            ({k: v for k, v in CLUSTER.items() if k != "type"}, "'type' is required"),
            ({**CLUSTER, "jobs": {"build": {"cpus": 1}}}, "needs cpus and mem"),
            ({**CLUSTER, "jobs": {**CLUSTER["jobs"], "other": {}}}, "unknown job kind"),
            ({**CLUSTER, "limits": {"ram": 1}}, "unknown limit"),
            ({**CLUSTER, "jobs": {**CLUSTER["jobs"], "build": {"cpus": 2, "mem": "lots"}}}, "Invalid memory"),
        ]:
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError, msg):
                self.load(data)

    def test_mem(self):
        self.assertEqual(mem_bytes("120G"), 120 << 30)
        self.assertEqual(mem_bytes("4096M"), 4 << 30)
        self.assertEqual(mem_bytes("1.5T"), int(1.5 * (1 << 40)))
        self.assertEqual(mem_bytes(2048), 2 << 30)  # MB, as sbatch


class TestWriteSlurm(ClusterCase):
    def plan(self, per_job):
        chunks = [f"idx_g0_initial_chunk{n}" for n in range(7)]
        tasks = {}
        for shard in ("idx_g0", "idx_g1"):
            runs = [c.replace("idx_g0", shard) for c in chunks]
            tasks[f"{shard}_initial"] = {
                "shard": shard,
                "dir": f"{shard}/",
                "jobs": job_names(shard, runs, True, per_job),
            }
        return {
            "definition": "/db/compose/idx/initial/index.yaml",
            "build_dir": str(self.tmp / "build"),
            "tasks": tasks,
        }

    def write(self, per_job, notify=None, level="global"):
        cluster = self.load(CLUSTER)
        out = self.tmp / "slurm"
        write_slurm(self.plan(per_job), cluster, str(out), notify, level)
        return out

    def test_jobs_and_headers(self):
        out = self.write(3)
        self.assertEqual(
            (out / "jobs.txt").read_text().split(),
            [f"idx_g{s}_j{k}" for s in (0, 1) for k in range(3)],
        )
        build = (out / "build.sbatch").read_text()
        for line in ("#SBATCH -p compute", "#SBATCH -c 24", "#SBATCH --mem=120G",
                     "#SBATCH --exclude=node01", "export PATH=/opt/kmhelpers/bin:$PATH"):
            self.assertIn(line, build)
        self.assertIn('--task "$JOB"', build)
        publish = (out / "publish.sbatch").read_text()
        self.assertIn("#SBATCH -p mem", publish)
        self.assertIn("#SBATCH -c 8", publish)
        finish = (out / "finish.sbatch").read_text()
        self.assertIn("#SBATCH -t 1:00:00", finish)
        self.assertIn("--status", finish)
        self.assertIn("manage -r", finish)
        self.assertFalse((out / "check.sbatch").exists())
        # a failed dependency cancels publish and finish, never the build tasks
        self.assertIn("--kill-on-invalid-dep=yes", publish)
        self.assertIn("--kill-on-invalid-dep=yes", finish)
        self.assertNotIn("--kill-on-invalid-dep", build)
        submit = (out / "submit.sh").read_text()
        self.assertIn("%8", submit)
        self.assertIn("--pending", submit)
        for path in out.glob("*.s*"):
            subprocess.run(["bash", "-n", str(path)], check=True)

    def run_finish(self, pending="", check=0):
        """Run finish.sbatch with a fake kmhelpers; return its calls and exit code."""
        out = self.write(3)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        calls = self.tmp / "calls.txt"
        fake = bin_dir / "kmhelpers"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> {calls}\n'
            'case "$*" in\n'
            f'  *--pending*) printf "%s" "{pending}" ;;\n'
            f"  *check*) exit {check} ;;\n"
            "esac\n"
        )
        fake.chmod(0o755)
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        code = subprocess.run(["bash", str(out / "finish.sbatch")], env=env).returncode
        return calls.read_text().splitlines(), code

    def test_finish_cleans_up_a_done_and_checked_build(self):
        calls, code = self.run_finish()
        self.assertEqual(code, 0)
        self.assertTrue(any("--cleanup" in c for c in calls))
        # removed before the status is written and mailed
        self.assertLess(
            next(n for n, c in enumerate(calls) if "--cleanup" in c),
            next(n for n, c in enumerate(calls) if "--status" in c),
        )

    def test_finish_keeps_the_locks_of_an_unfinished_build(self):
        for kwargs in ({"pending": "idx_g0_publish"}, {"check": 1}):
            with self.subTest(**kwargs):
                (self.tmp / "calls.txt").unlink(missing_ok=True)
                calls, code = self.run_finish(**kwargs)
                self.assertNotEqual(code, 0)
                self.assertFalse(any("--cleanup" in c for c in calls))
                self.assertTrue(any("--status" in c for c in calls))

    def test_submit_records_and_skips_active_jobs(self):
        submit = (self.write(3) / "submit.sh").read_text()
        self.assertIn("submitted.tsv", submit)
        self.assertIn("squeue -h -j", submit)
        self.assertIn('--dependency="afterany:', submit)

    def test_notify(self):
        out = self.write(3)
        self.assertNotIn("--notify", (out / "build.sbatch").read_text())
        self.assertNotIn("--notify", (out / "finish.sbatch").read_text())

        out = self.write(3, "me@example.com")
        self.assertNotIn("--notify", (out / "build.sbatch").read_text())
        self.assertNotIn("--notify", (out / "publish.sbatch").read_text())
        self.assertIn("--status --notify me@example.com", (out / "finish.sbatch").read_text())

        out = self.write(3, "me@example.com", "shard")
        shard = "--notify me@example.com --notify-level shard --no-notify-final"
        self.assertIn(shard, (out / "build.sbatch").read_text())
        self.assertIn(shard, (out / "publish.sbatch").read_text())
        self.assertIn("--status --notify me@example.com", (out / "finish.sbatch").read_text())

    def run_submit(self, pending, alive):
        """Run submit.sh with fake SLURM commands and a fake kmhelpers printing
        ``pending``; ``alive``: the SLURM ids squeue still lists. Return the calls."""
        out = self.write(3)
        fake = self.tmp / "fake"
        fake.mkdir(exist_ok=True)
        calls = fake / "calls"
        scripts = {
            "sbatch": f'n=$(( $(cat {fake}/n 2>/dev/null || echo 500) + 1 )); echo $n > {fake}/n; '
                      f'echo "sbatch $*" >> {calls}; echo $n',
            "squeue": f'grep -qxF "$3" {fake}/alive && echo RUNNING; exit 0',
            "scancel": f'echo "scancel $*" >> {calls}',
            "scontrol": "echo 'MaxArraySize = 1001'",
            "kmhelpers": f"cat {fake}/pending",
        }
        for name, body in scripts.items():
            (fake / name).write_text(f"#!/usr/bin/env bash\n{body}\n")
            (fake / name).chmod(0o755)
        (fake / "pending").write_text("".join(f"{j}\n" for j in pending))
        (fake / "alive").write_text("".join(f"{i}\n" for i in alive))
        calls.write_text("")
        env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}")
        proc = subprocess.run(["bash", str(out / "submit.sh")], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return calls.read_text().splitlines(), out

    def test_rerun_keeps_a_pending_finish_job(self):
        _, out = self.run_submit(["idx_g0_j0", "idx_g0_publish"], [])
        submitted = (out / "submitted.tsv").read_text()
        finish = submitted.strip().splitlines()[-1].split("\t")[1]
        ids = [ln.split("\t")[1] for ln in submitted.strip().splitlines()]
        # everything still queued: nothing submitted, the finish job kept
        calls, _ = self.run_submit(["idx_g0_j0", "idx_g0_publish"], ids)
        self.assertEqual(calls, [])
        # the build job ended without its chunks: resubmitted, finish replaced
        alive = [i for i in ids if not i.endswith("_0")]
        calls, _ = self.run_submit(["idx_g0_j0", "idx_g0_publish"], alive)
        self.assertEqual(sum(c.startswith("sbatch") and "--array" in c for c in calls), 1)
        self.assertIn(f"scancel {finish}", calls)
        self.assertTrue(calls[-1].startswith("sbatch") and "finish.sbatch" in calls[-1])

    def test_each_run_has_its_own_job_list(self):
        """Queued array tasks read their line when they start: a later run of
        submit.sh must not change the list they were given."""
        calls, out = self.run_submit(["idx_g0_j0", "idx_g0_j1", "idx_g0_publish"], [])
        first = next(c for c in calls if "--array" in c).split()[-2]
        self.assertEqual(Path(first).parent, out / "lists")
        self.assertEqual(Path(first).read_text().split(), ["idx_g0_j0", "idx_g0_j1"])
        ids = [ln.split("\t")[1] for ln in (out / "submitted.tsv").read_text().splitlines()]
        # everything still queued: no new list
        self.run_submit(["idx_g0_j0", "idx_g0_j1", "idx_g0_publish"], ids)
        self.assertEqual(list((out / "lists").iterdir()), [Path(first)])
        # j1 cancelled: a new list with it only, the first one unchanged
        alive = [i for i in ids if not i.endswith("_1")]
        calls, _ = self.run_submit(["idx_g0_j0", "idx_g0_j1", "idx_g0_publish"], alive)
        second = next(c for c in calls if "--array" in c).split()[-2]
        self.assertNotEqual(second, first)
        self.assertEqual(Path(second).read_text().split(), ["idx_g0_j1"])
        self.assertEqual(Path(first).read_text().split(), ["idx_g0_j0", "idx_g0_j1"])

    def test_array_task_without_a_job_fails(self):
        out = self.write(3)
        fake = self.tmp / "fake"
        fake.mkdir()
        (fake / "kmhelpers").write_text(f'#!/usr/bin/env bash\necho "$*" >> {fake}/calls\n')
        (fake / "kmhelpers").chmod(0o755)
        jobs = self.tmp / "jobs.txt"
        jobs.write_text("idx_g0_j0\n")
        env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}")
        for task, ok in (("0", True), ("1", False)):
            proc = subprocess.run(
                ["bash", str(out / "build.sbatch"), str(jobs), "0"],
                capture_output=True, text=True, env=dict(env, SLURM_ARRAY_TASK_ID=task),
            )
            self.assertEqual(proc.returncode == 0, ok, proc.stdout + proc.stderr)
        self.assertIn("No job on line 2", proc.stderr)
        # the task without a job ran nothing (not every job of the plan)
        self.assertEqual(len((fake / "calls").read_text().splitlines()), 1)

    def test_submission_files_follow_the_type(self):
        cluster = self.load(CLUSTER)
        written = write_submission(self.plan(3), cluster, str(self.tmp / "assets"))
        self.assertTrue(written)
        self.assertTrue(all(Path(p).parent == self.tmp / "assets" / "slurm" for p in written))
        with self.assertRaisesRegex(ValueError, "'pbs' is not supported"):
            write_submission(self.plan(3), {**cluster, "type": "pbs"}, str(self.tmp / "x"))
        self.assertFalse((self.tmp / "x").exists())

    def test_whole_shard_jobs_have_no_publish_job(self):
        out = self.write(0)
        self.assertEqual((out / "jobs.txt").read_text().split(), ["idx_g0", "idx_g1"])
        self.assertNotIn("_publish", (out / "submit.sh").read_text().split("for SHARD in")[1].split(";")[0])


if __name__ == "__main__":
    unittest.main()
