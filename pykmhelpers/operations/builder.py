import datetime
import logging
import os
import shutil
import threading
from typing import IO, Optional

import yaml

from ..core import (
    BloomFilterSpecs,
    KmindexRegistry,
    KmindexWrapper,
    KmtricksIndex,
    Toolbox,
)
from ..core.byte import ByteCounter, SizeFormat
from ..core.fasta import Fasta, FASTAReader
from ..pipeline.fof import FofManager
from ..pipeline.query import KmindexQuery, KmindexQueryResult

logger = logging.getLogger(__name__)


class IndexBuilder:
    class Progress:
        def __init__(self, on_change, delay: int = 30):
            self._delay: int = delay
            self._progress: float = 0
            self._on_change = on_change

        @property
        def delay(self) -> int:
            return self._delay

        @property
        def progress(self) -> float:
            return self._progress

        @progress.setter
        def progress(self, value: float):
            p = self._progress
            self._progress = value
            if p != value:
                self._on_change(value)

    def __init__(
        self,
        workdir: str,
        registry_name="registry",
        data_folder=".subindexes",
        log_folder="logs",
        assets_folder="assets",
        script_out: Optional[IO[str]] = None,
    ) -> None:
        """Initialize the IndexBuilder."""
        self._path = Toolbox.get_canonical_path(workdir)
        os.makedirs(self.path, exist_ok=True)
        self._registry_name = registry_name
        self._data_folder = data_folder
        self._log_folder = log_folder
        self._registry = KmindexRegistry(self.registry_path)
        self._assets_folder = assets_folder
        self._script_out = script_out

    @property
    def index(self) -> KmindexRegistry:
        return self._registry

    @property
    def path(self) -> str:
        return self._path

    @property
    def registry_name(self) -> str:
        return self._registry_name

    @property
    def registry_path(self) -> str:
        return os.path.join(self.path, self.registry_name)

    @property
    def data_folder(self) -> str:
        return os.path.join(self.path, self._data_folder)

    @property
    def log_folder(self) -> str:
        return os.path.join(self.path, self._log_folder)

    @property
    def assets_folder(self) -> str:
        return os.path.join(self.path, self._assets_folder)

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
            logger.warning(f"Could not add sample in FOF: {e}")

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
        self,
        bf_specs: BloomFilterSpecs,
    ) -> ByteCounter:
        return ByteCounter.auto(bf_specs.total_storage_size(), SizeFormat.BYTE)

    def create_subindex(
        self,
        name: str,
        samples: FofManager,
        bloom_size: int,
        kmer_size: int = 25,
        abundance_min: int = 2,
        n_partitions: int = 256,
        n_threads: int = 0,
        n_max_threads: int = 0,
        build_from: Optional[str] = None,
        auto_check: bool = True,
        minim_size: int = 10,
        compress_intermediate: bool = True,
        dry_run: bool = False,
        on_existing: str = "fail",
        progress: Optional[Progress] = None,
    ) -> dict:

        assert (
            samples and samples.get_sample_count()
        ), "Samples dictionary cannot be empty"
        assert bloom_size, "Bloom size must be specified and greater than 0"
        assert name, "Index name cannot be empty"
        assert not self.index.has_index(
            name
        ), f"Index '{name}' already exists in registry"

        if not dry_run:
            assert samples.validate_sample_files(), "Some sample files are missing"

        wrapper = KmindexWrapper(dry_run=dry_run)
        fof_path = os.path.join(self.assets_folder, f"{name}.fof")
        samples.save(fof_path=fof_path)

        if n_threads == 0:
            n_threads = os.cpu_count() or 1
        n_threads = max(n_threads, 1)
        if n_max_threads > 0:
            n_threads = min(n_threads, n_max_threads)

        n_partitions = max(n_partitions, 0)

        bf_specs = self.get_bf_specs(
            n_samples=samples.get_sample_count(),
            bloom_size=bloom_size,
            n_partitions=max(256, n_partitions),
        )

        self.index.load_json()

        if build_from:
            if self.index.has_index(build_from) or dry_run:
                logger.info(f"Reusing parameters from index: {build_from}")
            elif name != build_from:
                logger.warning(
                    f"Index '{build_from}' not found, building '{name}' from scratch"
                )
                build_from = None

        output_basedir = os.path.join(self.path, self.data_folder)
        output_indexdir = os.path.join(output_basedir, name)

        if not dry_run and os.path.exists(output_indexdir):
            if on_existing == "fail":
                raise FileExistsError(f"Directory already exists: {output_indexdir}")
            elif on_existing == "rename":
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                logger.info(
                    f"Rename {output_indexdir} to {os.path.basename(output_indexdir)}_{timestamp}"
                )
                shutil.move(output_indexdir, f"{output_indexdir}_{timestamp}")
            elif on_existing == "replace":
                logger.info(f"Delete {output_indexdir}")
                shutil.rmtree(
                    output_indexdir,
                )
            elif on_existing in (
                "register",
                "register_or_replace",
                "register_or_rename",
            ):
                try:
                    r = self.index.add_index(KmtricksIndex(output_basedir, name))
                except:
                    r = False
                if r == False:
                    if on_existing == "register_or_replace":
                        logger.info(f"Delete {output_indexdir}")
                        shutil.rmtree(output_indexdir)
                    elif on_existing == "register_or_rename":
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        logger.info(
                            f"Rename {output_indexdir} to {os.path.basename(output_indexdir)}_{timestamp}"
                        )
                        shutil.move(output_indexdir, f"{output_indexdir}_{timestamp}")
                else:
                    return {"register": True}
            else:
                raise ValueError(
                    f"Unknown value for parameter 'on_existing': {on_existing}"
                )

        progress_handler = None
        stop_event = None

        if not dry_run and progress and progress.delay > 0:
            stop_event = threading.Event()

            def _progress_worker():
                while not stop_event.wait(timeout=progress.delay):
                    total_size = 0
                    for p in range(n_partitions):
                        m_path = wrapper.get_matrix_path(output_indexdir, p, False)
                        if os.path.isfile(m_path):
                            try:
                                total_size += os.stat(m_path).st_size
                            except Exception as e:
                                logger.debug(e)
                    progress.progress = (1.0 * total_size) / bf_specs.total_byte_count()

            progress_handler = threading.Thread(target=_progress_worker, daemon=True)
            progress_handler.start()

        result = wrapper.build(
            input_fof_file=fof_path,
            output_registry_path=self.index.root_path,
            output_index_dir=output_basedir,
            k=kmer_size,
            hard_min=abundance_min,
            threads=n_threads,
            nb_partitions=n_partitions,
            register_as=name,
            bloom_size=bloom_size,
            output_log_dir=os.path.join(self.log_folder, name),
            output_param_file=os.path.join(self.assets_folder, f"{name}.yaml"),
            from_index=build_from,
            compress_intermediate=compress_intermediate,
            minim_size=minim_size,
        )

        if stop_event:
            stop_event.set()

        if progress_handler:
            progress_handler.join()

        if not dry_run:
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
                    idx.kmer_size == kmer_size
                ), f"K-mer size mismatch: expected {kmer_size}, got {idx.kmer_size}"
                self.check_index_structure(name)

        return result

    def merge(
        self,
        new_name: str,
        to_merge: list[str],
        rename: Optional[str] = None,
        delete_old: bool = True,
        threads: int = 14,
        dry_run: bool = False,
    ):
        """Merge sub-indexes into a single index via KmindexWrapper.merge."""
        self.index.load_json()

        if not dry_run:
            missing = [name for name in to_merge if not self.index.has_index(name)]
            if missing:
                raise ValueError(f"Sub-indexes not found in registry: {missing}")

        wrapper = KmindexWrapper(dry_run=dry_run)
        result = wrapper.merge(
            input_registry=self.index.root_path,
            new_name=new_name,
            new_path=os.path.join(self.data_folder, new_name),
            to_merge=to_merge,
            rename=rename,
            delete_old=delete_old,
            threads=threads,
        )

        if not dry_run:
            self.index.load_json()
            assert self.index.has_index(
                new_name
            ), f"Merged index '{new_name}' not found after merge"

        return result

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
                    logger.warning(f"Failed to extract sequences from {path}: {str(e)}")

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
                            logger.info(f"Query {input_path} into {output_dir}")
                            query = KmindexQuery(path=input_path)
                            query.execute(
                                registry_path=self.index.root_path,
                                output_dir=output_dir,
                                z=z,
                            )
                        except Exception as e:
                            logger.error(f"Failed to query {input_path}: {str(e)}")

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
                logger.error(f"Sample score is not 100%: {s} = {v}")
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
