from dataclasses import dataclass


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
