// TTA-Solo Neo4j Database Initialization
//
// This script creates indexes and constraints for the graph database.
// Run after container starts via:
//   docker exec tta-neo4j cypher-shell -u neo4j -p neo4jpass \
//     -f /var/lib/neo4j/import/init.cypher
//
// SECURITY NOTE: Change default passwords in production!

// =============================================================================
// Entity Indexes
// =============================================================================

// Primary lookup by ID
CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) ON (e.id);

// Name-based lookups
CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name);

// Universe-scoped queries
CREATE INDEX entity_universe_index IF NOT EXISTS FOR (e:Entity) ON (e.universe_id);

// Type-based filtering
CREATE INDEX entity_type_index IF NOT EXISTS FOR (e:Entity) ON (e.type);

// =============================================================================
// Memory Indexes (for NPC AI)
// =============================================================================

CREATE INDEX memory_id_index IF NOT EXISTS FOR (m:Memory) ON (m.id);
CREATE INDEX memory_npc_index IF NOT EXISTS FOR (m:Memory) ON (m.npc_id);
CREATE INDEX memory_type_index IF NOT EXISTS FOR (m:Memory) ON (m.type);
CREATE INDEX memory_timestamp_index IF NOT EXISTS FOR (m:Memory) ON (m.timestamp);

// =============================================================================
// Relationship Indexes
// =============================================================================

// Universe-scoped relationship queries
CREATE INDEX rel_universe_index IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.universe_id);

// Relationship type filtering
CREATE INDEX rel_type_index IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.type);

// =============================================================================
// Vector Index for Semantic Search
// =============================================================================
// Note: Requires Neo4j 5.11+ with native vector index support.
// The similarity_search method in src/db/neo4j_driver.py uses cosine similarity.
// Uncomment when vector embeddings are implemented:
//
// CALL db.index.vector.createNodeIndex(
//   'entityEmbeddings',
//   'Entity',
//   'embedding',
//   1536,
//   'cosine'
// );

// =============================================================================
// Constraints
// =============================================================================

// Ensure entity IDs are unique (covers Character, Location, Item via multi-label)
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;

// Ensure memory IDs are unique
CREATE CONSTRAINT memory_id_unique IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;
