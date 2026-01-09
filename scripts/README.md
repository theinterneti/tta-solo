# TTA-Solo Database Scripts

Scripts for initializing and managing the database infrastructure.

## Files

- `init-dolt.sql` - Dolt schema initialization (auto-runs on container start)
- `init-neo4j.cypher` - Neo4j indexes and constraints

## Quick Start

```bash
# Start the databases
docker compose up -d

# Wait for services to be healthy
docker compose ps

# Check Dolt is ready
docker exec tta-dolt mysql -u root -pdoltpass -e "USE tta_solo; SHOW TABLES;"

# Initialize Neo4j indexes (after container is healthy)
docker exec tta-neo4j cypher-shell -u neo4j -p neo4jpass -f /var/lib/neo4j/import/init.cypher
```

## Manual Schema Updates

If you need to update the schema after initial setup:

### Dolt

```bash
docker exec -it tta-dolt mysql -u root -pdoltpass tta_solo
```

### Neo4j

```bash
docker exec -it tta-neo4j cypher-shell -u neo4j -p neo4jpass
```

Or use the Neo4j Browser at http://localhost:7474

## Resetting Databases

```bash
# Stop and remove volumes (WARNING: deletes all data!)
docker compose down -v

# Start fresh
docker compose up -d
```
