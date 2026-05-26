import argparse
from dataclasses import dataclass, asdict
from copy import deepcopy
import math
import json
import sys

@dataclass
class kmtricks_params:
    kmers: list[int] | None | int = None
    threads: int | None = None
    samples: int | None = None
    memory: int | float | None = None
    partitions: int | None = None
    files: int | None | dict = None
    focus: float = 0.5

    def __str__(self):
        c = self.copy()
        if isinstance(c.kmers, list):
            c.kmers = max(c.kmers)
        d = asdict(c)
        return json.dumps(d)

    def copy(self) -> "kmtricks_params":
        return deepcopy(self)

    def nb_open_files(self):
        assert(self.partitions is not None)
        assert(self.threads is not None)
        assert(self.samples is not None)

        nw = math.floor(self.threads * self.focus)
        if nw <= 0:
            nw = 1

        self.files = {
            "superk": (self.threads * self.partitions) + nw,
            "count": (self.threads * 2),
            "merge": (self.threads * self.samples) + self.threads
        }

    def max_memory(self):
        assert(self.kmers is not None)
        assert(self.partitions is not None)
        assert(self.threads is not None)
        byte_per_k = 8
        maxk = max(self.kmers) if isinstance(self.kmers, list) else self.kmers
        per_partition = maxk / self.partitions
        self.memory = round(((per_partition * byte_per_k) * 1.05) * self.threads, 2)

    def nb_partitions(self):
        assert(self.kmers is not None)
        assert(self.memory is not None)
        assert(self.threads is not None)
        byte_per_k = 8
        maxk = max(self.kmers) if isinstance(self.kmers, list) else self.kmers
        mem_per_thread = self.memory / self.threads
        kmers_per_partition = mem_per_thread / (byte_per_k * 1.05)
        self.partitions = math.ceil(maxk / kmers_per_partition)


    def nb_threads(self):
        assert(self.kmers is not None)
        assert(self.memory is not None)
        assert(self.partitions is not None)
        byte_per_k = 8
        maxk = max(self.kmers) if isinstance(self.kmers, list) else self.kmers
        per_partition_bytes = (maxk / self.partitions) * byte_per_k * 1.05
        self.threads = max(1, math.floor(self.memory / per_partition_bytes))

    def nb_threads_partitions(self):
        assert(self.samples is not None)
        assert(isinstance(self.files, int))

        max_files = self.files
        best_threads = 1
        best_partitions = 1

        max_threads = max_files

        for t in range(1, max_threads + 1):
            max_p = (max_files // t) - self.samples

            if max_p < 1:
                continue

            nw = math.floor(t * self.focus)
            if nw <= 0:
                nw = 1

            total_files = (t * max_p) + nw + (t * 2) + (t * self.samples) + t

            if total_files <= max_files:
                if t > best_threads:
                    best_threads = t
                    best_partitions = max_p

        self.threads = best_threads
        self.partitions = best_partitions

    def auto(self):
        if isinstance(self.files, int) and self.samples is not None:
            if self.threads is None or self.partitions is None:
                self.nb_threads_partitions()
        if (
            self.kmers is not None
            and self.memory is not None
            and self.threads is not None
            and self.partitions is None
        ):
            self.nb_partitions()

        if (
            self.kmers is not None
            and self.memory is not None
            and self.partitions is not None
            and self.threads is None
        ):
            self.nb_threads()

        if (
            self.kmers is not None
            and self.threads is not None
            and self.partitions is not None
            and self.memory is None
        ):
            self.max_memory()

        if (
            self.threads is not None
            and self.partitions is not None
            and self.samples is not None
        ):
            self.nb_open_files()

def parse_kmers(value: str):
    try:
        return int(value)
    except ValueError:
        pass

    kmers = []
    try:
        with open(value) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                kmers.append(int(line))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid integer found in kmers file: '{value}'"
        )

    if not kmers:
        raise argparse.ArgumentTypeError(
            f"Kmers file is empty: '{value}'"
        )

    return kmers

def build_parser():
    parser = argparse.ArgumentParser(
        prog="kmparams",
    )
    parser.add_argument("--kmers", type=parse_kmers, help="Max number of kmers")
    parser.add_argument("--threads", type=int, help="Number of threads")
    parser.add_argument("--samples", type=int, help="Number of samples")
    parser.add_argument("--memory", type=float, help="Memory available (bytes)")
    parser.add_argument("--partitions", type=int, help="Number of partitions")
    parser.add_argument("--files", type=int, help="Max open files (ulimit -n)")
    parser.add_argument("--focus", type=float, default=0.5, help="Focus ratio (default: 0.5)")
    parser.add_argument("--auto", action="store_true", help="Compute all fields that can be derived from the inputs (the default)")
    parser.add_argument("--compute-memory", action="store_true", help="Compute memory")
    parser.add_argument("--compute-partitions", action="store_true", help="Compute partitions")
    parser.add_argument("--compute-threads", action="store_true", help="Compute threads")
    parser.add_argument("--compute-files", action="store_true", help="Compute number of open files")
    parser.add_argument("--compute-partitions-threads", action="store_true", help="Fit threads & partitions from file limit")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    params = kmtricks_params(
        kmers=args.kmers,
        threads=args.threads,
        samples=args.samples,
        memory=args.memory,
        partitions=args.partitions,
        files=args.files,
        focus=args.focus,
    )

    print("input:", params)

    try:
        if args.auto or (not args.compute_memory
           and not args.compute_partitions
           and not args.compute_threads
           and not args.compute_partitions_threads
           and not args.compute_files):
            params.auto()
            print("result:", params)
            sys.exit(0)

        if args.compute_memory:
            params.max_memory()

        if args.compute_partitions:
            params.nb_partitions()

        if args.compute_threads:
            params.nb_threads()

        if args.compute_files:
            params.nb_open_files()

        if args.compute_partitions_threads:
            params.nb_threads_partitions()


        print("result:", params)

    except AssertionError as e:
        print("Error: missing required parameters", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()



