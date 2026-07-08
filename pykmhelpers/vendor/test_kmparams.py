"""Explanation of and examples for ``kmparams.py``.

WHAT kmparams.py DOES
=====================
It is a small solver for kmtricks run parameters. kmtricks performance
depends on four interlocking knobs -- ``threads``, ``partitions``,
``memory`` and the open-file count -- driven by the dataset size
(``kmers``, ``samples``). This module lets you specify the ones you know
and computes the rest.

The core is the ``kmtricks_params`` dataclass. Its fields:

    kmers       max number of distinct k-mers (int, or a list -> max is used)
    threads     worker threads
    samples     number of input samples
    memory      bytes of RAM available
    partitions  how many partitions to split k-mers into
    files       EITHER the max open-file limit (int, an input)
                OR a computed per-stage breakdown (dict, an output)
    focus       ratio (0.5) tuning the superk writer count

THE MODEL BEHIND THE MATH
-------------------------
Everything rests on one assumption: each k-mer costs ~8 bytes plus a 5%
overhead, and each thread holds one partition-sized slice of k-mers in
memory at a time. So the central relationship is:

    memory ~= (max_kmers / partitions) * 8 * 1.05 * threads

Each solver method rearranges that equation to isolate one unknown:

    nb_partitions()   given kmers, memory, threads -> solve partitions
    nb_threads()      given kmers, memory, partitions -> solve threads
    max_memory()      given kmers, threads, partitions -> memory needed
    nb_open_files()   given threads, partitions, samples -> dict of file
                      descriptors per pipeline stage (superk/count/merge)
    nb_threads_partitions()
                      inverse: given an open-file LIMIT and samples, search
                      for the largest threads/partitions staying under it.
                      The merge stage (t*(samples+1)) binds threads; the
                      superk stage bounds partitions.

auto() -- THE DISPATCHER
------------------------
auto() is the intended entry point. It inspects which fields are set and
fires whichever solver applies, in order:

    1. files is int + samples set, threads/partitions unset
           -> fit threads & partitions from the file limit
    2. kmers+memory+threads set, partitions unset  -> compute partitions
    3. kmers+memory+partitions set, threads unset  -> compute threads
    4. kmers+threads+partitions set, memory unset  -> compute memory needed
    5. threads+partitions+samples all set          -> compute files dict

Pattern: leave the unknowns as None, call auto(), read the result. Step 5
runs after the earlier steps, so once threads/partitions are known the
file breakdown gets filled in too.

CAVEATS
-------
* nb_open_files() / --compute-files require threads & partitions to already
  be set, otherwise they hit the asserts (the CLI exits with "missing
  required parameters").
* Passing ``files`` as an int input and then running auto() replaces that
  int with the computed dict once threads/partitions are known.
"""

import kmparams


def deduce_max(kmers, ram, samples, ulimit, threads=None, focus=0.5):
    """Deduce the maximum feasible kmtricks configuration.

    Given the dataset (``kmers``, ``samples``) and the resource ceilings
    (``ram``, ``ulimit``, and optionally a CPU ``threads`` cap), return the
    ``kmtricks_params`` with the LARGEST thread count that satisfies both:

      * RAM        -> partitions >= ceil(kmers * 8 * 1.05 * threads / ram)
      * open files -> every stage (esp. merge = threads*(samples+1)) <= ulimit

    partitions is set to the RAM-required minimum for the chosen thread count,
    and the per-stage ``files`` dict is filled in. Raises ValueError if not
    even one thread fits under ``ulimit`` (i.e. samples+1 > ulimit).
    """
    # merge stage caps threads regardless of anything else
    max_t = ulimit // (samples + 1)
    if threads is not None:
        max_t = min(max_t, threads)
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs {samples + 1} "
            f"open files for a single thread"
        )

    # search downward for the largest thread count whose RAM-required
    # partitions still keep the superk stage under the file limit
    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers, memory=ram, threads=t, samples=samples, focus=focus
        )
        p.nb_partitions()  # partitions <- RAM
        p.nb_open_files()  # files      <- computed dict
        if max(p.files.values()) <= ulimit:
            return p

    raise ValueError("no feasible configuration under the given ulimit")


