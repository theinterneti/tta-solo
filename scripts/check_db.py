#!/usr/bin/env python3
"""
Database health check and initialization script.

Usage:
    uv run python scripts/check_db.py          # Check connectivity
    uv run python scripts/check_db.py --init   # Initialize schemas
"""

from __future__ import annotations

import argparse
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_dolt() -> bool:
    """Check Dolt database connectivity."""
    from src.db import DoltConnection

    host = os.getenv("DOLT_HOST", "localhost")
    port = int(os.getenv("DOLT_PORT", "3306"))
    user = os.getenv("DOLT_USER", "root")
    password = os.getenv("DOLT_PASSWORD", "doltpass")
    database = os.getenv("DOLT_DATABASE", "tta_solo")

    print(f"Checking Dolt at {host}:{port}...")

    try:
        conn = DoltConnection(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        # Try to get a connection - will raise if it fails
        db_conn = conn.get_connection()
        if db_conn.is_connected():
            print("  Dolt: Connected")
            conn.close()
            return True
        else:
            print("  Dolt: Connection failed")
            return False
    except Exception as e:
        print(f"  Dolt: Error - {e}")
        return False


def check_neo4j() -> bool:
    """Check Neo4j database connectivity."""
    from src.db import Neo4jConnection

    host = os.getenv("NEO4J_HOST", "localhost")
    port = int(os.getenv("NEO4J_BOLT_PORT", "7687"))
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpass")

    uri = f"bolt://{host}:{port}"
    print(f"Checking Neo4j at {uri}...")

    try:
        conn = Neo4jConnection(
            uri=uri,
            user=user,
            password=password,
        )
        if conn.verify_connectivity():
            print("  Neo4j: Connected")
            conn.close()
            return True
        else:
            print("  Neo4j: Connection failed")
            return False
    except Exception as e:
        print(f"  Neo4j: Error - {e}")
        return False


def init_dolt() -> bool:
    """Initialize Dolt schema."""
    from src.db import DoltConnection, init_dolt_schema

    host = os.getenv("DOLT_HOST", "localhost")
    port = int(os.getenv("DOLT_PORT", "3306"))
    user = os.getenv("DOLT_USER", "root")
    password = os.getenv("DOLT_PASSWORD", "doltpass")
    database = os.getenv("DOLT_DATABASE", "tta_solo")

    print("Initializing Dolt schema...")

    try:
        conn = DoltConnection(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        init_dolt_schema(conn)
        print("  Dolt schema initialized")
        return True
    except Exception as e:
        print(f"  Dolt init error: {e}")
        return False


def init_neo4j() -> bool:
    """Initialize Neo4j schema."""
    from src.db import Neo4jConnection, init_neo4j_schema

    host = os.getenv("NEO4J_HOST", "localhost")
    port = int(os.getenv("NEO4J_BOLT_PORT", "7687"))
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpass")

    uri = f"bolt://{host}:{port}"
    print("Initializing Neo4j schema...")

    try:
        conn = Neo4jConnection(
            uri=uri,
            user=user,
            password=password,
        )
        init_neo4j_schema(conn)
        print("  Neo4j schema initialized")
        conn.close()
        return True
    except Exception as e:
        print(f"  Neo4j init error: {e}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check and initialize TTA-Solo databases")
    parser.add_argument("--init", action="store_true", help="Initialize database schemas")
    args = parser.parse_args()

    print("TTA-Solo Database Check")
    print("=" * 40)

    dolt_ok = check_dolt()
    neo4j_ok = check_neo4j()

    if args.init:
        print()
        print("Schema Initialization")
        print("=" * 40)
        if dolt_ok:
            init_dolt()
        if neo4j_ok:
            init_neo4j()

    print()
    print("Summary")
    print("=" * 40)
    print(f"  Dolt:  {'OK' if dolt_ok else 'FAILED'}")
    print(f"  Neo4j: {'OK' if neo4j_ok else 'FAILED'}")

    return 0 if (dolt_ok and neo4j_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
