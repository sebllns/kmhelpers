from ..core import (
    KmindexWrapper,
    KmtricksIndex,
    KmindexRegistry,
    Toolbox,
    BloomFilterSpecs,
)
from ..core.byte import ByteCounter, SizeFormat
from ..pipeline.fof import FofManager
from ..core.fasta import Fasta, FASTAReader
from ..pipeline.query import KmindexQuery, KmindexQueryResult
from typing import Optional
import os
import yaml


class IndexBuilder:
    def __init__(self, output_index_path: str, k=25) -> None:
        """Initialize the IndexBuilder."""
        self._path = Toolbox.get_canonical_path(output_index_path)
        os.makedirs(self.path, exist_ok=True)
        self._registry = KmindexRegistry(os.path.join(self.path, "registry"))
        self._k = k

    @property
    def index(self) -> KmindexRegistry:
        return self._registry

    @property
    def path(self) -> str:
        return self._path

    @property
    def k(self) -> int:
        return self._k

    def load_metadata(self, file: str):
        """
        Docstring for load_metadata

        :param self: Description
        :param file: Description
        :type file: str
        """
        with open(file, "r") as f:
            tmp = yaml.safe_load(f)
            return {s["sample_id"]: s for s in tmp["samples"]}
        return None

    def has_subindex(self, name: str):
        return self.index.has_index(name)

    def add_sample_to_fof(self, sample, fof: FofManager) -> None:
        try:
            sample_id = sample["sample_id"]
            sample_path = sample["file_path"]
            assert sample_id, "Sample ID cannot be empty"
            assert not fof.has_sample(
                sample_id
            ), f"Sample ID already present in FOF: {sample_id}"
            fof.add_sample(sample_path, sample_id)
        except Exception as e:
            print(f"Could not add sample in FOF: {e}")

    def create_fof(self, samples) -> FofManager:
        """
        Docstring for create_fof

        :param self: Description
        :param samples: Description
        :return: Description
        :rtype: FofManager
        """
        fof = FofManager()
        for s in samples:
            self.add_sample_to_fof(s, fof)
        return fof

    def get_bf_specs(
        self, n_samples: int, bloom_size: int, n_partitions: int
    ) -> BloomFilterSpecs:
        return BloomFilterSpecs(
            n_cols=n_samples, n_rows=bloom_size, n_partitions=n_partitions
        )

    def get_storage_size(
        self, bf_specs: BloomFilterSpecs, n_partitions: int
    ) -> ByteCounter:
        return ByteCounter.auto(bf_specs.total_storage_size(), SizeFormat.BYTE)

    def create_subindex(
        self,
        name: str,
        samples: FofManager,
        assembled: bool,
        bloom_size: int,
        n_partitions: int = 256,
        n_threads: int = 0,
        n_max_threads: int = 0,
        build_from: Optional[str] = None,
        auto_check: bool = True,
    ) -> KmtricksIndex:
        """
        Docstring for create_subindex

        :param self: Description
        :param name: Description
        :type name: str
        :param samples: Description
        :type samples: FofManager
        :param assembled: Description
        :type assembled: bool
        :param bloom_size: Description
        :type bloom_size: int
        :param n_partitions: Description
        :type n_partitions: int
        :param n_threads: Description
        :type n_threads: int
        :param n_max_threads: Description
        :type n_max_threads: int
        :param auto_check: Description
        :type auto_check: bool
        :return: Description
        :rtype: KmtricksIndex
        """

        assert (
            samples and samples.get_sample_count()
        ), "Samples dictionary cannot be empty"
        assert samples.validate_sample_files(), "Some sample files are missing"
        assert bloom_size, "Bloom size must be specified and greater than 0"
        assert name, "Index name cannot be empty"
        assert not self.index.has_index(
            name
        ), f"Index '{name}' already exists in registry"

        wrapper = KmindexWrapper()
        fof_path = os.path.join(self.path, f"{name}.fof")
        samples.save(fof_path=fof_path)
        hard_min = 1 if assembled else 2

        if n_threads == 0:
            n_threads = os.cpu_count() or 1
        n_threads = max(n_threads, 1)
        if n_max_threads > 0:
            n_threads = min(n_threads, n_max_threads)

        n_partitions = max(n_partitions, 0)

        n_samples = samples.get_sample_count()

        # bf_specs = self.get_bf_specs(n_samples, bloom_size, n_partitions)

        wrapper.build(
            input_fof_file=fof_path,
            output_registry_path=self.index.root_path,
            output_index_dir=os.path.join(self.path, ".subindexes"),
            k=self.k,
            hard_min=hard_min,
            threads=n_threads,
            nb_partitions=n_partitions,
            register_as=name,
            bloom_size=bloom_size,
            output_log_dir=os.path.join(self.path, "logs", name),
            output_param_file=os.path.join(self.index.root_path, f"{name}.yaml"),
            from_index=build_from
        )

        self.index.load_json()
        assert self.index.has_index(
            name
        ), f"Index '{name}' was not successfully created"
        idx = self.index.get_index(name)

        if auto_check:
            if n_partitions > 0:
                assert (
                    idx.nb_partitions == n_partitions
                ), f"Partition count mismatch: expected {n_partitions}, got {idx.nb_partitions}"

            # assert (
            #     idx.bloom_size == bloom_size
            # ), f"Bloom size mismatch: expected {bloom_size}, got {idx.bloom_size}"
            assert (
                idx.kmer_size == self.k
            ), f"K-mer size mismatch: expected {self.k}, got {idx.kmer_size}"
            self.check_index_structure(name)

        return idx

    def check_index_structure(
        self,
        name: str,
    ):
        idx = self.index.get_index(name)
        idx.check_structure()

    def create_test_dataset(
        self, idx: KmtricksIndex, output_dir: str, n_samples: int = 5, max_length=2000
    ):
        """
        Create test dataset by extracting sequences from the index.

        :param idx: The kmtricks index to extract sequences from
        :type idx: KmtricksIndex
        :param output_dir: Output directory for test FASTA files
        :type output_dir: str
        :param n_samples: Number of samples to extract
        :type n_samples: int
        """
        os.makedirs(output_dir, exist_ok=True)
        fof = FofManager(idx.fof_path)
        i = 0
        for s in idx:
            if i >= n_samples:
                break
            path = fof.get_sample_path(s)
            if path and os.path.isfile(path):
                i += 1
                try:
                    reader = FASTAReader(path)
                    output_file = os.path.join(output_dir, f"{s}.fasta")
                    with open(output_file, "w") as f:
                        f.write(reader.fetch_first_n(max_length).to_fasta())
                except Exception as e:
                    print(f"Warning: Failed to extract sequences from {path}: {str(e)}")

    def create_random_test_dataset(
        self, output_dir: str, n_samples: int = 5, average_size=1000, min_size=100
    ):
        """
        Create random sequences FASTA files for testing.

        :param output_dir: Output directory for test FASTA files
        :type output_dir: str
        :param n_samples: Number of random sequences to generate
        :type n_samples: int
        """
        os.makedirs(output_dir, exist_ok=True)
        fasta = Fasta()
        fasta.fill_random(
            num_sequences=n_samples, average_size=average_size, min_size=min_size
        )
        for i, sequence in enumerate(fasta):
            output_file = os.path.join(output_dir, f"sequence_{i}.fasta")
            with open(output_file, "w") as f:
                f.write(sequence.to_fasta())

    def query_test_dataset(self, dataset: str, output_dir: str, z: int):
        """
        Query a whole directory (recursive) containing FASTA files.

        Recursively searches the dataset directory for FASTA files and queries them
        against the index, recreating the same structure in the output directory.

        :param idx: The kmtricks index to query against
        :type idx: KmtricksIndex
        :param dataset: Path to directory containing FASTA files
        :type dataset: str
        :param output_dir: Output directory to store query results
        :type output_dir: str
        """
        os.makedirs(output_dir, exist_ok=True)
        for root, dirs, files in os.walk(dataset):
            for file in files:
                if file.endswith((".fasta", ".fa", ".fna")):
                    input_path = os.path.join(root, file)
                    rel_path = os.path.relpath(root, dataset)
                    result_dir = os.path.join(output_dir, rel_path)
                    output_dir = os.path.join(result_dir, file.replace(".", "_"))

                    if not output_dir:
                        os.makedirs(result_dir, exist_ok=True)
                        try:
                            print(f"Query {input_path} into {output_dir}")
                            query = KmindexQuery(path=input_path)
                            query.execute(
                                registry_path=self.index.root_path,
                                output_dir=output_dir,
                                z=z,
                            )
                        except Exception as e:
                            print(f"Warning: Failed to query {input_path}: {str(e)}")

    def check_presence(self, results: str, samples: list[str]):
        """
        Check presence of samples in query results.

        :param results: Path to query results directory
        :type results: str
        :param samples: List of sample names to check
        :type samples: list[str]
        """
        r = KmindexQueryResult(results)
        ok = True
        for s in samples:
            v = r.max_score(s)
            if v < 1:
                print(f"Sample score is not 100%: {s} = {v}")
                ok = False
        return ok

    def compare_results(self, results: str, ground_truth: str):
        """
        Compare query results against ground truth.

        :param results: Path to query results directory
        :type results: str
        :param ground_truth: Path to ground truth results directory
        :type ground_truth: str
        """
        return KmindexQueryResult(results) == KmindexQueryResult(ground_truth)
