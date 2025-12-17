from ..core import KmindexWrapper, KmtricksIndex, KmindexRegistry, Toolbox
from ..operations import FofManager
import os
from typing import Any


class IndexBuilder:
    def __init__(self, output_index_path: str, k=31, z=6) -> None:
        """Initialize the IndexBuilder."""
        self._path = Toolbox.get_canonical_path(output_index_path)
        os.makedirs(self.path, exist_ok=True)
        self._registry = KmindexRegistry(os.path.join(self.path, "registry"))
        assert z >= 0 and k > z
        self._k = k
        self._z = z

    @property
    def index(self) -> KmindexRegistry:
        return self._registry

    @property
    def path(self) -> str:
        return self._path

    @property
    def k(self) -> int:
        return self._k

    @property
    def z(self) -> int:
        return self._z

    @property
    def s(self) -> int:
        return self.k - self.z

    def create_subindex(
        self,
        name: str,
        samples: dict[str, str],
        assembled: bool,
        bloom_size: int,
        n_partitions: int = 256,
        n_threads: int = 0,
        n_max_threads: int = 0,
        auto_check: bool = True,
    ) -> None:

        assert samples
        assert bloom_size
        assert name
        assert not self.index.has_index(name)

        wrapper = KmindexWrapper()
        fof = FofManager(samples=samples)
        fof_path = os.path.join(self.path, f"{name}.fof")
        fof.save(fof_path=fof_path)
        hard_min = 1 if assembled else 2

        if n_threads == 0:
            n_threads = os.cpu_count() or 1
        n_threads = max(n_threads, 1)
        if n_max_threads > 0:
            n_threads = min(n_threads, n_max_threads)

        n_partitions = max(n_partitions, 0)

        wrapper.build(
            input_fof_file=fof_path,
            output_registry_path=self.index.root_path,
            output_index_dir=os.path.join(self.path, ".subindexes"),
            k=self.s,
            hard_min=hard_min,
            threads=n_threads,
            nb_partitions=n_partitions,
            register_as=name,
            bloom_size=bloom_size,
        )

        self.index.load_json()

        if auto_check:
            assert self.index.has_index(name)
            idx = self.index.get_index(name)

            if n_partitions > 0 :
                assert idx.nb_partitions == n_partitions

            assert idx.bloom_size == bloom_size
            assert idx.kmer_size == self.k
            self.check_index(name)


    def check_index(
        self,
        name: str,
    ):
        idx = self.index.get_index(name)
        idx.check_structure()


