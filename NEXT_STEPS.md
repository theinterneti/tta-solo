# TTA-Solo: Next Steps & Roadmap

**Date**: 2026-02-05  
**Current Grade**: A  
**Target Grade**: A+  
**Timeline**: 8-10 weeks

This document outlines the concrete next steps to evolve TTA-Solo from its current **A** grade to **A+** production quality.

---

## Vision: What A+ Looks Like

A **A+ TTA-Solo** delivers:
1. ✅ All current features (quests, conversation, navigation, economy)
2. ➕ **Character creation** with class choice
3. ➕ **AI narrator** that dynamically tells the story
4. ➕ **Combat encounters** playable in goblin quest
5. ➕ **10+ abilities** per class for tactical depth
6. ➕ **15+ locations** for exploration
7. ➕ **Rich content** (NPCs, items, quests)

---

## Phase 1: Combat Integration (Week 1-2)

### Goal
Make combat playable by wiring the fully-tested combat system to the goblin quest.

### Tasks

#### Week 1: Combat Trigger
- [ ] **Create combat encounter spec** (`specs/combat-encounters.md`)
  - Define when combat starts
  - Define combat flow (rounds, turns)
  - Define victory/defeat conditions
  - Define rewards

- [ ] **Wire combat to router** (`src/engine/router.py`)
  - Add `/attack` command
  - Add `/defend` command  
  - Detect combat state from quest progress
  - Route to combat skills

- [ ] **Goblin quest combat trigger**
  - Quest: "Goblin Trouble in the Woods"
  - Trigger: Travel to Tickwood Forest (3rd visit?)
  - Encounter: 2 goblins (CR 1/4 each)
  - Victory: Quest objective complete

#### Week 2: Combat UI & Polish
- [ ] **Display combat status**
  - Show current HP, momentum, stress
  - Show enemy HP
  - Show available actions

- [ ] **Combat round loop**
  - Player action → Enemy action → Repeat
  - Fray damage each round
  - Momentum gain on round start

- [ ] **Combat rewards**
  - Gold: 10-20gp
  - XP: 50 (track for future leveling)
  - Items: Goblin weapon (random)

- [ ] **Test full combat flow**
  - Playtest goblin encounter
  - Test victory path
  - Test defeat path (Defy Death)

### Deliverables
- ✅ `/attack` and `/defend` commands working
- ✅ Goblin quest triggers combat
- ✅ Full combat rounds playable
- ✅ Victory/defeat handled properly
- ✅ Rewards distributed

### Success Metrics
- Combat test coverage: 95%+
- Goblin quest completable
- Combat feels fun and balanced

---

## Phase 2: Expand Abilities (Week 2-3)

### Goal
Add 8 more abilities (10 total) for tactical variety.

### Tasks

#### Fighter Abilities (5 total)
- [x] Second Wind (implemented)
- [x] Power Strike (implemented)
- [ ] **Shield Wall** - +2 AC until next turn (bonus action)
- [ ] **Cleave** - Attack 2 adjacent enemies (costs 2 momentum)
- [ ] **Rally** - Heal stress by 1 (action, 1/rest)

#### Rogue Abilities (3 total, preparation for character creation)
- [ ] **Sneak Attack** - +2d6 damage if enemy is flanked (passive)
- [ ] **Disengage** - Move without opportunity attack (bonus action)
- [ ] **Cheap Shot** - Stun enemy, costs 3 momentum (action)

#### Mage Abilities (3 total, preparation for character creation)
- [ ] **Magic Missile** - 3 x 1d4+1 damage, never misses (1st level spell)
- [ ] **Shield** - Reaction, +5 AC vs one attack (1st level spell)
- [ ] **Burning Hands** - 3d6 fire damage, DEX save (1st level spell)

### Implementation Steps
1. **Define ability in spec** (`specs/abilities.md`)
2. **Add to Universal Ability Object** format
3. **Write tests** (`tests/test_use_ability_command.py`)
4. **Implement in ability executor** (`src/engine/ability_pbta.py`)
5. **Test in-game**

### Deliverables
- ✅ 8 new abilities implemented
- ✅ All tested (95%+ coverage)
- ✅ Available via `/use` command
- ✅ Resource tracking works

### Success Metrics
- 10 total abilities across 3 classes
- Each ability feels distinct
- Resource management is interesting

---

## Phase 3: Character Creation (Week 4-6)

### Goal
Let players create custom characters with class choice.

### Tasks

#### Week 4: Character Creation Spec & Models
- [ ] **Update archetypes spec** (`specs/archetypes.md`)
  - Character creation flow
  - Class descriptions (Fighter, Rogue, Mage)
  - Starting stats by class
  - Starting equipment by class

- [ ] **Data models** (`src/models/`)
  - `CharacterClass` enum
  - `CharacterCreationRequest` model
  - Update `Character` model with class field

