-- TTA-Solo Dolt Database Initialization
--
-- This script creates the core schema for the TTA-Solo game engine.
-- Run automatically when the Dolt container starts.

-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS tta_solo;
USE tta_solo;

-- Initialize Dolt repository
CALL DOLT_INIT();

-- Universes table (timeline branches)
CREATE TABLE IF NOT EXISTS universes (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    dolt_branch VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    depth INT NOT NULL DEFAULT 0,
    parent_universe_id VARCHAR(36),
    owner_id VARCHAR(36),
    fork_point_event_id VARCHAR(36),
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_dolt_branch (dolt_branch),
    INDEX idx_parent (parent_universe_id)
);

-- Entities table (characters, locations, items, etc.)
CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(36) PRIMARY KEY,
    universe_id VARCHAR(36) NOT NULL,
    type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tags JSON,
    stats JSON,
    faction_properties JSON,
    location_properties JSON,
    item_properties JSON,
    current_location_id VARCHAR(36),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_universe (universe_id),
    INDEX idx_type (type),
    INDEX idx_name (name),
    UNIQUE KEY uk_name_universe (name, universe_id)
);

-- Events table (append-only log - the game history)
CREATE TABLE IF NOT EXISTS events (
    id VARCHAR(36) PRIMARY KEY,
    universe_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp DATETIME NOT NULL,
    real_timestamp DATETIME NOT NULL,
    actor_id VARCHAR(36) NOT NULL,
    target_id VARCHAR(36),
    location_id VARCHAR(36),
    outcome VARCHAR(50) NOT NULL,
    roll INT,
    payload JSON,
    narrative_summary TEXT,
    caused_by_event_id VARCHAR(36),
    INDEX idx_universe_time (universe_id, timestamp),
    INDEX idx_location (location_id),
    INDEX idx_actor (actor_id)
);

-- NPC profiles (extends entities with personality data)
CREATE TABLE IF NOT EXISTS npc_profiles (
    entity_id VARCHAR(36) PRIMARY KEY,
    traits JSON NOT NULL,
    motivations JSON NOT NULL,
    speech_style VARCHAR(50),
    quirks JSON,
    lawful_chaotic INT DEFAULT 0,
    good_evil INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- NPC memories (for persistence, Neo4j handles search)
CREATE TABLE IF NOT EXISTS npc_memories (
    id VARCHAR(36) PRIMARY KEY,
    npc_id VARCHAR(36) NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    subject_id VARCHAR(36),
    description TEXT NOT NULL,
    emotional_valence FLOAT DEFAULT 0,
    importance FLOAT DEFAULT 0.5,
    event_id VARCHAR(36),
    timestamp DATETIME NOT NULL,
    times_recalled INT DEFAULT 0,
    last_recalled DATETIME,
    INDEX idx_npc (npc_id),
    INDEX idx_subject (subject_id),
    INDEX idx_event (event_id),
    FOREIGN KEY (npc_id) REFERENCES entities(id)
);

-- Commit the initial schema
CALL DOLT_ADD('.');
CALL DOLT_COMMIT('-m', 'Initialize TTA-Solo schema');

-- Create the Prime universe (default timeline)
INSERT INTO universes (
    id,
    name,
    description,
    dolt_branch,
    status,
    depth,
    is_shared,
    created_at,
    updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Prime',
    'The original timeline - the canonical reality.',
    'main',
    'active',
    0,
    TRUE,
    NOW(),
    NOW()
);

CALL DOLT_ADD('.');
CALL DOLT_COMMIT('-m', 'Create Prime universe');
