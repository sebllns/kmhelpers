"""Collect and render the state of a build directory against its compose definitions.

The map is a grid: one row per index name, one column per session. Each cell
tells whether that index was built in that session, whether it is the version
currently registered, or whether it was declared but never built.
"""

import glob
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml

from pykmhelpers.core.byte import ByteCounter
from pykmhelpers.core.kmindex_layout import load_fof_file, load_options_file
from pykmhelpers.core.kmindex_paths import (
    get_fof_path,
    get_json_path,
    get_matrix_dir,
    get_options_path,
)

BLOOM_DIR = "kmindex_data"
# Column used for registered indices whose data lives outside BLOOM_DIR
EXTERNAL_SESSION = "(external)"

ACTIVE = "active"
SUPERSEDED = "superseded"
MISSING = "missing"
ORPHAN = "orphan"
BROKEN = "broken"
STATUSES = [ACTIVE, SUPERSEDED, MISSING, ORPHAN, BROKEN]


@dataclass
class MapCell:
    name: str
    session: str
    status: str = ""
    built: bool = False
    active: bool = False
    declared: bool = False
    path: Optional[str] = None
    span: Optional[int] = None
    samples: Optional[int] = None
    kmer_size: Optional[int] = None
    partitions: Optional[int] = None
    size: Optional[int] = None
    compression: Optional[str] = None


@dataclass
class IndexMap:
    build_dir: str
    compose_dir: Optional[str] = None
    sessions: List[str] = field(default_factory=list)
    names: List[str] = field(default_factory=list)
    cells: Dict[Tuple[str, str], MapCell] = field(default_factory=dict)

    def cell(self, name: str, session: str) -> MapCell:
        key = (name, session)
        if key not in self.cells:
            self.cells[key] = MapCell(name, session)
        return self.cells[key]

    def to_dict(self) -> dict:
        return {
            "build_dir": self.build_dir,
            "compose_dir": self.compose_dir,
            "sessions": self.sessions,
            "names": self.names,
            "cells": [asdict(c) for c in self.cells.values()],
        }


def _scan_matrices(index_dir: str) -> Tuple[int, str]:
    """Return (matrix bytes on disk, compression flag C / U / C+U / -)."""
    size, has_c, has_u = 0, False, False
    matrix_dir = get_matrix_dir(index_dir)
    if not os.path.isdir(matrix_dir):
        return 0, "-"
    for entry in os.scandir(matrix_dir):
        if not entry.is_file():
            continue
        size += entry.stat().st_size
        if entry.name.startswith("blocks_"):
            has_c = True
        elif entry.name.endswith(".cmbf"):
            has_u = True
    flag = {(True, True): "C+U", (True, False): "C", (False, True): "U"}
    return size, flag.get((has_c, has_u), "-")


def _fill_from_dir(cell: MapCell, index_dir: str) -> None:
    cell.built = True
    cell.path = index_dir
    try:
        opts = load_options_file(get_options_path(index_dir))
        cell.kmer_size = opts.get("kmer_size")
        cell.partitions = opts.get("nb_partitions")
    except FileNotFoundError:
        pass
    try:
        cell.samples = len(load_fof_file(get_fof_path(index_dir)))
    except FileNotFoundError:
        pass
    cell.size, cell.compression = _scan_matrices(index_dir)