#### Week 5: Creation Flow Implementation
- [ ] **/create command** (`src/engine/router.py`)
  - Step 1: Choose name
  - Step 2: Choose class
  - Step 3: Roll attributes (standard array or 4d6 drop lowest)
  - Step 4: Confirm choices

- [ ] **Class-specific starting gear**
  - Fighter: Longsword, Chain Mail, Shield
  - Rogue: Shortsword, Leather Armor, Thieves' Tools
  - Mage: Quarterstaff, Robe, Spellbook

- [ ] **Class-specific starting abilities**
  - Fighter: Second Wind, Power Strike, Shield Wall
  - Rogue: Sneak Attack, Disengage, Cheap Shot
  - Mage: Magic Missile, Shield, Burning Hands

#### Week 6: Testing & Polish
- [ ] **Test character creation flow**
  - Create fighter, rogue, mage
  - Verify stats are correct
  - Verify abilities are correct
  - Verify equipment is correct

- [ ] **Update starter world** (`src/content/starter_world.py`)
  - Don't create "Hero" by default
  - Prompt player to `/create` character

- [ ] **Welcome screen update** (`play.py`)
  - Show "Create your character with /create"
  - Show class descriptions

### Deliverables
- ✅ `/create` command working
- ✅ 3 classes (Fighter, Rogue, Mage)
- ✅ Attribute rolling
- ✅ Class-specific gear and abilities
- ✅ Character creation tests (95%+)

### Success Metrics
- Players can create unique characters
- Each class feels different
- Creation flow is smooth and intuitive

---

## Phase 4: AI Narrator Integration (Week 7-10)

### Goal
Integrate LLM to dynamically narrate the story and respond to player actions.

### Tasks

#### Week 7: Fix LLM Test & Core Service
- [ ] **Fix failing LLM test** (`tests/test_llm_integration.py`)
  - Debug API key issue
  - Ensure completion works
  - Add retry logic

- [ ] **Enhance LLM service** (`src/services/llm.py`)
  - Add streaming support
  - Add temperature control
  - Add system prompt management
  - Add context window management

#### Week 8: Game Master Agent
- [ ] **GM agent spec** (update `specs/engine.md`)
  - Define GM responsibilities
  - Define context injection
  - Define tool calling (skills)
  - Define narration style

- [ ] **Implement GM agent** (`src/engine/agents.py`)
  - Load context from Neo4j (location, NPCs, quests)
  - Generate scene descriptions
  - Interpret player actions
  - Call skills as needed
  - Narrate results

- [ ] **Context builder** (`src/services/context.py`)
  - Fetch relevant entities from Neo4j
  - Build context prompt
  - Include recent events
  - Include quest objectives

#### Week 9: Integration & Testing
- [ ] **Wire GM to game loop** (`play.py`)
  - Detect when to use GM vs direct commands
  - Free-form input → GM interprets → Skills execute
  - Commands like `/status` bypass GM

- [ ] **Prompt engineering**
  - Craft system prompt for GM
  - Test narrative quality
  - Balance verbosity
  - Ensure skill usage is correct

- [ ] **Test scenarios**
  - "I search the room" → GM calls perception check
  - "I talk to Ameiko" → GM initiates conversation
  - "I attack the goblin" → GM triggers combat
  - "I buy a sword" → GM routes to economy

#### Week 10: Polish & Refinement
- [ ] **Narration quality**
  - Consistent tone
  - Engaging descriptions
  - No hallucinations (facts from DB only)

- [ ] **Error handling**
  - Fail forward on LLM errors
  - Fallback to text descriptions
  - Log issues for improvement

- [ ] **Performance**
  - Optimize prompt size
  - Cache common contexts
  - Stream responses for speed

### Deliverables
- ✅ LLM test passing
- ✅ GM agent working
- ✅ Free-form input supported
- ✅ Context-aware narration
- ✅ Skills called correctly

### Success Metrics
- Players can type natural language
- GM generates engaging narration
- Game feels alive and responsive
- No hallucinated facts

---

## Phase 5: Content Expansion (Ongoing)

### Goal
Expand world content for richer exploration and gameplay.

### Locations (Target: 15 total, +10 more)

#### Sandpoint Expansion
- [ ] **Sandpoint Cathedral** - Healing, quests from priests
- [ ] **Sandpoint Jail** - Sheriff NPC, law enforcement
- [ ] **Blacksmith's Forge** - Buy/sell weapons and armor
- [ ] **Town Gate** - Guards, entrance to wilderness

#### Wilderness
- [ ] **Goblin Camp** - Combat encounter, treasure
- [ ] **Mysterious Cave** - Dungeon entrance
- [ ] **Ancient Ruins** - Lore, puzzles
- [ ] **Riverbank** - Fishing, rest area

