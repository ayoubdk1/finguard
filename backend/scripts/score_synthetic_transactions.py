
import csv
from pathlib import Path

from app.services.risk import assess_risk


BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_FILE = BASE_DIR / "data" / "synthetic_transactions.csv"
OUTPUT_FILE = BASE_DIR / "data" / "scored_transactions.csv"


def score_transactions():
    with INPUT_FILE.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)

        fieldnames = list(reader.fieldnames or []) + [
            "risk_score",
            "risk_decision",
            "risk_reasons",
        ]

        count = 0

        with OUTPUT_FILE.open(
            "w", encoding="utf-8", newline=""
        ) as output_file:

            writer = csv.DictWriter(
                output_file,
                fieldnames=fieldnames
            )
            writer.writeheader()

            for row in reader:
                result = assess_risk(
                    amount_cents=int(row["amount_cents"]),
                    transfers_last_10min=int(row["transfers_last_10min"]),
                    account_age_minutes=int(row["account_age_minutes"]),
                    failed_transfers_last_hour=int(
                        row["failed_transfers_last_hour"]
                    ),
                )

                row["risk_score"] = result["score"]
                row["risk_decision"] = result["decision"]
                row["risk_reasons"] = "|".join(
                    result["reason_codes"]
                )

                writer.writerow(row)
                count += 1

    print(f"Scored {count} transactions")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    score_transactions()
