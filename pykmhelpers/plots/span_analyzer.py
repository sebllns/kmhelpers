import csv
import itertools
import math
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from pykmhelpers.core.bloom_filter import BloomFilterSpecs
from pykmhelpers.core.byte import ByteCounter, SizeFormat


class SpanAnalyzer:
    def __init__(self, path):
        self.path = path
        data = self._load_csv(path)
        self.spans = [d[0] for d in data]
        self.bf = {d[0]: d[1] for d in data}
        self.nc = {d[0]: d[2] for d in data}
        self.lk = {s: self._pack8(self.nc[s]) for s in self.spans}
        non_empty = [s for s in self.spans if self.nc[s] > 0]
        self.adj_pairs = [
            (non_empty[i], non_empty[i + 1]) for i in range(len(non_empty) - 1)
        ]
        self.sizes = {
            d[0]: BloomFilterSpecs(d[1], d[2], 256).total_storage_size() for d in data
        }

    @staticmethod
    def _load_csv(path):
        data = []
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=",")
            for row in reader:
                span = int(row["span"].strip())
                bf = int(row["bf_size"].strip().replace(",", ""))
                nc = int(row["sample_count"].strip().replace(",", ""))
                data.append((span, bf, nc))
        return data

    @staticmethod
    def _pack8(n):
        return math.ceil(max(n, 0) / 8) * 8

    def get_total_stored_size(self):
        return sum(self.sizes.values())

    def get_total_stored_size_str(self):
        return str(ByteCounter.auto(self.get_total_stored_size(), SizeFormat.BYTE))

    def waste_pct(self, s):
        l = self.lk[s]
        if l == 0:
            return None
        return (l - self.nc[s]) / l * 100

    def delta_cumulative(self, j):
        m = self.spans[j]
        Nm = self.nc[m]
        Lm = self.lk[m]
        sources = [self.spans[k] for k in range(j) if self.nc[self.spans[k]] > 0]
        if not sources:
            return None
        sum_Nk = sum(self.nc[k] for k in sources)
        sum_LkBk = sum(self.bf[k] * self.lk[k] for k in sources)
        d_plus = self.bf[m] * (self._pack8(Nm + sum_Nk) - Lm)
        d_minus = sum_LkBk
        return (d_plus - d_minus) / 8e9

    def delta_adjacent(self, k, m):
        Nm = self.nc[m]
        Lm = self.lk[m]
        Nk = self.nc[k]
        d_plus = self.bf[m] * (self._pack8(Nm + Nk) - Lm)
        d_minus = self.bf[k] * self.lk[k]
        return (d_plus - d_minus) / 8e9

    def compute_groups(self, n_groups):
        """Find optimal boundaries to partition spans into n_groups storage-balanced groups.

        Uses self.sizes (actual bloom filter storage per span) as the cost to balance.
        Returns (boundaries, group_spans, costs) where:
            boundaries  — tuple of span values used as upper limits between groups
            group_spans — list of lists, each containing the spans in that group
            costs       — list of total storage cost (bytes) per group
        """
        spans = self.spans

        def split(boundaries):
            limits = [-math.inf] + list(boundaries) + [math.inf]
            groups = []
            for i in range(len(limits) - 1):
                lo, hi = limits[i], limits[i + 1]
                groups.append([s for s in spans if lo < s <= hi])
            return groups

        best, best_score = None, float("inf")
        for boundaries in itertools.combinations(spans[:-1], n_groups - 1):
            groups = split(boundaries)
            costs = [sum(self.sizes[s] for s in g) for g in groups]
            total = sum(costs)
            if total == 0:
                continue
            target = total / n_groups
            score = max(abs(c - target) for c in costs)
            if score < best_score:
                best_score = score
                best = boundaries

        group_spans = split(best)
        costs = [sum(self.sizes[s] for s in g) for g in group_spans]
        return best, group_spans, costs

    def _plot_groups(self, ax, boundaries, group_spans, costs):
        COLORS = [plt.colormaps["tab10"](i) for i in range(10)]
        spans = self.spans
        x = list(range(len(spans)))

        def group_idx(s):
            for i, bnd in enumerate(boundaries):
                if s <= bnd:
                    return i
            return len(boundaries)

        colors = [COLORS[group_idx(s) % len(COLORS)] for s in spans]
        nc_vals = [self.nc[s] for s in spans]

        self._style_ax(ax)
        ax.bar(x, nc_vals, color=colors, width=0.6, zorder=2)
        ax.set_xticks(x)
        ax.set_xticklabels(spans, rotation=45, ha="right", fontsize=8, color="#8a9bb5")
        ax.set_title("Group partitioning", color="#c9cdd8")

        for bnd in boundaries:
            if bnd in spans:
                xi = spans.index(bnd)
                ax.axvline(x=xi + 0.5, color="white", linestyle="--", linewidth=1.0)

        total_cost = sum(costs)
        legend_handles = [
            Patch(
                facecolor=COLORS[i % len(COLORS)],
                label=f"G{i+1}: {len(g)} spans  {costs[i]/2**30:.2f} GB ({100*costs[i]/total_cost:.1f}%)",
            )
            for i, g in enumerate(group_spans)
        ]
        ax.legend(
            handles=legend_handles,
            facecolor="#1a1d27",
            edgecolor="#2a2d3a",
            labelcolor="#c9cdd8",
            fontsize=8,
        )

    def _style_ax(self, ax):
        ax.set_facecolor("#0f1117")
        ax.tick_params(colors="#5a5f72")
        for spine in ax.spines.values():
            spine.set_edgecolor("#2a2d3a")
        ax.grid(True, color="#1e2130", linewidth=0.8, axis="y")

    def plot(self, n_groups=None):
        spans = self.spans
        adj_costs = [(k, m, self.delta_adjacent(k, m)) for k, m in self.adj_pairs]
        cum_points = [
            (spans[j], self.delta_cumulative(j)) for j in range(1, len(spans))
        ]
        cum_points = [(s, d) for s, d in cum_points if d is not None]

        boundaries, group_spans, group_costs = None, None, None
        if n_groups is not None and n_groups > 1:
            boundaries, group_spans, group_costs = self.compute_groups(n_groups)

        fig, axes = plt.subplots(2, 2, figsize=(18, 12))
        fig.patch.set_facecolor("#0f1117")
        axes = axes.flatten()

        # plot 1: sample_count bars + waste% on twin axis
        ax = axes[0]
        self._style_ax(ax)
        x = list(range(len(spans)))
        nc_vals = [self.nc[s] for s in spans]
        # wp_vals = [self.waste_pct(s) for s in spans]

        ax.bar(x, nc_vals, color="#4a9eff", width=0.6, label="sample_count", zorder=2)
        ax.set_xticks(x)
        ax.set_xticklabels(spans, rotation=45, ha="right", fontsize=8, color="#8a9bb5")
        # ax.set_ylabel("sample_count", color="#4a9eff")
        # ax.set_title("Sample count & pack-of-8 waste per span", color="#c9cdd8")
        ax.set_title("Sample distribution", color="#c9cdd8")

        # ax2 = ax.twinx()
        # ax2.set_facecolor("#0f1117")
        # ax2.tick_params(colors="#5a5f72")
        # wp_x = [xi for xi, w in zip(x, wp_vals) if w is not None]
        # wp_y = [w for w in wp_vals if w is not None]
        # ax2.plot(
        #     wp_x,
        #     wp_y,
        #     color="#ff9f43",
        #     linewidth=1.5,
        #     marker="o",
        #     markersize=4,
        #     zorder=3,
        #     label="waste % (L_k-N_k)/L_k",
        # )
        # ax2.set_ylabel("Waste %", color="#ff9f43")
        # ax2.tick_params(axis="y", colors="#ff9f43")
        # ax2.set_ylim(0, 110)

        lines1, labs1 = ax.get_legend_handles_labels()
        # lines2, labs2 = ax2.get_legend_handles_labels()
        ax.legend(
            lines1,  # lines1 + lines2,
            labs1,  # labs1 + labs2,
            facecolor="#1a1d27",
            edgecolor="#2a2d3a",
            labelcolor="#c9cdd8",
            fontsize=9,
        )

        # plot 2: cumulative fusion cost as x-y line
        ax = axes[1]
        self._style_ax(ax)
        ax.grid(True, color="#1e2130", linewidth=0.8)

        cx = [c[0] for c in cum_points]
        cy = [c[1] for c in cum_points]
        seg_colors = ["#2ecc71" if v < 0 else "#4a9eff" for v in cy]

        for i in range(1, len(cx)):
            col = "#2ecc71" if cy[i] < 0 else "#4a9eff"
            ax.plot(
                cx[i - 1 : i + 1], cy[i - 1 : i + 1], color=col, linewidth=2, zorder=2
            )
        ax.scatter(cx, cy, color=seg_colors, s=40, zorder=3)
        ax.axhline(0, color="#5a5f72", linewidth=0.8, linestyle=":")
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_xlabel("Target span m", color="#8a9bb5")
        ax.set_ylabel("Delta (GB)", color="#8a9bb5")
        ax.set_title("Cumulative fusion cost: all previous spans → m", color="#c9cdd8")
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
        ax.legend(
            handles=[
                Line2D([0], [0], color="#2ecc71", lw=2, label="Gain"),
                Line2D([0], [0], color="#4a9eff", lw=2, label="Loss"),
            ],
            facecolor="#1a1d27",
            edgecolor="#2a2d3a",
            labelcolor="#c9cdd8",
            fontsize=9,
        )

        # plot 3: adjacent fusion cost bar
        ax = axes[2]
        self._style_ax(ax)
        ax_x = list(range(len(adj_costs)))
        ax_y = [c[2] for c in adj_costs]
        ax_lbl = [f"{c[0]}→{c[1]}" for c in adj_costs]
        colors3 = ["#2ecc71" if v < 0 else "#4a9eff" for v in ax_y]
        ax.bar(ax_x, ax_y, color=colors3, width=0.6, zorder=2)
        ax.axhline(0, color="#5a5f72", linewidth=0.8, linestyle=":")

        ref = max(abs(v) for v in ax_y) * 0.02
        for xi, yi in zip(ax_x, ax_y):
            va = "bottom" if yi >= 0 else "top"
            off = ref if yi >= 0 else -ref
            ax.annotate(
                f"{yi:.1f}",
                xy=(xi, yi),
                xytext=(xi, yi + off),
                ha="center",
                va=va,
                fontsize=6.5,
                color="#c9cdd8",
                family="monospace",
            )

        ax.set_xticks(ax_x)
        ax.set_xticklabels(
            ax_lbl,
            rotation=45,
            ha="right",
            fontsize=7.5,
            color="#8a9bb5",
            family="monospace",
        )
        ax.set_ylabel("Delta (GB)", color="#8a9bb5")
        ax.set_title("Adjacent merge cost: k → next non-empty span", color="#c9cdd8")
        ax.legend(
            handles=[
                Patch(facecolor="#2ecc71", label="Gain"),
                Patch(facecolor="#4a9eff", label="Loss"),
            ],
            facecolor="#1a1d27",
            edgecolor="#2a2d3a",
            labelcolor="#c9cdd8",
            fontsize=9,
        )

        ax = axes[3]
        if boundaries is not None and group_spans is not None and group_costs is not None:
            self._plot_groups(ax, boundaries, group_spans, group_costs)
        else:
            ax.set_visible(False)

        fig.suptitle(
            f"Span analysis (total size ≈ {self.get_total_stored_size_str()})",
            color="#e0e4f0",
            fontsize=13,
        )
        plt.tight_layout()
        out = self.path.replace(".csv", "_analysis.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "spans.csv"
    n_groups = int(sys.argv[2]) if len(sys.argv) > 2 else None
    SpanAnalyzer(path).plot(n_groups=n_groups)