def deduce_optimal(kmers, ram, samples, ulimit, n_threads, focus=0.5):
    """Maximize threads (up to n_threads), then minimize partitions.

    The ideal kmtricks configuration for fixed hardware: use as many threads
    as possible without exceeding ``n_threads`` OR the resource ceilings, and
    for that thread count take the fewest partitions.

    The objective is lexicographic but conflict-free:
      * threads is capped by n_threads, by RAM (via the partitions needed),
        and by ulimit (merge stage = threads*(samples+1), superk stage =
        threads*partitions + writers).
      * for the chosen thread count, ``nb_partitions()`` returns the RAM
        MINIMUM, which is also the best case for the superk file count.

    So this returns the largest feasible thread count with its minimum
    partitions. Raises ValueError if not even one thread fits ``ulimit``.
    """
    # hard ceiling on threads: user cap and the merge-stage file limit
    max_t = min(n_threads, ulimit // (samples + 1))
    if max_t < 1:
        raise ValueError(
            f"ulimit {ulimit} too low: merge stage needs {samples + 1} "
            f"open files for a single thread"
        )

    # walk down from the ceiling; first feasible t is the maximum, and its
    # RAM-minimum partitions is the minimum partition count for that t
    for t in range(max_t, 0, -1):
        p = kmparams.kmtricks_params(
            kmers=kmers, memory=ram, threads=t, samples=samples, focus=focus
        )
        p.nb_partitions()  # minimum partitions for t threads (RAM floor)
        p.nb_open_files()
        if max(p.files.values()) <= ulimit:
            return p

    raise ValueError("no feasible configuration under the given ulimit")


def deduce_min_partitions(kmers, ram, samples, ulimit, threads=None, focus=0.5):
    """Deduce the configuration with the FEWEST partitions.

    Under a fixed RAM budget, partitions scale WITH threads
    (partitions = ceil(kmers * 8 * 1.05 * threads / ram)), so partitions is
    minimized by minimizing threads. The absolute minimum is at threads=1.

    This is the opposite objective from ``deduce_max``: fewer partitions means
    less parallelism. Pass ``threads`` to pin a thread count (partitions is
    then the forced RAM minimum for it); omit it to get the global minimum
    (threads=1). Raises ValueError if the choice does not fit ``ulimit``.
    """
    t = 1 if threads is None else threads

    # merge stage: threads*(samples+1) must fit under ulimit
    if t * (samples + 1) > ulimit:
        raise ValueError(
            f"threads={t} needs {t * (samples + 1)} open files > ulimit {ulimit}"
        )

    p = kmparams.kmtricks_params(
        kmers=kmers, memory=ram, threads=t, samples=samples, focus=focus
    )
    p.nb_partitions()  # partitions <- RAM (the minimum for this thread count)
    p.nb_open_files()
    if max(p.files.values()) > ulimit:
        raise ValueError(
            f"threads={t} needs {max(p.files.values())} open files > ulimit {ulimit}"
        )
    return p


def show(title, p):
    print(f"\n# {title}")
    print(p)


# --- Original test case -----------------------------------------------------
# kmers + memory + partitions known, threads unknown. auto() skips the
# threads/partitions fit (partitions is already set), computes threads from
# the central equation, then fills in the files dict. Note the input int
# `files` gets OVERWRITTEN by the computed dict.
p = kmparams.kmtricks_params(
    kmers=2_147_483_647,  # ~137 billion k-mers
    memory=33_050_427_392,  # ~33 GB
    files=1_073_741_816,  # int -> treated as a file limit (overwritten)
    partitions=256,
    samples=7397,
)
p.auto()
show("original test case (solves threads, then files dict)", p)


# --- Example 1: X kmers and Y RAM -> partitions per thread run -------------
p = kmparams.kmtricks_params(
    kmers=2_147_483_647,
    memory=33_050_427_392,
    threads=16,
)
p.auto()  # fills partitions, then the files dict
show("example 1: solve partitions", p)


# --- Example 2: how many threads can this box drive? (memory-bound) --------
p = kmparams.kmtricks_params(
    kmers=2_147_483_647,
    memory=33_050_427_392,
    partitions=256,
    samples=7397,
)
p.auto()  # computes threads, then files dict
show("example 2: solve threads", p)
print("threads =", p.threads)


# --- Example 3: pin threads & partitions -> how much RAM is needed? --------
p = kmparams.kmtricks_params(kmers=2_147_483_647, threads=32, partitions=512)
p.max_memory()
show("example 3: solve memory", p)
print("memory (bytes) =", p.memory)


# --- Example 4: ulimit -n is 1024 -> biggest safe threads/partitions -------
# The merge stage t*(samples+1) is the limiter here.
p = kmparams.kmtricks_params(files=1024, samples=100)
p.nb_threads_partitions()
show("example 4: fit threads & partitions from file limit", p)
print("threads =", p.threads, "partitions =", p.partitions)


# --- Example 5: file descriptors per pipeline stage ------------------------
p = kmparams.kmtricks_params(threads=8, partitions=256, samples=7397, focus=0.5)
p.nb_open_files()
show("example 5: per-stage open files", p)
print("files =", p.files)  # {'superk': ..., 'count': ..., 'merge': ...}


# --- Example 6: deduce the maximum feasible configuration ------------------
# Given the dataset + resource ceilings, deduce_max() returns the most
# threads that fit under BOTH RAM and ulimit, with partitions filled in.
best = deduce_max(
    kmers=2_147_483_647,
    ram=33_050_427_392,
    samples=7397,
    ulimit=131_072,  # theoretical high ulimit
    threads=64,  # CPU cap
)
show("example 6: maximum feasible configuration", best)
print(
    "=> threads=%d partitions=%d peak_open_files=%d"
    % (best.threads, best.partitions, max(best.files.values()))
)


# --- Example 7: minimize partitions ---------------------------------------
# Fewest partitions = fewest threads. Omit `threads` for the global minimum
# (threads=1); pass `threads` to pin parallelism and accept the resulting
# (forced) partition count.
fewest = deduce_min_partitions(
    kmers=2_147_483_647,
    ram=33_050_427_392,
    samples=7397,
    ulimit=131_072,
)
show("example 7: minimum partitions (threads=1)", fewest)
print(
    "=> threads=%d partitions=%d peak_open_files=%d"
    % (fewest.threads, fewest.partitions, max(fewest.files.values()))
)


# --- Example 8: the ideal config -- max threads (<=N), min partitions ------
N_THREADS = 32
opt = deduce_optimal(
    kmers=2_147_483_647,
    ram=33_050_427_392,
    samples=7397,
    ulimit=131_072,
    n_threads=N_THREADS,
)
show(f"example 8: optimal (threads<={N_THREADS}, min partitions)", opt)
print(
    "=> threads=%d partitions=%d peak_open_files=%d"
    % (opt.threads, opt.partitions, max(opt.files.values()))
)
