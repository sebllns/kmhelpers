"""Unit tests for FASTA/FASTQ validation (SequenceValidator + SeqKitWrapper).

Two engines are covered:

- Builtin Python checks, forced with ``use_seqkit=False`` so they run on any
  machine and stay deterministic.
- seqkit, only when the real binary is installed. When seqkit is missing a
  warning is emitted and those tests are skipped (no fake binary is used).

Manual run:
    python -m pykmhelpers.tests.test_fasta_validation [FILE ...]

With one or more file paths, each file is validated (using seqkit when
available, builtin otherwise) and the result is printed. With no path, the
normal unittest suite runs against generated good/bad sequences.
"""

import os
import tempfile
import unittest
import warnings

from pykmhelpers.core.fasta import Fasta, SequenceValidator, validate_sequence_file
from pykmhelpers.core.seqkit_wrapper import SeqKitWrapper

SEQKIT_AVAILABLE = SeqKitWrapper.is_available()
if not SEQKIT_AVAILABLE:
    warnings.warn(
        "seqkit not installed: seqkit validation tests are skipped, "
        "builtin validator only.",
        RuntimeWarning,
    )


def _write(directory, name, content):
    """Write content to a file and return its path."""
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(content)
    return path


def _random_good_fasta():
    """Generate a well-formed multi-record FASTA string with random sequences."""
    fasta = Fasta()
    fasta.fill_random(num_sequences=4, average_size=120, min_size=60, header="rnd_")
    return fasta.to_fasta() + "\n"


def _random_good_fastq(n=4, length=60):
    """Generate a well-formed FASTQ string from random sequences."""
    fasta = Fasta()
    fasta.fill_random(num_sequences=n, average_size=length, min_size=length)
    records = []
    for seq in fasta:
        records.append(f"@{seq.header}\n{seq.content}\n+\n{'I' * len(seq)}\n")
    return "".join(records)


class TestBuiltinFasta(unittest.TestCase):
    """Builtin FASTA checks against generated and crafted inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _validate(self, name, content):
        path = _write(self.dir, name, content)
        v = SequenceValidator(path, use_seqkit=False)
        return v, v.validate()

    def test_random_good_fasta_is_valid(self):
        v, ok = self._validate("good.fasta", _random_good_fasta())
        self.assertTrue(ok)
        self.assertEqual(v.engine, "builtin")
        self.assertEqual(v.get_errors(), [])

    def test_sequence_before_header(self):
        v, ok = self._validate("bad.fasta", "ACGT\n>s1\nACGT\n")
        self.assertFalse(ok)
        self.assertIn("Sequence data before any header", v.get_errors()[0][1])

    def test_empty_header(self):
        v, ok = self._validate("bad.fasta", ">\nACGT\n")
        self.assertFalse(ok)
        self.assertTrue(any("Empty FASTA header" in r for _, r in v.get_errors()))

    def test_header_with_no_sequence(self):
        v, ok = self._validate("bad.fasta", ">s1\nACGT\n>s2\n")
        self.assertFalse(ok)
        self.assertTrue(any("no sequence" in r for _, r in v.get_errors()))

    def test_invalid_sequence_char(self):
        v, ok = self._validate("bad.fasta", ">s1\nACGZ1T\n")
        self.assertFalse(ok)
        reason = v.get_errors()[0][1]
        self.assertIn("Invalid sequence character", reason)
        self.assertIn("Z", reason)

    def test_empty_file(self):
        v, ok = self._validate("empty.fasta", "")
        self.assertFalse(ok)
        self.assertIn("no FASTA records", v.get_errors()[0][1])


class TestBuiltinFastq(unittest.TestCase):
    """Builtin FASTQ checks against generated and crafted inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _validate(self, name, content):
        path = _write(self.dir, name, content)
        v = SequenceValidator(path, use_seqkit=False)
        return v, v.validate()

    def test_random_good_fastq_is_valid(self):
        v, ok = self._validate("good.fastq", _random_good_fastq())
        self.assertTrue(ok)
        self.assertEqual(v.engine, "builtin")

    def test_quality_length_mismatch(self):
        v, ok = self._validate("bad.fastq", "@r1\nACGT\n+\nII\n")
        self.assertFalse(ok)
        self.assertTrue(any("Quality length" in r for _, r in v.get_errors()))

    def test_bad_separator(self):
        v, ok = self._validate("bad.fastq", "@r1\nACGT\n-\nIIII\n")
        self.assertFalse(ok)
        self.assertTrue(any("start with '+'" in r for _, r in v.get_errors()))

    def test_bad_header_start(self):
        v, ok = self._validate("bad.fastq", "r1\nACGT\n+\nIIII\n")
        self.assertFalse(ok)
        self.assertTrue(any("start with '@'" in r for _, r in v.get_errors()))

    def test_truncated_record(self):
        v, ok = self._validate("bad.fastq", "@r1\nACGT\n+\n")
        self.assertFalse(ok)
        self.assertTrue(any("Truncated" in r for _, r in v.get_errors()))


