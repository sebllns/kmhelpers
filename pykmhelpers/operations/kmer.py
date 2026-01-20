from .sequence import Sequence


class Kmer(Sequence):

    def __init__(self, seq: str, k: int = 0, header: str = ""):
        if k == 0:
            k = len(seq)
        if len(seq) != k:
            raise ValueError(f"Sequence length {len(seq)} doesn't match k={k}")
        super().__init__(content=seq, header=header)
        self._k = k

    @property
    def k(self):
        return self._k

