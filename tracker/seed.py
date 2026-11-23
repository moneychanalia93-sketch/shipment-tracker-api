"""Fill the database with fake shipments: python -m tracker.seed"""

import argparse
import random
from datetime import date, timedelta

from tracker import db

CUSTOMERS = ["Acme Corp", "Birch Foods", "Cobalt Labs", "Delta Toys", "Eagle Tools",
             "Fern Books", "Globe Gear", "Harbor Pets", "Iris Home", "Juniper Kits"]
CITIES = ["Austin", "Boston", "Chicago", "Denver", "Phoenix", "Seattle", "Atlanta", "Dallas"]

# How likely each final status is. "cancelled" is rare on purpose:
# a rare value is where an index helps the most.
STATUS_WEIGHTS = {"created": 30, "packed": 25, "shipped": 25, "delivered": 18, "cancelled": 2}

# The steps a shipment took to reach each final status (used for history).
PATHS = {
    "created": ["created"],
    "packed": ["created", "packed"],
    "shipped": ["created", "packed", "shipped"],
    "delivered": ["created", "packed", "shipped", "delivered"],
    "cancelled": ["created", "cancelled"],
}


# Insert `count` fake shipments, each with a believable history.
# The same seed number always gives the same data, so runs can be compared.
# Everything is saved in one transaction, which is much faster.
def add_fake_shipments(conn, count, seed=42):
    rng = random.Random(seed)
    today = date.today()
    now = db.now_text()
    statuses = list(STATUS_WEIGHTS)
    weights = list(STATUS_WEIGHTS.values())
    with conn:
        for _ in range(count):
            status = rng.choices(statuses, weights)[0]
            promised = (today + timedelta(days=rng.randint(-15, 30))).isoformat()
            cursor = conn.execute(
                "INSERT INTO shipments"
                " (customer, destination, promised_date, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (rng.choice(CUSTOMERS), rng.choice(CITIES), promised, status, now, now),
            )
            steps = PATHS[status]
            conn.executemany(
                "INSERT INTO history (shipment_id, from_status, to_status, note, created_at)"
                " VALUES (?, ?, ?, 'seeded', ?)",
                [(cursor.lastrowid, before, after, now)
                 for before, after in zip([None] + steps, steps)],
            )


# Command line: create the tables, add the shipments, print the counts.
def main():
    parser = argparse.ArgumentParser(description="Add fake shipments")
    parser.add_argument("--db", default="shipments.db")
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    db.init_db(args.db)
    conn = db.connect(args.db)
    add_fake_shipments(conn, args.count)
    stats = db.get_stats(conn, date.today().isoformat())
    conn.close()
    print(f"Added {args.count} shipments to {args.db}")
    print(f"Totals now: {stats['total']} shipments, {stats['late']} late")
    print("By status:", stats["by_status"])


if __name__ == "__main__":
    main()
