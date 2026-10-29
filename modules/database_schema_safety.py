"""Protect user-owned schema attached to catalogs before destructive updates."""
from __future__ import annotations

import sqlite3


class UnsafeCatalogSchemaError(RuntimeError):
    """A custom trigger or foreign key could change or orphan user data."""


def quote_identifier(name: str) -> str:
    """Quote an identifier read from the user's existing SQLite schema."""
    return '"' + name.replace('"', '""') + '"'


def validate_catalog_schema(connection: sqlite3.Connection, *, written_tables: set[str],
                            affected: dict[str, set[str]]) -> None:
    """Refuse triggers and links that could be damaged by catalog writes.

    SQLite's foreign-key enforcement is normally off per connection. A catalog
    update can thus orphan a user's annotation; enabling enforcement could
    instead cascade-delete or rewrite it. Reinserted effect keys may also
    acquire a different meaning after reparsing. References to untouched rows
    are allowed, while affected or already-unresolved links require review.
    """
    for name, table in connection.execute(
            "SELECT name, tbl_name FROM sqlite_master WHERE type='trigger'"):
        if str(table).casefold() in written_tables:
            raise UnsafeCatalogSchemaError(
                f"Custom database trigger {name!r} on {table} may modify user data; "
                "no catalog changes were made. Preserve and review it before retrying."
            )

    identities = {"weapons": "weapon", "mods": "unique_name", "mod_effects": "unique_name"}
    affected = {table: {key.rstrip().casefold() for key in keys}
                for table, keys in affected.items() if keys}
    if not affected:
        return

    tables = [str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7)) != 'sqlite_'")]
    existing_tables = {name.casefold() for name in tables}
    for child in tables:
        foreign_keys: dict[int, list[tuple]] = {}
        for row in connection.execute(f"PRAGMA foreign_key_list({quote_identifier(child)})"):
            if str(row[2]).casefold() in affected:
                foreign_keys.setdefault(int(row[0]), []).append(row)
        for rows in foreign_keys.values():
            rows.sort(key=lambda row: int(row[1]))
            parent = str(rows[0][2]).casefold()
            nonnull = [f"c.{quote_identifier(str(row[3]))} IS NOT NULL" for row in rows]
            if parent not in existing_tables:
                query = (f"SELECT 1 FROM {quote_identifier(child)} AS c "
                         f"WHERE {' AND '.join(nonnull)} LIMIT 1")
                if connection.execute(query).fetchone():
                    raise UnsafeCatalogSchemaError(
                        f"Custom foreign key from {child!r} has an unresolved {parent} parent; "
                        "no catalog changes were made. Preserve and review it before retrying."
                    )
                continue
            primary_key = sorted(
                ((int(row[5]), str(row[1])) for row in connection.execute(
                    f"PRAGMA table_info({quote_identifier(parent)})") if int(row[5]) > 0),
                key=lambda item: item[0],
            )
            comparisons = []
            for row in rows:
                sequence = int(row[1])
                target = row[4]
                if target is None:
                    if sequence >= len(primary_key):
                        raise UnsafeCatalogSchemaError(
                            f"Cannot resolve a foreign key from {child!r} to {parent}; "
                            "no catalog changes were made."
                        )
                    target = primary_key[sequence][1]
                source = quote_identifier(str(row[3]))
                comparisons.append(f"p.{quote_identifier(str(target))} = c.{source}")
            query = (
                f"SELECT p.{quote_identifier(identities[parent])} "
                f"FROM {quote_identifier(child)} AS c "
                f"LEFT JOIN {quote_identifier(parent)} AS p ON {' AND '.join(comparisons)} "
                f"WHERE {' AND '.join(nonnull)}"
            )
            for (identity,) in connection.execute(query):
                if identity is None or str(identity).rstrip().casefold() in affected[parent]:
                    raise UnsafeCatalogSchemaError(
                        f"Custom foreign key from {child!r} references affected or unresolved "
                        f"{parent} data; no catalog changes were made. Preserve and review "
                        "those linked rows before retrying."
                    )
