class KmerOperation:
    def __init__(self, k: int):
        self._k = k

    @property
    def k(self):
        return self._k
