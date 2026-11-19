"""Generate reproducible raw events. Revision 2 fixtures model upstream corrections."""

from datetime import date, timedelta
from random import Random

START = date(2026, 1, 5)


def dispatch():
    rng = Random(614)
    for week in range(14):
        for index in range(108 + week * 3):
            sent = START + timedelta(days=week * 7 + rng.randrange(5))
            promised = sent + timedelta(days=rng.randrange(2, 6))
            late_rate = [17, 15, 20, 12, 14, 11, 13, 9, 8, 12, 9, 7, 6, 6][week]
            offset = rng.choice([1, 2, 3]) if rng.randrange(100) < late_rate else rng.choice([-1, 0, 0])
            row = {
                "ref": f"D-{week:02d}-{index:03d}",
                "sent_on": sent.isoformat(),
                "promised_on": promised.isoformat(),
                "delivered_on": (promised + timedelta(days=offset)).isoformat() if index % 31 else None,
                "region": rng.choice([" North", "West", "Central", "Coastal "]),
                "carrier": rng.choice(["Ember Line", "Juniper Haul", "Mosaic Freight"]),
                "freight_cents": rng.randrange(1850, 8900) + week * 46,
                "revision": 1,
            }
            yield row
            if index % 13 == 0:
                corrected = row["delivered_on"]
                if corrected and offset > 0:
                    corrected = promised.isoformat()
                yield {**row, "revision": 2, "delivered_on": corrected, "freight_cents": row["freight_cents"] + 210}


def returns():
    rng = Random(207)
    for week in range(14):
        for index in range(42 + (week * 11) % 29):
            row = {
                "ref": f"R-{week:02d}-{index:03d}",
                "opened_on": (START + timedelta(days=week * 7 + rng.randrange(7))).isoformat(),
                "channel": rng.choice([" Web", "Partner", "Store "]),
                "reason": rng.choice(["Damaged", "Wrong item", "Unwanted", "Late arrival"]),
                "refund_cents": rng.randrange(1400, 14300),
                "revision": 1,
            }
            yield row
            if index % 17 == 0:
                yield {**row, "revision": 2, "refund_cents": row["refund_cents"] + 150}


def source_rows(source: str, scenario: str) -> list[dict]:
    rows = list(dispatch() if source == "Dispatch events" else returns())
    if scenario == "negative-money":
        # Pick a latest revision that survives Silver deduplication.
        field = "freight_cents" if source == "Dispatch events" else "refund_cents"
        rows[-1][field] = -2500
    return rows
