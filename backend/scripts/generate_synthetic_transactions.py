
import csv
import random
from pathlib import Path

# Reproducible dataset
rng = random.Random(42)

# Output file
BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT = BASE_DIR / "data" / "synthetic_transactions.csv"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

fields = [
    "transaction_id",
    "amount_cents",
    "transfers_last_10min",
    "account_age_minutes",
    "failed_transfers_last_hour",
    "is_fraud",
]

with OUTPUT.open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()

    for i in range(1, 1001):

        # Simulated fraud label (10% probability)
        is_fraud = int(rng.random() < 0.10)

        if is_fraud:
            amount = rng.randint(15000, 180000)
            velocity = rng.randint(1, 6)
            age = rng.randint(10, 40000)
            failures = rng.randint(0, 5)
        else:
            amount = rng.randint(100, 110000)
            velocity = rng.randint(0, 4)
            age = rng.randint(60, 150000)
            failures = rng.randint(0, 3)

        writer.writerow({
            "transaction_id": f"SIM-{i:06d}",
            "amount_cents": amount,
            "transfers_last_10min": velocity,
            "account_age_minutes": age,
            "failed_transfers_last_hour": failures,
            "is_fraud": is_fraud,
        })

print(f"Generated 1000 transactions: {OUTPUT}")
