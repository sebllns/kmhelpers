# kmtricks_params formulas

Notation:

- $K$ = `kmers` (max k-mer count, $K = \max(\text{kmers})$ when a list)
- $T$ = `threads`
- $S$ = `samples`
- $M$ = `memory` (bytes)
- $P$ = `partitions`
- $f$ = `focus` (default $0.5$)
- $b = 8$ = bytes per k-mer (`byte_per_k`)
- $\alpha = 1.05$ = memory safety margin

## focus

focus (default 0.5) is a ratio in nb_open_files and nb_threads_partitions used to estimate how many extra file descriptors the superk-counting stage needs beyond the per-thread × per-partition ones.

It's used to compute:
nw = max(1, floor(threads * focus))
nw is added to threads * partitions for the superk file count:
superk = threads * partitions + nw

So focus represents the fraction of threads that simultaneously hold an extra file open during the superk stage (on top of each thread's own partition file), on top of the threads * partitions files already open one-per-thread-per-partition. Raising focus increases the open-file budget kmtricks reserves for that stage; it doesn't affect nb_partitions, nb_threads, or max_memory, only file-count estimation.


Looking at the code, focus isn't derived from anything, it's a pure input you choose. It only feeds into the nw (extra concurrent file handles) term used for open-files accounting:

nw = max(1, floor(threads * focus))

You'd need to specify a non-default focus in two situations:

1. --compute-files (nb_open_files): to get an accurate superk file-count estimate for your actual kmtricks run, if you know the real ratio of "extra" concurrently-open files to total threads differs from the 50% default.
2. --compute-partitions-threads (nb_threads_partitions): when fitting threads/partitions to a hard ulimit -n, focus changes how many files are reserved for nw vs. left available for threads * partitions, so it directly shifts the resulting thread/partition split.

There's no docstring or comment in kmparams.py tying focus to a specific kmtricks internal (e.g., writer-thread ratio), so beyond "fraction of threads assumed to hold an extra open file during the superk stage," its precise physical meaning isn't documented in this file. If you know the actual kmtricks source for that ratio, that would confirm the exact interpretation.


## `max_memory` (computes $M$ from $K, T, P$)

$$
M = \operatorname{round}\left( \frac{K}{P} \cdot b \cdot \alpha \cdot T,\ 2 \right)
$$

## `nb_partitions` (computes $P$ from $K, M, T$)

$$
P = \left\lceil \frac{K}{\dfrac{M / T}{b \cdot \alpha}} \right\rceil
= \left\lceil \frac{K \cdot b \cdot \alpha \cdot T}{M} \right\rceil
$$

## `nb_threads` (computes $T$ from $K, M, P$)

$$
T = \max\left(1,\ \left\lfloor \frac{M}{\dfrac{K}{P} \cdot b \cdot \alpha} \right\rfloor \right)
$$

## `nb_open_files` (computes `files` dict from $T, P, S$)

$$
n_w = \max\left(1,\ \lfloor T \cdot f \rfloor \right)
$$

$$
\text{superk} = T \cdot P + n_w
$$

$$
\text{count} = 2T
$$

$$
\text{merge} = T \cdot S + T = T (S + 1)
$$

## `nb_threads_partitions` (fits $T, P$ from `files` limit $F$ and $S$)

For each candidate $t = 1, \dots, F$, with $n_w(t) = \max(1, \lfloor t \cdot f \rfloor)$:

- merge-stage constraint (binding, sequential stage):

$$
t (S + 1) \le F
$$

- superk-stage constraint on partitions given $t$:

$$
P_{\max}(t) = \left\lfloor \frac{F - n_w(t)}{t} \right\rfloor, \qquad P_{\max}(t) \ge 1
$$

The loop keeps the largest $t$ (and corresponding $P_{\max}(t)$) satisfying both constraints:

$$
T = \max\{\, t : t(S+1) \le F \ \text{and}\ P_{\max}(t) \ge 1 \,\}, \qquad P = P_{\max}(T)
$$

## Parameter selection procedure (`build_params.py`)

Additional notation:

- $R$ = `ram` (bytes)
- $F$ = `ulimit` (max open files)
- $N$ = `n_threads` (user thread cap)
- $S_{\text{total}}$ = total dataset sample count (`samples` arg to `get_best_params`)
- $\sigma$ = `safety_margin` (used only in `auto_params`, default $1.0$)

### `get_best_params`: maximize threads, then minimize partitions

**Original approach.** The chunk size used to be fixed unconditionally at the largest value
`ulimit` allows:

$$
S = \min(F - 1,\ S_{\text{total}})
$$

with no regard for $N$, which could leave threads unused whenever $\lfloor F/(S+1) \rfloor < N$.

**Why it changed.** Priority was flipped to maximize threads first: shrink the chunk just
enough to unlock $N$ threads when the largest chunk caps them below $N$, trading more chunks
for full requested parallelism. Unchanged when the largest chunk already supports $N$ threads.

1. Chunk size: as large as `ulimit` allows (fewest chunks), unless that size caps threads below
   $N$, in which case shrink it to the largest size that still fits $N$ threads in the merge
   stage:

$$
S = \max\!\left(1,\ \min\!\left(\left\lfloor \dfrac{F}{N} \right\rfloor - 1,\ S_{\text{total}}\right)\right)
$$

$\lfloor F/N \rfloor - 1$ is the largest $S$ satisfying $N(S+1) \le F$ (i.e. $S+1 \le F/N$, and
since $S+1$ is an integer, $S+1 \le \lfloor F/N \rfloor$): the merge-stage chunk size that fits
$N$ threads. Capping it at $S_{\text{total}}$ never asks for a chunk bigger than the whole
dataset; flooring at $1$ keeps a chunk non-empty.

This single expression is equivalent to a two-case split on $S_{\max} = \min(F - 1,\ S_{\text{total}})$
(largest chunk `ulimit` allows, vs. shrunk to fit $N$ threads) for any $F \ge 2$: whenever
$S_{\max}$ is capped by $F - 1$ rather than $S_{\text{total}}$, the fitted-$N$ term
$\lfloor F/N \rfloor - 1$ never falls below it either, so the `min` with $S_{\text{total}}$ still
picks the right value. It only diverges from the two-case form at the degenerate $F = 1$ corner
(1 open file total), which has no practical meaning for kmtricks. This only relaxes the
merge-stage thread ceiling below; it never affects the superk-stage infeasibility case, since
superk ($T \cdot P + n_w$) doesn't depend on $S$.

2. Hard thread ceiling, from the user cap and the merge-stage file limit ($T(S+1) \le F$):

$$
T_{\max} = \min\left(N,\ \left\lfloor \frac{F}{S+1} \right\rfloor \right)
$$

If $T_{\max} < 1$, no configuration fits `ulimit` (raises `ValueError`). Given the $S$ selection
above, this now only happens when $N < 1$.

3. Walk $t$ down from $T_{\max}$ to $1$. For each $t$, take the RAM-minimum partitions via `nb_partitions`:

$$
P(t) = \left\lceil \frac{K \cdot b \cdot \alpha \cdot t}{R} \right\rceil
$$

then compute `nb_open_files` with $(t, P(t), S, f)$ and accept the first (largest) $t$ for which:

$$
\max\big(\text{superk}(t),\ \text{count}(t),\ \text{merge}(t)\big) \le F
$$

The result is $T^ = t$, $P^ = P(t)$. Since `nb_partitions` already returns the RAM floor for a given thread count, the largest feasible $t$ paired with its minimum $P(t)$ is simultaneously the most-parallel and most file-frugal choice, so "maximize threads, then minimize partitions" has no conflicting trade-off. If no $t \in [1, T_{\max}]$ is feasible, raises `ValueError`.

The returned `params.samples` is the **per-chunk** count $S$, not $S_{\text{total}}$: when $S_{\text{total}} > S$, the caller runs $\lceil S_{\text{total}} / S \rceil$ sub-builds and merges them.

### `auto_params`: resolve system limits, then delegate and sanity-check

1. Parse the `limits` JSON for optional `ram`, `files`, `threads`, `focus`.
2. Any missing key falls back to a detected system limit scaled by $\sigma$: `get_available_ram`, `get_max_open_files`, `get_available_threads` (`pykmhelpers/core/resources.py`). `focus` falls back to $0.5$ if absent (not scaled by $\sigma$).
3. Call `get_best_params(K, R, S_{\text{total}}, F, N, f)` as above.
4. Re-check the returned params against the resolved $R$, $F$, $N$ and raise `ValueError` if any is exceeded, as a guard against a logic error in `get_best_params` rather than an expected outcome.