#### Dungeons
- [ ] **Crypt Level 2** - Deeper underground
- [ ] **Crypt Level 3** - Boss encounter
- [ ] **Goblin Warren** - Multi-room dungeon

### NPCs (Target: 15 total, +11 more)

#### Merchants
- [ ] **Blacksmith** - Weapons and armor
- [ ] **Apothecary** - Potions and herbs
- [ ] **Fletcher** - Bows and arrows

#### Quest Givers
- [ ] **Sheriff Hemlock** - Law quests
- [ ] **Father Zantus** - Cathedral quests
- [ ] **Sage Brodert** - Lore quests

#### Enemies
- [ ] **Goblin** (already in world, need encounter)
- [ ] **Bandit** - Wilderness encounter
- [ ] **Skeleton** - Crypt encounter
- [ ] **Zombie** - Crypt encounter
- [ ] **Crypt Guardian** - Boss

### Quests (Target: 10 total, +7 more)

- [ ] **Missing Fisherman** - Investigation quest
- [ ] **Bandits on the Road** - Combat quest
- [ ] **The Sage's Lost Tome** - Fetch quest
- [ ] **Undead in the Crypt** - Dungeon quest
- [ ] **The Merchant's Problem** - Escort quest
- [ ] **Strange Noises** - Mystery quest
- [ ] **Goblin Chieftain** - Boss quest

### Items (Target: 30 total, +26 more)

#### Weapons
- [ ] Longsword, Shortsword, Dagger
- [ ] Greataxe, Battleaxe, Handaxe
- [ ] Longbow, Shortbow, Crossbow

#### Armor
- [ ] Leather Armor, Studded Leather
- [ ] Chain Mail, Chain Shirt
- [ ] Scale Mail, Plate Armor

#### Magic Items (rare drops)
- [ ] +1 Weapon (any type)
- [ ] Ring of Protection
- [ ] Cloak of Resistance
- [ ] Boots of Speed

#### Consumables
- [ ] Potion of Healing (common)
- [ ] Potion of Greater Healing (uncommon)
- [ ] Antidote
- [ ] Oil of Sharpness

---

## Testing & Quality Standards

### Test Coverage Targets
- Overall: 95%+
- New features: 100%
- Critical systems (combat, economy): 98%+

### Testing Checklist (Per Feature)
- [ ] Unit tests for all functions
- [ ] Integration tests for flows
- [ ] Manual playtest
- [ ] Edge case testing
- [ ] Performance testing (if applicable)

### Code Quality Standards
- [ ] Type hints everywhere (`str | None`, not `Optional[str]`)
- [ ] Pydantic models for all data
- [ ] Docstrings (Google style)
- [ ] 100 char line length
- [ ] Zero ruff/pyright errors

---

## Success Metrics

### Technical Metrics (Target by Week 10)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Test Pass Rate | 99.9% | 100% | 🟨 Fix 1 test |
| Code Coverage | 94% | 95%+ | 🟨 +1% |
| Type Safety | 100% | 100% | ✅ |
| Linting | 100% | 100% | ✅ |
| Source Files | 47 | 60+ | 🟦 +13 |
| Test Files | 31 | 40+ | 🟦 +9 |
| Abilities | 2 | 10+ | 🟦 +8 |
| Locations | 5 | 15+ | 🟦 +10 |
| NPCs | 4 | 15+ | 🟦 +11 |
| Quests | 3 | 10+ | 🟦 +7 |

### Player Experience Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Grade | A | A+ | 🟦 In Progress |
| Character Options | 1 | 3 classes | 🟦 Phase 3 |
| Tactical Depth | Low | High | 🟦 Phase 2 |
| Combat Playable | No | Yes | 🟦 Phase 1 |
| AI Narration | No | Yes | 🟦 Phase 4 |
| World Size | Small | Medium | 🟦 Phase 5 |
| Replayability | Low | High | 🟦 Phases 3+5 |

---

## Risk Assessment

### High Risk
1. **LLM Integration Complexity** (Phase 4)
   - **Risk**: LLM might not follow tool calling correctly
   - **Mitigation**: Extensive prompt engineering, fallback to text
   - **Impact**: High - core differentiator

2. **Combat Balance** (Phase 1)
   - **Risk**: Solo combat might be too hard/easy
   - **Mitigation**: Extensive playtesting, tuning
   - **Impact**: Medium - can adjust

### Medium Risk
3. **Content Creation Time** (Phase 5)
   - **Risk**: Creating 10+ locations/NPCs takes time
   - **Mitigation**: Use templates, procedural generation
   - **Impact**: Medium - can ship with less content

4. **Character Creation UX** (Phase 3)
   - **Risk**: Creation flow might be clunky
   - **Mitigation**: Prototype, iterate, user testing
   - **Impact**: Medium - can simplify if needed

