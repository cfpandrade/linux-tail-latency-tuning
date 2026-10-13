"""Generate planning (illustrative) figures for the dissertation.

These are planning illustrations, not empirical results. They orient the
reader and will be replaced or supplemented once experimental data exist.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

FIG = os.environ.get("FIGURES_DIR", "figures")
os.makedirs(FIG, exist_ok=True)


def _box(ax, x, y, w, h, text, fc="#eef3fb"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02",
                                linewidth=1.2, edgecolor="#2b4a7a", facecolor=fc))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)


def topology():
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")
    _box(ax, 0.5, 2.5, 3, 1.4, "Producer EC2\n(ENA + PHC)")
    _box(ax, 6.5, 2.5, 3, 1.4, "Consumer EC2\n(ENA + PHC)")
    _box(ax, 3.5, 0.3, 3, 1.1, "Amazon Time Sync\n(GPS-disciplined)", fc="#f6eef9")
    ax.annotate("", xy=(6.5, 3.2), xytext=(3.5, 3.2),
                arrowprops=dict(arrowstyle="-|>", lw=1.6, color="#2b4a7a"))
    ax.text(5, 3.45, "data plane", ha="center", fontsize=8)
    for sx in (2.0, 8.0):
        ax.annotate("", xy=(sx, 2.5), xytext=(5.0, 1.4),
                    arrowprops=dict(arrowstyle="-|>", lw=1.2, ls="--", color="#7a4a8a"))
    ax.text(5.0, 1.95, "PTP sync", ha="center", fontsize=8, color="#7a4a8a")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "topology.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def cpu_layout():
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")
    _box(ax, 0.3, 0.3, 4.6, 4.3, "", fc="#f3f7fc")
    _box(ax, 5.1, 0.3, 4.6, 4.3, "", fc="#f3f7fc")
    ax.text(2.6, 4.35, "NUMA Node 0  (cores 0-7)", ha="center", fontsize=9, weight="bold")
    ax.text(7.4, 4.35, "NUMA Node 1  (cores 8-15)", ha="center", fontsize=9, weight="bold")
    _box(ax, 0.6, 3.0, 4.0, 1.0, "NIC IRQs -> cores 2-3", fc="#eef3fb")
    _box(ax, 0.6, 1.8, 4.0, 1.0, "Producer -> cores 2-3", fc="#eef3fb")
    _box(ax, 0.6, 0.6, 4.0, 1.0, "Strategy thread -> cores 4-7 (FIFO)", fc="#e7f2ea")
    _box(ax, 5.4, 3.0, 4.0, 1.0, "Housekeeping -> cores 8-9", fc="#f9f1e9")
    _box(ax, 5.4, 0.6, 4.0, 1.9, "Background\n(isolcpus excluded)", fc="#f9f1e9")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "cpu_layout.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def latency_cdf():
    fig, ax = plt.subplots(figsize=(6, 3.6))
    x = np.linspace(0, 700, 600)
    def cdf(med, tail):
        z = (np.log(x + 1) - np.log(med)) / tail
        return 1 / (1 + np.exp(-z))
    ax.plot(x, cdf(40, 0.9), label="Baseline (S0)", lw=2)
    ax.plot(x, cdf(12, 0.55), label="Full Opt. (S5)", lw=2)
    ax.set_xlabel("Latency (us)"); ax.set_ylabel("CDF")
    ax.set_ylim(0, 1); ax.set_xlim(0, 700)
    ax.legend(loc="lower right"); ax.grid(alpha=0.3)
    ax.set_title("Anticipated tick-to-trade latency CDF (illustrative)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "latency_cdf_illustrative.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def tail_progression():
    fig, ax = plt.subplots(figsize=(6, 3.6))
    scen = ["S0", "S1", "S2", "S3", "S4", "S5"]
    p99 = [300, 240, 150, 120, 80, 45]
    p999 = [600, 500, 320, 250, 150, 70]
    xi = np.arange(len(scen))
    ax.plot(xi, p99, "o-", label="p99", lw=2)
    ax.plot(xi, p999, "s-", label="p99.9", lw=2)
    ax.set_xticks(xi); ax.set_xticklabels(scen)
    ax.set_ylabel("Latency (us)"); ax.legend(); ax.grid(alpha=0.3)
    ax.set_title("Anticipated tail-latency progression (illustrative)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "tail_progression_illustrative.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    topology()
    cpu_layout()
    latency_cdf()
    tail_progression()
    print("Wrote 4 figures to", FIG)
    print(sorted(os.listdir(FIG)))
