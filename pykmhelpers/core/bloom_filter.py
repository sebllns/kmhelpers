import math

KMINDEX_HEADER_SIZE: int = 49
BYTE_SIZE: int = 8
ENCODED_BITLENGTH: int = 64


class BloomFilterSpecs:
    def __init__(self, n_rows: int, n_cols: int, n_partitions: int):
        self._n_parts = n_partitions
        self._n_rows = n_rows
        self._n_cols = n_cols

        # assert (
        #     self.n_cols % BYTE_SIZE == 0
        # ), f"Columns must be divisible by {BYTE_SIZE} (got {self.n_cols})"
        # assert (
        #     self.n_rows % ENCODED_BITLENGTH == 0
        # ), f"Rows must be divisible by {ENCODED_BITLENGTH} (got {self.n_rows})"

    @property
    def rows(self) -> int:
        return self._n_rows

    @property
    def cols(self) -> int:
        return self._n_cols

    @property
    def parts(self) -> int:
        return self._n_parts

    def row_byte_count(self) -> int:
        return (self.cols + BYTE_SIZE - 1) // BYTE_SIZE

    def column_byte_count(self) -> int:
        return (
            int(
                (
                    (self.rows / self.parts + ENCODED_BITLENGTH - 1)
                    // ENCODED_BITLENGTH
                )
                * ENCODED_BITLENGTH
                * self.parts
            )
        )

    def total_byte_count(self):
        return self.row_byte_count() * self.column_byte_count()

    def total_storage_size(self):
        return self.total_byte_count() + self._n_parts * KMINDEX_HEADER_SIZE

    def partition_file_size(self):
        return KMINDEX_HEADER_SIZE + self.total_byte_count() // self.parts

    def get_auto_partition_count(self, max_partition_size: int):
        return 1 + self.total_byte_count() // max_partition_size


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
