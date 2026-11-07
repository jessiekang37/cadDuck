"""Summarize condition-level GestureCAD evaluation CSV results."""

import argparse
import csv
from pathlib import Path
import sys


NASA_FIELDS = (
    "nasa_mental_demand",
    "nasa_physical_demand",
    "nasa_temporal_demand",
    "nasa_performance",
    "nasa_effort",
    "nasa_frustration",
)


def summarize(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"evaluation CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    if not records:
        return []

    conditions: dict[str, list[dict[str, str]]] = {}
    for record in records:
        conditions.setdefault(record["condition"], []).append(record)

    summaries = []
    for condition, rows in sorted(conditions.items()):
        row: dict[str, str] = {
            "condition": condition,
            "condition_count": str(len(rows)),
            "participant_count": str(len({item["participant_id"] for item in rows})),
        }
        numeric_fields = [
            f"task{index}_{suffix}"
            for index in range(1, 4)
            for suffix in ("time_seconds", "error_count")
        ] + list(NASA_FIELDS)
        for field in numeric_fields:
            values = [float(item[field]) for item in rows if item.get(field, "") != ""]
            row[f"mean_{field}"] = f"{sum(values) / len(values):.3f}" if values else ""
        summaries.append(row)
    return summaries


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", nargs="?", default=str(Path(__file__).with_name("results.csv")))
    parser.add_argument("--output", help="optional path for the summary CSV")
    args = parser.parse_args(argv)
    try:
        rows = summarize(Path(args.csv_file))
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
        return
    if not rows:
        print("No evaluation condition rows found.")
        return

    columns = list(rows[0])
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Summary written to {output_path}")
    writer = csv.DictWriter(sys.stdout, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
