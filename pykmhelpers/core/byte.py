try:
    from typing import Self
except ImportError:
    from typing_extensions import Self
from enum import Enum, IntEnum
from dataclasses import dataclass


class SizeFormat(Enum):
    BYTE = 0
    BIBYTE = 1
    BIT = 2


class SizeUnit(IntEnum):
    NONE = 0
    KILO = 1
    MEGA = 2
    GIGA = 3
    TERA = 4
    PETA = 5


@dataclass
class ByteCounter:
    value: float = 0
    unit: SizeUnit = SizeUnit.NONE
    format: SizeFormat = SizeFormat.BYTE

    def __init__(
        self,
        value: float = 0,
        unit: SizeUnit = SizeUnit.NONE,
        format: SizeFormat = SizeFormat.BYTE,
    ):
        self.value = value
        self.unit = unit
        self.format = format

    @property
    def byte_count(self):
        """Get the value converted to bytes."""
        factor = 1024 if self.format == SizeFormat.BIBYTE else 1000
        byte_value = self.value * (factor ** int(self.unit))

        if self.format == SizeFormat.BIT:
            byte_value = (byte_value + 7) // 8

        return int(byte_value)

    @property
    def bit_count(self):
        return self.byte_count * 8

    def convert(
        self, unit: SizeUnit = SizeUnit.NONE, format: SizeFormat = SizeFormat.BYTE
    ) -> "ByteCounter":
        """Convert to a different unit and format, returning a new ByteCounter."""
        byte_value = self.byte_count * 8 if format == SizeFormat.BIT else 1
        target_factor = 1024 if format == SizeFormat.BIBYTE else 1000
        converted_value = byte_value / (target_factor ** int(unit))
        return ByteCounter(converted_value, unit, format)

    @classmethod
    def auto(
        cls, byte_count: int, format: SizeFormat = SizeFormat.BYTE
    ) -> "ByteCounter":
        """Automatically determine the best unit for the given byte count."""
        if format == SizeFormat.BIT:
            byte_count = byte_count * 8

        factor = 1024 if format == SizeFormat.BIBYTE else 1000

        # Determine the best unit by finding the largest unit where value >= 1
        unit = SizeUnit.NONE
        value = byte_count

        for candidate_unit in [
            SizeUnit.KILO,
            SizeUnit.MEGA,
            SizeUnit.GIGA,
            SizeUnit.TERA,
            SizeUnit.PETA,
        ]:
            scaled_value = byte_count / (factor ** int(candidate_unit))
            if scaled_value >= 1:
                unit = candidate_unit
                value = scaled_value
            else:
                break

        return cls(value, unit, format)

    @classmethod
    def from_str(cls, s: str) -> "ByteCounter":
        """Parse a ByteCounter from a human-readable string (e.g., '1.5GB', '256MB', '1.2KiB')."""
        s = s.strip()

        # Map unit prefixes to SizeUnit
        unit_map = {
            "K": SizeUnit.KILO,
            "M": SizeUnit.MEGA,
            "G": SizeUnit.GIGA,
            "T": SizeUnit.TERA,
            "P": SizeUnit.PETA,
        }

        # Determine format suffix
        format_type = SizeFormat.BYTE
        if s.endswith("b"):
            format_type = SizeFormat.BIT
            s = s[:-1]
        elif s.endswith("iB"):
            format_type = SizeFormat.BIBYTE
            s = s[:-2]
        elif s.endswith("B"):
            s = s[:-1]

        # Extract unit
        unit = SizeUnit.NONE
        if s and s[-1] in unit_map:
            unit = unit_map[s[-1]]
            s = s[:-1]

        # Parse value
        s = s.strip()
        value = float(s)

        return cls(value, unit, format_type)

    def __add__(self, other: "ByteCounter") -> "ByteCounter":
        """Add two ByteCounters, converting to the same unit."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"unsupported operand type(s) for +: 'ByteCounter' and '{type(other).__name__}'"
            )

        # Convert both to bytes and add
        result_bytes = self.byte_count + other.byte_count
        return type(self).auto(result_bytes, self.format)

    def __sub__(self, other: "ByteCounter") -> "ByteCounter":
        """Subtract two ByteCounters, converting to the same unit."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"unsupported operand type(s) for -: 'ByteCounter' and '{type(other).__name__}'"
            )

        # Convert both to bytes and subtract
        result_bytes = self.byte_count - other.byte_count
        return type(self).auto(result_bytes, self.format)

    def __mul__(self, scalar: float) -> "ByteCounter":
        """Multiply ByteCounter by a scalar value."""
        if not isinstance(scalar, (int, float)):
            raise TypeError(
                f"unsupported operand type(s) for *: 'ByteCounter' and '{type(scalar).__name__}'"
            )

        result_bytes = int(self.byte_count * scalar)
        return type(self).auto(result_bytes, self.format)

    def __rmul__(self, scalar: float) -> "ByteCounter":
        """Right multiplication for scalar * ByteCounter."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> "ByteCounter":
        """Divide ByteCounter by a scalar value."""
        if not isinstance(scalar, (int, float)):
            raise TypeError(
                f"unsupported operand type(s) for /: 'ByteCounter' and '{type(scalar).__name__}'"
            )

        if scalar == 0:
            raise ZeroDivisionError("Cannot divide ByteCounter by zero")

        result_bytes = int(self.byte_count / scalar)
        return type(self).auto(result_bytes, self.format)

    def __floordiv__(self, scalar: float) -> "ByteCounter":
        """Floor divide ByteCounter by a scalar value."""
        if not isinstance(scalar, (int, float)):
            raise TypeError(
                f"unsupported operand type(s) for //: 'ByteCounter' and '{type(scalar).__name__}'"
            )

        if scalar == 0:
            raise ZeroDivisionError("Cannot divide ByteCounter by zero")

        result_bytes = self.byte_count // int(scalar)
        return type(self).auto(result_bytes, self.format)

    def __eq__(self, other: object) -> bool:
        """Check equality based on byte count."""
        if not isinstance(other, ByteCounter):
            return False
        return self.byte_count == other.byte_count

    def __lt__(self, other: Self) -> bool:
        """Check if less than another ByteCounter."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"'<' not supported between instances of 'ByteCounter' and '{type(other).__name__}'"
            )
        return self.byte_count < other.byte_count

    def __le__(self, other: Self) -> bool:
        """Check if less than or equal to another ByteCounter."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"'<=' not supported between instances of 'ByteCounter' and '{type(other).__name__}'"
            )
        return self.byte_count <= other.byte_count

    def __gt__(self, other: Self) -> bool:
        """Check if greater than another ByteCounter."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"'>' not supported between instances of 'ByteCounter' and '{type(other).__name__}'"
            )
        return self.byte_count > other.byte_count

    def __ge__(self, other: Self) -> bool:
        """Check if greater than or equal to another ByteCounter."""
        if not isinstance(other, ByteCounter):
            raise TypeError(
                f"'>=' not supported between instances of 'ByteCounter' and '{type(other).__name__}'"
            )
        return self.byte_count >= other.byte_count

    def __ne__(self, other: object) -> bool:
        """Check inequality based on byte count."""
        return not self.__eq__(other)

    def __str__(self) -> str:
        """String representation of the ByteCounter."""
        unit_names = {
            SizeUnit.NONE: "",
            SizeUnit.KILO: "K",
            SizeUnit.MEGA: "M",
            SizeUnit.GIGA: "G",
            SizeUnit.TERA: "T",
            SizeUnit.PETA: "P",
        }

        if self.format == SizeFormat.BIT:
            format_suffix = "b"
        elif self.format == SizeFormat.BIBYTE:
            format_suffix = "iB"
        else:
            format_suffix = "B"

        unit_str = unit_names.get(self.unit, "")
        return f"{self.value:.4g}{unit_str}{format_suffix}"
