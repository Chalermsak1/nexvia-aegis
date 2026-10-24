from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "results" / "v1.0_summary.csv"
OUT_DIR = ROOT / "results" / "figures"

OUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def load_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(
        newline="",
        encoding="utf-8",
    ) as file:
        return list(
            csv.DictReader(file)
        )


def plot_metric(
    rows: list[dict[str, str]],
    evaluation: str,
    metric: str,
    filename: str,
    ylabel: str,
) -> None:
    scenarios = [
        "NORMAL",
        "BIASED",
        "HEAVY_TAIL",
        "OUTLIER",
        "DRIFT",
        "CORRELATED_BIAS",
    ]

    policies = [
        "Always Act",
        "Inspect Once",
        "Nexvia Aegis",
    ]

    values: dict[
        str,
        list[float],
    ] = {
        policy: []
        for policy in policies
    }

    for scenario in scenarios:
        for policy in policies:
            match = next(
                row
                for row in rows
                if row["evaluation"] == evaluation
                and row["scenario"] == scenario
                and row["policy"] == policy
            )

            values[policy].append(
                float(match[metric])
            )

    x = np.arange(
        len(scenarios)
    )

    width = 0.25

    for index, policy in enumerate(
        policies
    ):
        plt.bar(
            x
            + (index - 1) * width,
            values[policy],
            width,
            label=policy,
        )

    plt.xticks(
        x,
        scenarios,
        rotation=30,
        ha="right",
    )

    plt.ylabel(ylabel)

    plt.xlabel("Scenario")

    plt.title(
        f"Nexvia Aegis v1.0 — "
        f"{evaluation.title()} Evaluation"
    )

    plt.legend()

    plt.tight_layout()

    plt.savefig(
        OUT_DIR / filename,
        dpi=200,
        bbox_inches="tight",
    )

    plt.close()


def main() -> None:
    rows = load_rows()

    plot_metric(
        rows,
        "final",
        "false_stop_rate",
        "final_false_stop_rate.png",
        "False Stop Rate (%)",
    )

    plot_metric(
        rows,
        "holdout",
        "false_stop_rate",
        "holdout_false_stop_rate.png",
        "False Stop Rate (%)",
    )

    print(
        f"Figures written to: {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