def collect_build(build_dir: str, index_map: IndexMap) -> Dict[str, float]:
    """Fill built and registered cells. Returns session -> mtime."""
    json_path = get_json_path(build_dir)
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"index.json not found in {build_dir}")
    with open(json_path) as f:
        registered = json.load(f).get("index", {})

    bloom_root = os.path.realpath(os.path.join(build_dir, BLOOM_DIR))
    mtimes: Dict[str, float] = {}

    # Every folder under kmindex_data/SESSION/ is a built index
    for index_dir in sorted(glob.glob(os.path.join(bloom_root, "*", "*"))):
        if not os.path.isdir(index_dir):
            continue
        session = os.path.basename(os.path.dirname(index_dir))
        name = os.path.basename(index_dir)
        _fill_from_dir(index_map.cell(name, session), os.path.realpath(index_dir))
        # options.txt is written at build time, unlike folder mtimes which move
        stamp = get_options_path(index_dir)
        mtime = os.path.getmtime(stamp if os.path.isfile(stamp) else index_dir)
        mtimes[session] = min(mtimes.get(session, mtime), mtime)

    # Registered names point (usually through a symlink) to the active version
    for name, props in registered.items():
        target = os.path.realpath(os.path.join(build_dir, name))
        if not os.path.isdir(target):
            cell = index_map.cell(name, EXTERNAL_SESSION)
            cell.active = True
            cell.status = BROKEN
            continue
        parent = os.path.dirname(target)
        if os.path.dirname(parent) == bloom_root:
            cell = index_map.cell(name, os.path.basename(parent))
        else:
            cell = index_map.cell(name, EXTERNAL_SESSION)
            _fill_from_dir(cell, target)
        cell.active = True
        cell.samples = props.get("nb_samples", cell.samples)
    return mtimes


def collect_compose(compose_dir: str, index_map: IndexMap) -> Dict[str, float]:
    """Fill declared cells from span registries COMPOSE_DIR/NAME/SESSION/*.yaml."""
    mtimes: Dict[str, float] = {}
    for path in sorted(glob.glob(os.path.join(compose_dir, "*", "*", "*.yaml"))):
        with open(path) as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict) or doc.get("type") != "span":
            continue
        session_dir = os.path.dirname(path)
        session = os.path.basename(session_dir)
        mtimes[session] = min(mtimes.get(session, float("inf")), os.path.getmtime(path))
        for span, entry in (doc.get("data") or {}).items():
            for name, subs in (entry.get("indices") or {}).items():
                cell = index_map.cell(name, session)
                cell.declared = True
                cell.span = int(span)
                if cell.built:
                    continue
                # Not built: estimate from the sub-index definitions
                samples = 0
                for sub in subs:
                    sub_path = os.path.join(session_dir, f"{sub}.yaml")
                    if not os.path.isfile(sub_path):
                        continue
                    with open(sub_path) as f:
                        sub_doc = (yaml.safe_load(f).get("data") or {}).get(sub, {})
                    samples += (sub_doc.get("infos") or {}).get("sample_count", 0)
                    k = (sub_doc.get("parameters") or {}).get("kmer_size")
                    if k is not None:
                        cell.kmer_size = int(k)
                cell.samples = samples
    return mtimes


def build_map(build_dir: str, compose_dir: Optional[str] = None) -> IndexMap:
    index_map = IndexMap(os.path.realpath(build_dir), compose_dir and os.path.realpath(compose_dir))
    build_mtimes = collect_build(build_dir, index_map)
    compose_mtimes = collect_compose(compose_dir, index_map) if compose_dir else {}

    # Spans are known per (name, session); propagate them to the whole row
    spans = {c.name: c.span for c in index_map.cells.values() if c.span is not None}
    for c in index_map.cells.values():
        c.span = spans.get(c.name)
        if c.status:
            continue
        if compose_dir and c.built and not c.declared:
            c.status = ORPHAN
        elif c.active:
            c.status = ACTIVE
        elif c.built:
            c.status = SUPERSEDED
        else:
            c.status = MISSING

    sessions = {c.session for c in index_map.cells.values()}
    mtimes = {**build_mtimes, **compose_mtimes}
    index_map.sessions = sorted(
        sessions, key=lambda s: (s == EXTERNAL_SESSION, mtimes.get(s, float("inf")), s)
    )
    index_map.names = sorted(
        {c.name for c in index_map.cells.values()},
        key=lambda n: (spans.get(n) is None, spans.get(n) or 0, n),
    )
    return index_map


def _cell_text(cell: Optional[MapCell]) -> str:
    if cell is None:
        return ""
    return f"{cell.status} ({cell.samples})" if cell.samples is not None else cell.status


