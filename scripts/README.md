# TTA-Solo Database Scripts

Scripts for initializing and managing the database infrastructure.

## Files

- `init-dolt.sql` - Dolt schema initialization (auto-runs on container start)
- `init-neo4j.cypher` - Neo4j indexes and constraints (requires manual init)
- `check_db.py` - Python utility to verify database connectivity

## Quick Start

```bash
# Start the databases
docker compose up -d

# Wait for services to be healthy
docker compose ps

# Check Dolt is ready (uses default password; customize via .env)
docker exec tta-dolt mysql -u root -p"${DOLT_PASSWORD:-doltpass}" -e "USE tta_solo; SHOW TABLES;"

# Initialize Neo4j indexes (one-time, after container is healthy)
docker exec tta-neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-neo4jpass}" \
  -f /var/lib/neo4j/import/init.cypher
```

**Note:** The commands above use default passwords for local development.
For customized setups, copy `.env.example` to `.env` and update the passwords.

## Python Connectivity Check

```bash
# Check database connectivity
uv run python scripts/check_db.py

# Initialize schemas via Python (alternative to Docker init)
uv run python scripts/check_db.py --init
```

## Manual Schema Updates

If you need to update the schema after initial setup:

### Dolt

```bash
docker exec -it tta-dolt mysql -u root -p"${DOLT_PASSWORD:-doltpass}" tta_solo
```

### Neo4j

```bash
docker exec -it tta-neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-neo4jpass}"
```

Or use the Neo4j Browser at http://localhost:7474

## Resetting Databases

```bash
# Stop and remove volumes (WARNING: deletes all data!)
docker compose down -v

# Start fresh
docker compose up -d
```

## Security Note

The default passwords (`doltpass`, `neo4jpass`) are for local development only.
Always use strong, unique passwords for any non-local environment.
