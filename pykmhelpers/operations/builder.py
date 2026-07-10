import datetime
import logging
import os
import re
import shutil
import threading
import typing

import yaml

import pykmhelpers.core.byte
import pykmhelpers.core.fasta
import pykmhelpers.core.kmindex_paths
import pykmhelpers.pipeline.fof
import pykmhelpers.pipeline.query

logger = logging.getLogger(__name__)


class IndexBuilder:
    class Progress:
        """Polls build progress on a timer and reports changes via a callback.

        Used by `create_subindex` to periodically estimate build progress
        from the on-disk matrix file sizes and notify a caller-supplied
        callback whenever the estimate changes.
        """

        def __init__(self, on_change, delay: int = 30):
            """Initialize the progress tracker.

            Args:
                on_change (Callable[[float], None]): Called with the new
                    progress value (0.0-1.0) whenever it changes.
                delay (int): Seconds between progress checks.
            """
            self._delay: int = delay
            self._progress: float = 0
            self._on_change = on_change

        @property
        def delay(self) -> int:
            """int: Seconds between progress checks."""
            return self._delay

        @property
        def progress(self) -> float:
            """float: Last known progress, in [0.0, 1.0]."""
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
        script_out: typing.Optional[typing.IO[str]] = None,
    ) -> None:
        """Initialize the IndexBuilder.

        Args:
            workdir (str): Working directory holding the registry, sub-index
                data, logs, and assets. Created if it does not already exist.
            registry_name (str): Filename of the kmindex registry, relative
                to `workdir`.
            data_folder (str): Subdirectory of `workdir` where sub-index data
                is stored.
            log_folder (str): Subdirectory of `workdir` where build logs are
                written.
            assets_folder (str): Subdirectory of `workdir` where generated
                assets (FOF and parameter files) are written.
            script_out (typing.Optional[typing.IO[str]]): Optional stream to
                write the underlying kmindex shell commands to, for debugging
                or replay.
        """
        self._path = pykmhelpers.core.Toolbox.get_canonical_path(workdir)
        os.makedirs(self.path, exist_ok=True)
        self._registry_name = registry_name
        self._data_folder = data_folder
        self._log_folder = log_folder
        self._registry = pykmhelpers.core.KmindexRegistry(self.registry_path)
        self._assets_folder = assets_folder
        self._script_out = script_out

    @property
    def index(self) -> pykmhelpers.core.KmindexRegistry:
        """KmindexRegistry: Registry of indexes managed by this builder."""
        return self._registry

    @property
    def path(self) -> str:
        """str: Canonical working directory of this builder."""
        return self._path

    @property
    def registry_name(self) -> str:
        """str: Filename of the kmindex registry, relative to `path`."""
        return self._registry_name

    @property
    def registry_path(self) -> str:
        """str: Absolute path to the kmindex registry."""
        return os.path.join(self.path, self.registry_name)

    @property
    def data_folder(self) -> str:
        """str: Absolute path to the sub-index data directory."""
        return os.path.join(self.path, self._data_folder)

    @property
    def log_folder(self) -> str:
        """str: Absolute path to the build log directory."""
        return os.path.join(self.path, self._log_folder)

    @property
    def assets_folder(self) -> str:
        """str: Absolute path to the generated assets directory."""
        return os.path.join(self.path, self._assets_folder)

    def load_metadata(self, file: str) -> dict:
        """Load sample metadata from a YAML file.

        Args:
            file (str): Path to the YAML metadata file containing a `samples` list.

        Returns:
            dict: Mapping of sample ID → sample metadata dict.
        """
        with open(file, "r") as f:
            tmp = yaml.safe_load(f)
            return {s["sample_id"]: s for s in tmp["samples"]}
        return None

    def has_subindex(self, name: str):
        """Check whether a sub-index is present in the registry.

        Args:
            name (str): Sub-index name to look up.

        Returns:
            bool: True if the registry contains a sub-index with this name.
        """
        return self.index.has_index(name)

    def add_sample_to_fof(
        self, sample, fof: pykmhelpers.pipeline.fof.FofManager
    ) -> None:
        """Add a single sample to a FofManager, logging failures instead of raising.

        Args:
            sample (dict): Sample dict with `sample_id` and `file_path` keys.
            fof (FofManager): File-of-files manager to add the sample to.
        """
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

    def create_fof(self, samples) -> pykmhelpers.pipeline.fof.FofManager:
        """Build a FofManager from a list of sample dicts.

        Args:
            samples (list): List of sample dicts, each with `sample_id` and `file_path` keys.

        Returns:
            FofManager: Populated file-of-files manager.
        """
        fof = pykmhelpers.pipeline.fof.FofManager()
        for s in samples:
            self.add_sample_to_fof(s, fof)
        return fof

    def get_bf_specs(
        self, n_samples: int, bloom_size: int, n_partitions: int
    ) -> pykmhelpers.core.BloomFilterSpecs:
        """Build the Bloom filter specs for a would-be index.

        Args:
            n_samples (int): Number of samples (Bloom filter columns).
            bloom_size (int): Bloom filter size, in rows (bits per sample).
            n_partitions (int): Number of partitions the Bloom filter matrix
                is split into.

        Returns:
            BloomFilterSpecs: Specs describing the resulting Bloom filter matrix.
        """
        return pykmhelpers.core.BloomFilterSpecs(
            n_cols=n_samples, n_rows=bloom_size, n_partitions=n_partitions
        )

    def get_storage_size(
        self,
        bf_specs: pykmhelpers.core.BloomFilterSpecs,
    ) -> pykmhelpers.core.byte.ByteCounter:
        """Compute the on-disk storage size implied by a set of Bloom filter specs.

        Args:
            bf_specs (BloomFilterSpecs): Bloom filter specs, e.g. from `get_bf_specs`.

        Returns:
            ByteCounter: Total storage size, auto-scaled to a human-readable unit.
        """
        return pykmhelpers.core.byte.ByteCounter.auto(
            bf_specs.total_storage_size(), pykmhelpers.core.byte.SizeFormat.BYTE
        )

    def create_subindex(
        self,
        name: str,
        samples: pykmhelpers.pipeline.fof.FofManager,
        bloom_size: int,
        kmer_size: int = 25,
        abundance_min: int = 2,
        n_partitions: int = 256,
        n_threads: int = 0,
        n_max_threads: int = 0,
        build_from: typing.Optional[str] = None,
        auto_check: bool = True,
        minim_size: int = 10,
        compress_intermediate: bool = True,
        dry_run: bool = False,
        on_existing: str = "fail",
        progress: typing.Optional[Progress] = None,
    ) -> dict:
        """Build a new sub-index from a set of samples via KmindexWrapper.build.

        Args:
            name (str): Name of the sub-index to create. Must not already
                exist in the registry.
            samples (FofManager): Samples to include, e.g. from `create_fof`.
                Must be non-empty.
            bloom_size (int): Bloom filter size, in rows (bits per sample).
                Must be greater than 0.
            kmer_size (int): K-mer size used by kmindex.
            abundance_min (int): Minimum k-mer abundance (hard min) to keep.
            n_partitions (int): Number of partitions to split the Bloom
                filter matrix into. `0` lets kmindex choose.
            n_threads (int): Number of threads to use. `0` uses all available
                CPUs (`os.cpu_count()`).
            n_max_threads (int): Upper bound on `n_threads` when it is
                auto-detected. `0` means no cap.
            build_from (typing.Optional[str]): Name of an existing index to
                reuse build parameters from. Ignored (with a warning) if it
                is not found in the registry and differs from `name`.
            auto_check (bool): After a successful, non-dry-run build, verify
                that the resulting index's partition count and k-mer size
                match what was requested, and check its on-disk structure.
            minim_size (int): Minimizer size passed to kmindex.
            compress_intermediate (bool): Compress intermediate build files.
            dry_run (bool): Skip filesystem checks and mutations, and invoke
                `KmindexWrapper` in dry-run mode; only log what would be done.
            on_existing (str): What to do if `output_indexdir` already exists
                on disk:
                - `"fail"`: raise `FileExistsError`.
                - `"rename"`: move it aside with a timestamp suffix and build.
                - `"replace"`: delete it and build.
                - `"register"`: try to register the existing directory as
                  `name` in the registry instead of building.
                - `"register_or_replace"`: try `"register"`, falling back to
                  `"replace"` if registration fails.
                - `"register_or_rename"`: try `"register"`, falling back to
                  `"rename"` if registration fails.
            progress (typing.Optional[Progress]): Optional progress tracker;
                if given (and not a dry run), polled in a background thread
                that estimates completion from partial matrix file sizes.

        Returns:
            dict: Result returned by `KmindexWrapper.build`, or
                `{"return_code": 0, "register": True}` if an existing
                directory was registered instead of built.
        """
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

        wrapper = pykmhelpers.core.KmindexWrapper(dry_run=dry_run)
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
                logger.debug(f"Reusing parameters from index: {build_from}")
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
                    r = self.index.add_index(
                        pykmhelpers.core.KmtricksIndex(output_basedir, name)
                    )
                except Exception as e:
                    logger.debug(f"Could not add index {name}: {e}")
                    r = False
                if not r:
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
                    return {"return_code": 0, "register": True}
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
                        m_path = pykmhelpers.core.kmindex_paths.get_matrix_path(
                            output_indexdir, p, False
                        )
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
            output_log_dir=None if dry_run else os.path.join(self.log_folder, name),
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
            if not self.index.has_index(name):
                logger.warning(f"Index '{name}' was not successfully created")
            else:
                idx = self.index.get_index(name)

                if auto_check:
                    if n_partitions > 0:
                        if idx.nb_partitions != n_partitions:
                            logger.warning(
                                f"Partition count mismatch: expected {n_partitions}, got {idx.nb_partitions}"
                            )

                    if idx.kmer_size != kmer_size:
                        logger.warning(
                            f"K-mer size mismatch: expected {kmer_size}, got {idx.kmer_size}"
                        )

                    self.check_index_structure(name)

        return result

    def merge(
        self,
        new_name: str,
        to_merge: list[str],
        rename: typing.Optional[str] = None,
        is_update: bool = True,
        delete_old: bool = True,
        threads: int = 14,
        dry_run: bool = False,
    ):
        """Merge sub-indexes into a single index via KmindexWrapper.merge.

        Args:
            new_name (str): Name of the resulting merged index.
            to_merge (list[str]): Names of sub-indexes (already present in the
                registry) to merge together.
            rename (typing.Optional[str]): How to rename sample identifiers to
                avoid collisions between merged sub-indexes. A sub-index cannot
                contain samples with duplicate identifiers, so sub-indexes
                sharing identifiers must be renamed before merging. Passed
                through to `kmindex merge -r/--rename`, which accepts:
                - identifier files, one per sub-index, comma separated
                  (e.g. `"f:id1.txt,id2.txt,id3.txt"`);
                - a format string with `{}` substituted by an integer in
                  `[0, nb_samples)` (e.g. `"s:id_{}"`).
                `None` leaves identifiers unchanged.
            is_update (bool): If `new_name` already exists in the registry,
                rename it to `{new_name}_old` and include it in the merge so
                the existing index is updated in place rather than replaced.
                Raises `ValueError` if `False` and `new_name` already exists.
            delete_old (bool): Delete the original sub-index files (including
                the renamed `{new_name}_old` index, if any) after a successful
                merge.
            threads (int): Number of threads to use for the merge.
            dry_run (bool): If `True`, skip registry validation and actually
                invoking kmindex; only log what would be done.

        Returns:
            dict: Result returned by `KmindexWrapper.merge`.
        """
        self.index.load_json()

        if not dry_run:
            missing = [name for name in to_merge if not self.index.has_index(name)]
            if missing:
                raise ValueError(f"Sub-indexes not found in registry: {missing}")

        old_name = None
        leftover_names = []

        if self.index.has_index(new_name):
            if not is_update:
                raise ValueError(
                    f"Index '{new_name}' already exists in registry; "
                    f"pass is_update=True to merge into it"
                )
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            old_name = f"{new_name}_{timestamp}"
            logger.info(
                f"Renaming existing index '{new_name}' to '{old_name}' (required for update)"
            )
            if not self.index.rename_index(new_name, old_name):
                raise RuntimeError(
                    f"Failed to rename existing index '{new_name}' to '{old_name}'"
                )
        elif is_update:
            # 'new_name' is already gone -- this can happen when this merge was
            # already renamed out of the way by an earlier pass over the same
            # input (e.g. the "plan" phase of `kmhelpers build`, which performs
            # this rename for real so the exported script has fixed names).
            # Pick up any leftover renamed copy instead of silently dropping it.
            pattern = re.compile(rf"^{re.escape(new_name)}_\d{{8}}_\d{{6}}$")
            leftover_names = [
                idx for idx in self.index.list_indices() if pattern.match(idx)
            ]
            if leftover_names:
                logger.info(f"Found backup version of '{new_name}': {leftover_names}")

        if is_update and old_name:
            to_merge.append(old_name)
        elif is_update and leftover_names:
            to_merge.extend(leftover_names)

        logger.info(f"Merging {to_merge} into '{new_name}'")

        wrapper = pykmhelpers.core.KmindexWrapper(dry_run=dry_run)
        try:
            result = wrapper.merge(
                input_registry=self.index.root_path,
                new_name=new_name,
                new_path=os.path.join(self.data_folder, new_name),
                to_merge=to_merge,
                rename=rename,
                delete_old=delete_old,
                threads=threads,
            )
        except Exception:
            if old_name and not dry_run:
                self.index.load_json()
                if self.index.has_index(old_name) and not self.index.has_index(
                    new_name
                ):
                    logger.info(
                        f"Merge failed, rolling back: renaming '{old_name}' to '{new_name}'"
                    )
                    if not self.index.rename_index(old_name, new_name):
                        logger.error(
                            f"Rollback failed: could not rename '{old_name}' back to '{new_name}'"
                        )
            raise

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
        """Check that an index's on-disk layout is well-formed.

        Args:
            name (str): Name of the index to check, as registered in the registry.

        Returns:
            The result of `KmtricksIndex.check_structure()` for this index.
        """
        idx = self.index.get_index(name)
        return idx.check_structure()

    def create_random_test_dataset(
        self, output_dir: str, n_samples: int = 5, average_size=1000, min_size=100
    ):
        """Create random FASTA files for testing.

        Args:
            output_dir (str): Directory where test FASTA files are written.
            n_samples (int): Number of random sequences to generate.
            average_size (int): Average sequence length in bp.
            min_size (int): Minimum sequence length in bp.
        """
        os.makedirs(output_dir, exist_ok=True)
        fasta = pykmhelpers.core.fasta.Fasta()
        fasta.fill_random(
            num_sequences=n_samples, average_size=average_size, min_size=min_size
        )
        for i, sequence in enumerate(fasta):
            output_file = os.path.join(output_dir, f"sequence_{i}.fasta")
            with open(output_file, "w") as f:
                f.write(sequence.to_fasta())

    def query_test_dataset(self, dataset: str, output_dir: str, z: int):
        """Query a directory of FASTA files against the index.

        Recursively searches `dataset` for FASTA files and queries each against
        the index, recreating the same directory structure under `output_dir`.

        Args:
            dataset (str): Path to directory containing FASTA files.
            output_dir (str): Directory where query results are written.
            z (int): Z-value (error rate parameter) passed to kmindex.
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
                            query = pykmhelpers.pipeline.query.KmindexQuery(
                                path=input_path
                            )
                            query.execute(
                                registry_path=self.index.root_path,
                                output_dir=output_dir,
                                z=z,
                            )
                        except Exception as e:
                            logger.error(f"Failed to query {input_path}: {str(e)}")

    def check_presence(self, results: str, samples: list[str]) -> bool:
        """Check that all samples have a 100% query score in results.

        Args:
            results (str): Path to query results directory.
            samples (list[str]): Sample names that must be fully present.

        Returns:
            bool: True if all samples score 1.0, False if any fall below that.
        """
        r = pykmhelpers.pipeline.query.KmindexQueryResult(results)
        ok = True
        for s in samples:
            v = r.max_score(s)
            if v < 1:
                logger.error(f"Sample score is not 100%: {s} = {v}")
                ok = False
        return ok

    def compare_results(self, results: str, ground_truth: str) -> bool:
        """Compare query results against a ground truth result set.

        Args:
            results (str): Path to query results directory.
            ground_truth (str): Path to ground truth results directory.

        Returns:
            bool: True if both result sets are equal.
        """
        return pykmhelpers.pipeline.query.KmindexQueryResult(
            results
        ) == pykmhelpers.pipeline.query.KmindexQueryResult(ground_truth)