def render_text(index_map: IndexMap) -> str:
    header = ["index", "span"] + index_map.sessions
    rows = []
    for name in index_map.names:
        cells = [index_map.cells.get((name, s)) for s in index_map.sessions]
        span = next((c.span for c in cells if c and c.span is not None), None)
        rows.append([name, "-" if span is None else str(span)] + [_cell_text(c) for c in cells])
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    lines = [f"Build dir:   {index_map.build_dir}"]
    if index_map.compose_dir:
        lines.append(f"Compose dir: {index_map.compose_dir}")
    lines.append("")
    for row in [header] + rows:
        lines.append("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip())
    lines.append("")
    lines.append("Cells: status (samples). Use --output for sizes, k and compression.")
    return "\n".join(lines)


# Status colors (fixed palette); the status label is always printed in the cell
STATUS_COLORS = {
    ACTIVE: "#0ca30c",
    SUPERSEDED: "#a3a29c",
    MISSING: "#fab219",
    ORPHAN: "#ec835a",
    BROKEN: "#d03b3b",
}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"


def render_figure(index_map: IndexMap, output_path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    n_cols, n_rows = len(index_map.sessions), len(index_map.names)
    cell_w, cell_h, label_w, header_h = 2.4, 1.0, 2.0, 0.4
    fig_w = label_w + n_cols * cell_w
    fig_h = header_h + n_rows * cell_h
    # Data units match inches so text and boxes keep their proportions
    fig = plt.figure(figsize=(fig_w, fig_h))
    ax = fig.add_axes((0, 0, 1, 1))
    fig.patch.set_facecolor(SURFACE)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(fig_h, 0)
    ax.axis("off")

    for j, session in enumerate(index_map.sessions):
        x = label_w + j * cell_w
        ax.text(x + cell_w / 2, header_h / 2, session, ha="center", va="center",
                fontsize=10, fontweight="bold", color=INK)

    for i, name in enumerate(index_map.names):
        y = header_h + i * cell_h
        cells = [index_map.cells.get((name, s)) for s in index_map.sessions]
        span = next((c.span for c in cells if c and c.span is not None), None)
        ax.text(0.1, y + cell_h * 0.4, name, va="center", fontsize=10, color=INK)
        if span is not None:
            ax.text(0.1, y + cell_h * 0.7, f"span {span}", va="center",
                    fontsize=8, color=INK_MUTED)
        for j, cell in enumerate(cells):
            if cell is None:
                continue
            x = label_w + j * cell_w
            pad = 0.06
            color = STATUS_COLORS[cell.status]
            ax.add_patch(Rectangle((x + pad, y + pad), cell_w - 2 * pad, cell_h - 2 * pad,
                                   facecolor=color, alpha=0.18, edgecolor="none"))
            ax.add_patch(Rectangle((x + pad, y + pad), 0.08, cell_h - 2 * pad,
                                   facecolor=color, edgecolor="none"))
            ax.text(x + 0.25, y + 0.3, cell.status, va="center", fontsize=9,
                    fontweight="bold", color=INK)
            details = []
            if cell.samples is not None:
                details.append(f"{cell.samples} samples")
            if cell.kmer_size is not None:
                details.append(f"k={cell.kmer_size}")
            ax.text(x + 0.25, y + 0.55, ", ".join(details), va="center",
                    fontsize=8, color=INK_MUTED)
            if cell.built:
                extra = []
                if cell.partitions is not None:
                    extra.append(f"{cell.partitions} parts")
                extra.append(str(ByteCounter.auto(cell.size or 0)))
                extra.append(cell.compression or "-")
                ax.text(x + 0.25, y + 0.78, ", ".join(extra), va="center",
                        fontsize=8, color=INK_MUTED)

    used = [s for s in STATUSES if any(c.status == s for c in index_map.cells.values())]
    ax.legend(
        handles=[Patch(facecolor=STATUS_COLORS[s], label=s) for s in used],
        loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=len(used),
        frameon=False, fontsize=9, labelcolor=INK,
    )
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
