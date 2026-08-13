from __future__ import annotations

import argparse
import os
import re

import psycopg
from psycopg import sql

DATABASE_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}")


def _database_name(value: str) -> str:
    if not DATABASE_NAME.fullmatch(value):
        raise argparse.ArgumentTypeError("database name contains unsupported characters")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new isolated PostgreSQL database from an existing template"
    )
    parser.add_argument("--source", required=True, type=_database_name)
    parser.add_argument("--target", required=True, type=_database_name)
    args = parser.parse_args()
    if args.source == args.target:
        parser.error("source and target databases must differ")
    connection_options = {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }
    with psycopg.connect(dbname="postgres", autocommit=True, **connection_options) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (args.target,)
        ).fetchone()
        if exists is not None:
            raise SystemExit(f"refusing to overwrite existing database: {args.target}")
        source = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (args.source,)
        ).fetchone()
        if source is None:
            raise SystemExit(f"source database does not exist: {args.source}")
        connection.execute(
            sql.SQL("CREATE DATABASE {} WITH TEMPLATE {}").format(
                sql.Identifier(args.target), sql.Identifier(args.source)
            )
        )
    print(f"created isolated database {args.target} from {args.source}")


if __name__ == "__main__":
    main()
