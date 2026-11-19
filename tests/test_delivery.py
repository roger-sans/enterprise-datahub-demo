import json
from pathlib import Path

import pytest
from sqlglot import parse_one

from hub.catalog import PRODUCTS, sql_for

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("model", [*PRODUCTS, "dispatch-silver", "returns-silver"])
def test_shared_models_parse_as_snowflake_sql(model):
    assert parse_one(sql_for(model), read="snowflake")


def test_backlog_dependencies_and_scoring():
    backlog = json.loads((ROOT / "hub/contracts/delivery.json").read_text(encoding="utf-8"))
    items = {item["id"]: item for item in backlog["items"]}
    assert len(items) == len(backlog["items"]) == 8
    for item in items.values():
        assert item["score"] == round((item["value"] + item["risk"]) / item["effort"], 2)
        for dependency in item["depends"]:
            assert items[dependency]["milestone"] <= item["milestone"]
        path = item["evidence"].split("docs/", 1)
        if len(path) == 2:
            assert (ROOT / "docs" / path[1].split(" ", 1)[0].rstrip(".")).is_file()
