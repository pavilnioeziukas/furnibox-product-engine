from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

from webapp.product_engine import ProductEngineSettings
from webapp.toc_foundation import ROLES, TocStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an individual Product Engine user.")
    parser.add_argument("username")
    parser.add_argument("--role", choices=sorted(ROLES), default="production_manager")
    args = parser.parse_args()
    password = getpass("New password: ")
    confirmation = getpass("Repeat password: ")
    if password != confirmation:
        parser.error("Passwords do not match.")
    settings = ProductEngineSettings.from_env(Path(__file__).resolve().parent)
    store = TocStore(settings.database_url)
    store.create_schema()
    store.create_user(args.username, password, args.role)
    print(f"Created {args.username} with role {args.role}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
