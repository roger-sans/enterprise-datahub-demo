import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
PRODUCTS = {
    product["id"]: product
    for product in json.loads((PACKAGE / "contracts/portfolio.json").read_text(encoding="utf-8"))
}
BASE_CONTRACTS = {
    key: json.loads((PACKAGE / "contracts" / f"{key}.json").read_text(encoding="utf-8"))
    for key in PRODUCTS
}
ACTORS = {
    "platform-operator": {"name": "Platform Operator", "role": "operator"},
    "governance-steward": {"name": "Governance Steward", "role": "steward"},
    "operations-owner": {"name": "Fulfilment Data Owner", "role": "owner"},
    "finance-owner": {"name": "Finance Data Owner", "role": "owner"},
    "experience-owner": {"name": "Customer Experience Data Owner", "role": "owner"},
    "analytics-consumer": {"name": "Analytics Consumer", "role": "consumer"},
}
OPTIONAL_FIELD = {
    "name": "reporting_note",
    "type": "string",
    "description": "Reserved for an optional annotation on the published aggregate",
    "required": False,
}
SOURCE_COLUMNS = {
    "Dispatch events": ["ref", "sent_on", "promised_on", "delivered_on", "region", "carrier", "freight_cents", "revision"],
    "Return events": ["ref", "opened_on", "channel", "reason", "refund_cents", "revision"],
}


def sql_for(name: str) -> str:
    return (PACKAGE / "sql" / f"{name.replace('-', '_')}.sql").read_text(encoding="utf-8")


def compatibility(previous: dict, candidate: dict) -> list[str]:
    old = {field["name"]: field for field in previous["fields"]}
    new = {field["name"]: field for field in candidate["fields"]}
    changes = []
    if previous["primary_key"] != candidate["primary_key"]:
        changes.append("The published grain or primary key changed.")
    for name, field in old.items():
        if name not in new:
            changes.append(f"Published column {name} was removed.")
        elif field["type"] != new[name]["type"] or field["required"] != new[name]["required"]:
            changes.append(f"Published column {name} changed type or nullability.")
    for name in new.keys() - old.keys():
        if new[name]["required"]:
            changes.append(f"New column {name} is required for existing consumers.")
    retained_order = [name for name in new if name in old]
    if retained_order != [name for name in old if name in new]:
        changes.append("Published CSV column order changed.")
    if list(new)[:len(old)] != list(old) and len(new) > len(old):
        changes.append("New fields must be appended after existing CSV columns.")
    return changes
