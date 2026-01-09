// TTA-Solo Neo4j Database Initialization
//
// This script creates indexes and constraints for the graph database.
// Import this via Neo4j Browser or cypher-shell after container starts.

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
// Character Indexes (NPCs and Players)
// =============================================================================

CREATE INDEX character_id_index IF NOT EXISTS FOR (c:Character) ON (c.id);
CREATE INDEX character_name_index IF NOT EXISTS FOR (c:Character) ON (c.name);

// =============================================================================
// Location Indexes
// =============================================================================

CREATE INDEX location_id_index IF NOT EXISTS FOR (l:Location) ON (l.id);
CREATE INDEX location_name_index IF NOT EXISTS FOR (l:Location) ON (l.name);

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
// Note: Requires Neo4j 5.x with Graph Data Science (GDS) library
// Uncomment after GDS is confirmed available:
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

// Ensure entity IDs are unique
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;

// Ensure character IDs are unique
CREATE CONSTRAINT character_id_unique IF NOT EXISTS FOR (c:Character) REQUIRE c.id IS UNIQUE;

// Ensure location IDs are unique
CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.id IS UNIQUE;

// Ensure memory IDs are unique
CREATE CONSTRAINT memory_id_unique IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;
