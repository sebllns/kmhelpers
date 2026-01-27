from dataclasses import dataclass
import math


@dataclass
class BloomFilterSpecs:
    n_rows: int = 0
    n_cols: int = 0

    def __init__(self, n_rows: int, n_cols: int):
        self.n_rows = n_rows
        self.n_cols = n_cols

    @property
    def row_byte_count(self) -> int:
        return (self.n_rows + 7) // 8

    @property
    def column_byte_count(self) -> int:
        return self.n_cols

    @property
    def total_byte_count(self):
        return self.row_byte_count * self.column_byte_count

    def partition_byte_count(self, n_partitions: int):
        return self.total_byte_count / n_partitions

    def get_partition_count(self, max_partition_size: int):
        return 1 + self.total_byte_count // max_partition_size


class SpanManager:
    def __init__(self, p=0.25) -> None:
        assert p > 0, f"Constraint must be respected: p > 0 (got p = {p})"
        self._p = p
        self._f = -math.log(self._p) / (math.log(2) ** 2)

    def dispatch(self, kmer_count):
        assert (
            kmer_count > 0
        ), "Constraint must be respected: kmer_count > 0 (got kmer_count = {kmer_count})"
        s = int(math.log2(kmer_count))
        assert s > 0, f"Constraint must be respected: s > 0 (got s = {s})"
        return s

    def get_bf_size(self, span):
        # Calculate real Bloom filter size
        return ((int(self._f * (2 ** (span + 1))) + 7) // 8) * 8
