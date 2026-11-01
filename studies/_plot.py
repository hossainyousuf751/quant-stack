"""Shared plot style, matching the five libraries: seaborn-deep colours, varied line styles, bold left titles."""

from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
DOCS.mkdir(exist_ok=True)
C = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]
LS = ["-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1))]


def finish(fig, ax, name: str, title: str) -> Path:
    ax.set_title(title, loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    path = DOCS / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return path