class TestValidatorMisc(unittest.TestCase):
    """Format detection, helper and error-handling behavior."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            SequenceValidator(os.path.join(self.dir, "nope.fasta"))

    def test_unknown_extension_raises(self):
        path = _write(self.dir, "sample.txt", ">s\nACGT\n")
        with self.assertRaises(ValueError):
            SequenceValidator(path)

    def test_forced_format_overrides_extension(self):
        path = _write(self.dir, "sample.txt", ">s\nACGT\n")
        v = SequenceValidator(path, fmt="fasta", use_seqkit=False)
        self.assertTrue(v.validate())

    def test_convenience_helper(self):
        path = _write(self.dir, "good.fasta", _random_good_fasta())
        self.assertTrue(validate_sequence_file(path, use_seqkit=False))

    def test_max_errors_cap(self):
        content = ">s\n" + "".join("Z\n" for _ in range(50))
        path = _write(self.dir, "bad.fasta", content)
        v = SequenceValidator(path, use_seqkit=False, max_errors=5)
        v.validate()
        self.assertEqual(v.get_error_count(), 5)


class TestStrictToggle(unittest.TestCase):
    """The strict flag controls the (expensive) alphabet check only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_strict_skips_bad_fasta_chars(self):
        # Invalid character is ignored when strict=False.
        path = _write(self.dir, "bad.fasta", ">s1\nACGZ1T\n")
        self.assertFalse(validate_sequence_file(path, use_seqkit=False, strict=True))
        self.assertTrue(validate_sequence_file(path, use_seqkit=False, strict=False))

    def test_non_strict_skips_bad_fastq_quality(self):
        # Out-of-range quality char is ignored when strict=False.
        path = _write(self.dir, "bad.fastq", "@r1\nACGT\n+\nII\x01I\n")
        self.assertFalse(validate_sequence_file(path, use_seqkit=False, strict=True))
        self.assertTrue(validate_sequence_file(path, use_seqkit=False, strict=False))

    def test_non_strict_still_catches_structural_errors(self):
        # Structural checks stay on regardless of strict.
        path = _write(self.dir, "bad.fastq", "@r1\nACGT\n+\nII\n")
        v = SequenceValidator(path, use_seqkit=False, strict=False)
        self.assertFalse(v.validate())
        self.assertTrue(any("Quality length" in r for _, r in v.get_errors()))


class TestMaxErrors(unittest.TestCase):
    """max_errors caps the report and stops the scan early (1 = fail-fast)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_collects_many(self):
        # Several invalid sequence lines: the default collects them all.
        content = ">s\n" + "".join("Z\n" for _ in range(10))
        path = _write(self.dir, "bad.fasta", content)
        v = SequenceValidator(path, use_seqkit=False, max_errors=100)
        v.validate()
        self.assertGreater(v.get_error_count(), 1)

    def test_max_errors_one_stops_at_first(self):
        content = ">s\n" + "".join("Z\n" for _ in range(10))
        path = _write(self.dir, "bad.fasta", content)
        v = SequenceValidator(path, use_seqkit=False, max_errors=1)
        self.assertFalse(v.validate())
        self.assertEqual(v.get_error_count(), 1)

    def test_max_errors_valid_file_unaffected(self):
        path = _write(self.dir, "good.fasta", _random_good_fasta())
        v = SequenceValidator(path, use_seqkit=False, max_errors=1)
        self.assertTrue(v.validate())


@unittest.skipUnless(SEQKIT_AVAILABLE, "seqkit not installed")
class TestSeqKitEngine(unittest.TestCase):
    """seqkit-backed path, only run when the real seqkit binary is present."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_wrapper_available(self):
        self.assertTrue(SeqKitWrapper.is_available())

    def test_seqkit_valid(self):
        path = _write(self.dir, "good.fasta", _random_good_fasta())
        v = SequenceValidator(path, use_seqkit=True)
        ok = v.validate()
        self.assertEqual(v.engine, "seqkit")
        self.assertTrue(ok)

    def test_seqkit_flags_structural(self):
        # Structurally broken FASTQ: quality length != sequence length.
        path = _write(self.dir, "bad.fastq", "@r1\nACGTACGT\n+\nIII\n")
        v = SequenceValidator(path, use_seqkit=True)
        ok = v.validate()
        self.assertEqual(v.engine, "seqkit")
        self.assertFalse(ok)
        self.assertTrue(v.get_errors())

    def test_seqkit_flags_invalid_alphabet(self):
        # Stray characters must be rejected (seqkit auto-guess would miss them,
        # so the wrapper pins --seq-type dna).
        path = _write(self.dir, "bad.fasta", ">s1\nACGZ1T\n")
        v = SequenceValidator(path, use_seqkit=True, strict=True)
        self.assertFalse(v.validate())
        self.assertEqual(v.engine, "seqkit")

    def test_seqkit_non_strict_skips_alphabet(self):
        # Same stray characters pass when the alphabet check is off.
        path = _write(self.dir, "weird.fasta", ">s1\nACGZ1T\n")
        v = SequenceValidator(path, use_seqkit=True, strict=False)
        self.assertTrue(v.validate())
        self.assertEqual(v.engine, "seqkit")


def _run_on_file(path, strict=True, use_seqkit=True, timeout=None):
    """Validate a single file, print the outcome. Return True if valid."""
    import time

    if use_seqkit and not SEQKIT_AVAILABLE:
        print("Warning: seqkit not installed, using builtin validator")
    v = SequenceValidator(path, use_seqkit=use_seqkit, strict=strict, timeout=timeout)
    start = time.perf_counter()
    ok = v.validate()
    elapsed = time.perf_counter() - start
    status = "VALID" if ok else "INVALID"
    mode = "strict" if strict else "structural"
    print(f"[{status}] {path} (engine={v.engine}, mode={mode}, time={elapsed:.3f}s)")
    if not ok:
        v.print_errors()
    return ok


if __name__ == "__main__":
    import sys

    # Usage: python -m ...test_fasta_validation [--no-strict] [--no-seqkit] [FILE ...]
    strict = "--no-strict" not in sys.argv[1:]
    use_seqkit = "--no-seqkit" not in sys.argv[1:]
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    if files:
        rc = 0
        for f in files:
            if not _run_on_file(f, strict=strict, use_seqkit=use_seqkit, timeout=60):
                rc = 1
        sys.exit(rc)
    unittest.main()
