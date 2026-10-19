"""Wrapper around the kmtricks binary."""

import logging
import os
from pathlib import Path
from typing import Optional, Union

from pykmhelpers.core.resources import maximize_nofile
from pykmhelpers.core.utils import Toolbox
from pykmhelpers.core.wrapper import Wrapper

logger = logging.getLogger(__name__)


class KmtricksWrapper(Wrapper):
    """Runs ``kmtricks pipeline`` the way ``kmindex build`` does, without registering.

    ``kmindex build`` runs kmtricks then registers the run directory in a global
    index (kmindex ``app/kmindex/build.cpp:159-194, 274-278``). Building with
    kmtricks directly leaves the run unregistered: it can be registered later,
    in any registry, with ``kmindex register``.
    """

    def __init__(self, dry_run: bool = False):
        super().__init__("kmtricks", dry_run=dry_run)

    def pipeline(
        self,
        fof: Union[str, Path],
        run_dir: Union[str, Path],
        bloom_size: int,
        k: int = 25,
        minim_size: int = 10,
        hard_min: int = 2,
        bitw: Optional[int] = None,
        nb_partitions: int = 0,
        threads: int = 1,
        compress_intermediate: bool = False,
        static_repart: bool = True,
        repart_from: Optional[Union[str, Path]] = None,
        log_file: Optional[str] = None,
    ) -> dict:
        """Build a kmindex-compatible Bloom filter matrix in ``run_dir``.

        Same command as ``kmindex build``: ``--mode hash:bf:bin`` for
        presence/absence, ``--bitw N --mode hash:bfc:bin`` for abundance when
        ``bitw`` is set, ``bloom_size`` being then the number of cells.
        """
        if not (8 <= k <= 255):
            raise ValueError(f"K-mer size must be between 8 and 255, got {k}")

        cmd = [
            self.main_cmd,
            "pipeline",
            "--file",
            Toolbox.get_canonical_path(str(fof)),
            "--run-dir",
            Toolbox.get_canonical_path(str(run_dir)),
            "--kmer-size",
            str(k),
            "--hard-min",
            str(hard_min),
            "--bloom-size",
            str(bloom_size),
            "--minimizer-size",
            str(minim_size),
            "--nb-partitions",
            str(nb_partitions),
            "--threads",
            str(threads),
        ]
        if bitw:
            cmd += ["--bitw", str(bitw), "--mode", "hash:bfc:bin"]
        else:
            cmd += ["--mode", "hash:bf:bin"]
        if static_repart:
            cmd.append("--static-repart")
        if repart_from is not None:
            cmd += ["--repart-from", str(repart_from)]
        if compress_intermediate:
            cmd.append("--cpr")

        if not self.dry_run:
            # kmtricks creates the run directory but not its parents
            os.makedirs(
                os.path.dirname(Toolbox.get_canonical_path(str(run_dir))), exist_ok=True
            )

        maximize_nofile()
        result = self._monitor_cmd(cmd, log_file=log_file, log_errors_only=True)
        rc = (result or {}).get("return_code", 0 if self.dry_run else -1)
        if rc != 0:
            stderr = (result or {}).get("stderr") or (result or {}).get("error") or ""
            lines = [line.strip() for line in str(stderr).splitlines() if line.strip()]
            raise RuntimeError(
                f"kmtricks pipeline failed ({rc}): {lines[-1] if lines else '...'}"
            )
        return result or {}
