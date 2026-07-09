"""Unit tests for ByteCounter and the SizeFormat/SizeUnit enums.

Covers the v0.6.3 changes to ``pykmhelpers.core.byte``: the renumbered
``SizeFormat`` enum (``NONE`` added, ``BYTE``/``BIBYTE``/``BIT`` shifted), the
default-format passthrough in ``convert``, and the new ``to_str`` helper.
"""

import unittest

from pykmhelpers.core.byte import ByteCounter, SizeFormat, SizeUnit


class TestSizeEnums(unittest.TestCase):
    """Tests for the SizeFormat / SizeUnit enum values (renumbered in 0.6.3)."""

    def test_size_format_values(self):
        self.assertEqual(SizeFormat.NONE.value, 0)
        self.assertEqual(SizeFormat.BYTE.value, 1)
        self.assertEqual(SizeFormat.BIBYTE.value, 2)
        self.assertEqual(SizeFormat.BIT.value, 3)

    def test_size_unit_values(self):
        self.assertEqual(SizeUnit.NONE.value, 0)
        self.assertEqual(SizeUnit.KILO.value, 1)
        self.assertEqual(SizeUnit.MEGA.value, 2)
        self.assertEqual(SizeUnit.GIGA.value, 3)
        self.assertEqual(SizeUnit.TERA.value, 4)
        self.assertEqual(SizeUnit.PETA.value, 5)


class TestByteCounterConversion(unittest.TestCase):
    """Tests for ByteCounter byte/bit accounting and unit conversion."""

    def test_byte_and_bit_count(self):
        bc = ByteCounter(2000)
        self.assertEqual(bc.byte_count, 2000)
        self.assertEqual(bc.bit_count, 16000)

    def test_bibyte_scaling(self):
        """1 KiB is 1024 bytes (BIBYTE uses a 1024 factor)."""
        self.assertEqual(ByteCounter(1, SizeUnit.KILO, SizeFormat.BIBYTE).byte_count, 1024)

    def test_bit_format_rounds_up_to_bytes(self):
        """8 bits round up to exactly 1 byte."""
        self.assertEqual(ByteCounter(8, SizeUnit.NONE, SizeFormat.BIT).byte_count, 1)

    def test_convert_to_kilo(self):
        bc = ByteCounter(2000).convert(SizeUnit.KILO)
        self.assertEqual(bc.unit, SizeUnit.KILO)
        self.assertEqual(bc.value, 2)

    def test_convert_default_format_passthrough(self):
        """convert(format=NONE) keeps the receiver's own format (0.6.3 behavior)."""
        bibyte = ByteCounter(1, SizeUnit.KILO, SizeFormat.BIBYTE)
        self.assertEqual(bibyte.convert(SizeUnit.NONE).format, SizeFormat.BIBYTE)


class TestByteCounterStr(unittest.TestCase):
    """Tests for string rendering and the new to_str helper."""

    def test_str_suffix_by_format(self):
        self.assertTrue(str(ByteCounter(2, SizeUnit.KILO, SizeFormat.BYTE)).endswith("KB"))
        self.assertTrue(str(ByteCounter(2, SizeUnit.KILO, SizeFormat.BIBYTE)).endswith("KiB"))
        self.assertTrue(str(ByteCounter(2, SizeUnit.KILO, SizeFormat.BIT)).endswith("Kb"))

    def test_to_str_matches_convert_str(self):
        bc = ByteCounter(2000)
        self.assertEqual(bc.to_str(SizeUnit.KILO), str(bc.convert(SizeUnit.KILO)))
        self.assertEqual(bc.to_str(SizeUnit.KILO), "2KB")


class TestByteCounterAuto(unittest.TestCase):
    """Tests for the auto() best-unit picker."""

    def test_auto_picks_mega(self):
        self.assertEqual(str(ByteCounter.auto(1_500_000)), "1.5MB")

    def test_auto_bibyte_uses_1024_factor(self):
        self.assertEqual(str(ByteCounter.auto(1_500_000, SizeFormat.BIBYTE)), "1.43MiB")

    def test_auto_small_stays_none_unit(self):
        self.assertEqual(ByteCounter.auto(512).unit, SizeUnit.NONE)


if __name__ == "__main__":
    unittest.main()
