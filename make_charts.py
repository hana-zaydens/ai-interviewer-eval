"""
Generates two stacked bar chart SVGs for the white paper:
  chart_biasing_response.svg
  chart_probe_depth.svg
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── Data ──────────────────────────────────────────────────────────────────────

splits = ["All", "Workforce", "Creatives", "Scientists"]

biasing_pct     = [76.5, 71.6, 83.6, 83.3]
non_biasing_pct = [23.5, 28.4, 16.4, 16.7]

missed_pct   = [64.9, 59.7, 82.4, 66.7]
followup_pct = [35.1, 40.3, 17.6, 33.3]

# ── Style ─────────────────────────────────────────────────────────────────────

COLOR_ACCENT  = "#2A3F54"   # dark blue-grey (biasing / missed)
COLOR_NEUTRAL = "#C8CDD2"   # light grey (not biasing / follow-up taken)
COLOR_LABEL   = "white"
COLOR_LABEL_DARK = "#2A3F54"

BAR_WIDTH  = 0.5
FIG_W, FIG_H = 6.5, 4.2

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
})


def styled_ax(ax, title, ylabel):
    ax.set_title(title, fontsize=12, fontweight="bold", pad=14, loc="left")
    ax.set_ylabel(ylabel, fontsize=10, color="#555")
    ax.set_ylim(0, 108)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.set_xticks(np.arange(len(splits)))
    ax.set_xticklabels(splits, fontsize=11)
    ax.tick_params(axis="both", length=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#ddd")
    ax.spines["bottom"].set_color("#ddd")
    ax.yaxis.grid(True, color="#eee", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def bar_label(ax, x, y_center, value, threshold=15):
    color = COLOR_LABEL if value >= threshold else COLOR_LABEL_DARK
    va_offset = 0 if value >= threshold else -12
    ax.text(
        x, y_center, f"{value}%",
        ha="center", va="center",
        color=color, fontsize=10.5, fontweight="bold",
    )


# ── Chart 1: Biasing response ─────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
x = np.arange(len(splits))

ax.bar(x, biasing_pct,     BAR_WIDTH, color=COLOR_ACCENT,  label="Biasing response", zorder=3)
ax.bar(x, non_biasing_pct, BAR_WIDTH, color=COLOR_NEUTRAL, label="Not biasing",
       bottom=biasing_pct, zorder=3)

for i, (b, nb) in enumerate(zip(biasing_pct, non_biasing_pct)):
    bar_label(ax, i, b / 2, b)
    if nb >= 10:
        bar_label(ax, i, b + nb / 2, nb, threshold=0)

styled_ax(ax, "Biasing response rate", "% of substantive AI turns")

legend = ax.legend(
    loc="upper left", frameon=False, fontsize=9.5,
    handlelength=1.2, handleheight=0.9,
)

plt.tight_layout()
plt.savefig("chart_biasing_response.svg", format="svg", bbox_inches="tight")
plt.close()
print("Saved chart_biasing_response.svg")


# ── Chart 2: Probe depth ──────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

ax.bar(x, missed_pct,   BAR_WIDTH, color=COLOR_ACCENT,  label="Missed opportunity", zorder=3)
ax.bar(x, followup_pct, BAR_WIDTH, color=COLOR_NEUTRAL, label="Follow-up taken",
       bottom=missed_pct, zorder=3)

for i, (m, f) in enumerate(zip(missed_pct, followup_pct)):
    bar_label(ax, i, m / 2, m)
    if f >= 10:
        bar_label(ax, i, m + f / 2, f, threshold=0)

styled_ax(ax, "Probe depth: miss rate", "% of probe opportunities")

ax.legend(
    loc="upper left", frameon=False, fontsize=9.5,
    handlelength=1.2, handleheight=0.9,
)

plt.tight_layout()
plt.savefig("chart_probe_depth.svg", format="svg", bbox_inches="tight")
plt.close()
print("Saved chart_probe_depth.svg")
