import argparse
import json
from pathlib import Path

from .catalog import PRODUCTS
from .orchestration import SCENARIOS, launch
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Operate the Enterprise Data Hub demo.")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="Build each missing sample publication.")
    seed.add_argument("--with-incident", action="store_true", help="Also run the freight quality incident once.")
    run = commands.add_parser("run", help="Materialise one product with Dagster.")
    run.add_argument("product", choices=PRODUCTS)
    run.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    delivery = commands.add_parser("snowflake-export", help="Package a publication for a Snowflake sandbox.")
    delivery.add_argument("product", choices=PRODUCTS)
    delivery.add_argument("directory", type=Path)
    args = parser.parse_args()
    store = Store()
    store.init()
    if args.command == "seed":
        for product in PRODUCTS:
            if not store.current(product):
                result = launch(store, product)
                print(f"{product}: {result['status']}")
                if result["status"] != "published":
                    raise SystemExit(1)
        if args.with_incident and not any(r["scenario"] == "negative-money" for r in store.runs()):
            print("Intentional quality incident:", launch(store, "freight-spend", "negative-money")["status"])
    elif args.command == "run":
        result = launch(store, args.product, args.scenario)
        print(json.dumps(result, indent=2))
        if result["status"] != "published":
            raise SystemExit(1)
    else:
        from .snowflake import export
        print(export(store, args.product, args.directory))


if __name__ == "__main__":
    main()