### Low Risk
5. **Ability Implementation** (Phase 2)
   - **Risk**: Minimal - following established patterns
   - **Mitigation**: Use existing ability framework
   - **Impact**: Low - well-understood work

---

## Timeline Summary

| Phase | Weeks | Focus | Deliverable |
|-------|-------|-------|-------------|
| **Phase 1** | 1-2 | Combat | Goblin quest playable |
| **Phase 2** | 2-3 | Abilities | 10 total abilities |
| **Phase 3** | 4-6 | Character Creation | 3 classes, /create |
| **Phase 4** | 7-10 | AI Narrator | LLM-driven gameplay |
| **Phase 5** | Ongoing | Content | Expanded world |

**Total Duration**: 10 weeks (+ ongoing content)  
**Target Completion**: Mid-April 2026  
**Grade Evolution**: A → A+ 

---

## Definition of Done (A+ Criteria)

### Must Have
- ✅ All current features working (navigation, quests, etc.)
- ⬜ Character creation with 3 classes
- ⬜ 10+ abilities across classes
- ⬜ Combat playable (goblin quest)
- ⬜ AI narrator generating dynamic content
- ⬜ 15+ locations
- ⬜ 15+ NPCs
- ⬜ 10+ quests
- ⬜ 95%+ test coverage
- ⬜ 100% test pass rate

### Should Have
- ⬜ Quest completion rewards
- ⬜ Merchant reputation system
- ⬜ Boss encounters
- ⬜ Magic items

### Nice to Have
- ⬜ /fork command (multiverse)
- ⬜ Weather system
- ⬜ Time of day
- ⬜ Crafting system

---

## Weekly Checkpoints

### Week 1
- [ ] Combat encounter spec written
- [ ] `/attack` command implemented
- [ ] Goblin quest triggers combat

### Week 2
- [ ] Combat UI polished
- [ ] Victory/defeat paths working
- [ ] 3 new abilities added

### Week 3
- [ ] 5 more abilities added (10 total)
- [ ] All abilities tested

### Week 4
- [ ] Character creation spec updated
- [ ] Data models implemented

### Week 5
- [ ] `/create` command working
- [ ] 3 classes selectable

### Week 6
- [ ] Character creation tested
- [ ] Starter world updated

### Week 7
- [ ] LLM test fixed
- [ ] LLM service enhanced

### Week 8
- [ ] GM agent implemented
- [ ] Context builder working

### Week 9
- [ ] GM wired to game loop
- [ ] Free-form input working

### Week 10
- [ ] Narration polished
- [ ] Error handling solid
- [ ] A+ achieved! 🎉

---

## Resources Needed

### Development
- **Time**: ~40 hours/week for 10 weeks = 400 hours
- **LLM API**: OpenAI credits (~$50-100)
- **Testing**: Manual playtesting (5-10 hours)

### Tools
- ✅ Python, uv, pytest (already set up)
- ✅ Neo4j, Dolt (already configured)
- 🟦 LLM API key (need to configure)

### Documentation
- ✅ All specs exist (need updates)
- ✅ Code is well-documented
- 🟦 Playtest reports (ongoing)

---

## Next Actions (This Week)

### Day 1: Combat Spec
- [ ] Write `specs/combat-encounters.md`
- [ ] Define combat flow in detail
- [ ] Define trigger conditions

### Day 2-3: Combat Implementation
- [ ] Add `/attack` command to router
- [ ] Wire combat skills
- [ ] Test manually

### Day 4-5: Goblin Quest Integration
- [ ] Modify goblin quest to trigger combat
- [ ] Test full quest flow
- [ ] Adjust balance

### Day 6-7: New Abilities
- [ ] Implement Shield Wall (Fighter)
- [ ] Implement Cleave (Fighter)
- [ ] Test in combat

---

## Conclusion

This roadmap provides a **clear path from A to A+** over the next 10 weeks. Each phase builds on the previous one, and all work is grounded in the existing specs and architecture.

**Key Priorities**:
1. **Combat** - Make the goblin quest playable (immediate impact)
2. **Abilities** - Add tactical depth (quick wins)
3. **Character Creation** - Enable replayability (high value)
4. **AI Narrator** - Differentiate from other text adventures (unique feature)
5. **Content** - Expand the world (ongoing effort)

**Success Factors**:
- ✅ Strong foundation already built
- ✅ Clear specs to follow
- ✅ High test coverage
- ✅ Proven architecture
- 🟦 Focused execution needed

**By mid-April 2026, TTA-Solo will be a A+ production-quality game.**

---

**Document Created**: 2026-02-05  
**Owner**: Development Team  
**Next Review**: 2026-02-12 (after Phase 1 completion)
