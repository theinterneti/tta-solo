"""
Intent Parser for TTA-Solo.

Parses player input into structured Intent objects.
Uses pattern matching for common actions, with LLM fallback for complex cases.
"""

from __future__ import annotations

import re
from typing import Protocol

from src.engine.models import Intent, IntentType


class LLMProvider(Protocol):
    """Interface for LLM-based intent parsing."""

    async def parse_intent(self, player_input: str, context: str) -> Intent:
        """Parse player input using LLM."""
        ...


# Pattern definitions for rule-based parsing
INTENT_PATTERNS: dict[IntentType, list[re.Pattern]] = {
    IntentType.ATTACK: [
        re.compile(r"\b(attack|hit|strike|stab|slash|shoot|fire at)\b", re.I),
        re.compile(r"\bi (attack|hit|strike|stab|slash|shoot)\b", re.I),
    ],
    IntentType.CAST_SPELL: [
        re.compile(r"\b(cast|use spell|cast spell)\b", re.I),
        re.compile(r"\bi cast\b", re.I),
    ],
    IntentType.TALK: [
        re.compile(r'\b(say|tell|ask|speak|talk)\b.*["\']', re.I),
        re.compile(r"\bi (say|tell|ask|speak to|talk to)\b", re.I),
    ],
    IntentType.PERSUADE: [
        re.compile(r"\b(persuade|convince|negotiate)\b", re.I),
    ],
    IntentType.INTIMIDATE: [
        re.compile(r"\b(intimidate|threaten|scare)\b", re.I),
    ],
    IntentType.DECEIVE: [
        re.compile(r"\b(lie|deceive|trick|bluff)\b", re.I),
    ],
    IntentType.MOVE: [
        re.compile(r"\b(go|walk|run|move|head|travel)\s+(to|towards?|into?)\b", re.I),
        re.compile(r"\b(go|walk|run|move|head)\s+(north|south|east|west|up|down)\b", re.I),
        re.compile(r"\b(enter|leave|exit)\b", re.I),
    ],
    IntentType.LOOK: [
        re.compile(r"\b(look|examine|inspect|observe|watch)\b", re.I),
        re.compile(r"\bwhat do i see\b", re.I),
    ],
    IntentType.SEARCH: [
        re.compile(r"\b(search|investigate|check|look for)\b", re.I),
    ],
    IntentType.INTERACT: [
        re.compile(r"\b(open|close|push|pull|use|activate|touch)\b", re.I),
    ],
    IntentType.USE_ITEM: [
        re.compile(r"\b(use|drink|eat|apply|read)\s+(my|the|a)\b", re.I),
    ],
    IntentType.PICK_UP: [
        re.compile(r"\b(pick up|grab|collect|get)\b", re.I),
        re.compile(r"\btake\s+(?:the\s+)?(?!a\s+(?:short|long)\s+rest)", re.I),  # "take X" but not "take a rest"
    ],
    IntentType.DROP: [
        re.compile(r"\b(drop|put down|discard|throw away)\b", re.I),
    ],
    IntentType.GIVE: [
        re.compile(r"\b(give|hand|offer|pass)\b.*\bto\b", re.I),
    ],
    IntentType.REST: [
        re.compile(r"\b(rest|take a (short|long) rest|sleep|camp)\b", re.I),
    ],
    IntentType.WAIT: [
        re.compile(r"\b(wait|stay|remain|do nothing)\b", re.I),
    ],
    IntentType.ASK_QUESTION: [
        re.compile(r"^(what|where|who|why|how|when)\s+(is|are|was|were|do|does|did|can|could)\b", re.I),
    ],
    IntentType.FORK: [
        re.compile(r"\bwhat if\b", re.I),
        re.compile(r"\blet'?s go back\b", re.I),
        re.compile(r"\bundo\b", re.I),
    ],
}

# Target extraction patterns
TARGET_PATTERNS = [
    re.compile(r"\b(?:the|a|an)\s+(\w+(?:\s+\w+)?)\b", re.I),  # "the goblin"
    re.compile(r"\bat\s+(?:the\s+)?(\w+(?:\s+\w+)?)\b", re.I),  # "at the door"
    re.compile(r"\bto\s+(?:the\s+)?(\w+(?:\s+\w+)?)\b", re.I),  # "to the merchant"
]

# Direction extraction for MOVE
DIRECTION_PATTERN = re.compile(
    r"\b(north|south|east|west|up|down|left|right|forward|back|inside|outside)\b", re.I
)

# Dialogue extraction for TALK
DIALOGUE_PATTERN = re.compile(r'["\'](.+?)["\']', re.I)


def extract_target(text: str) -> str | None:
    """Extract target from player input."""
    for pattern in TARGET_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_destination(text: str) -> str | None:
    """Extract movement destination from player input."""
    match = DIRECTION_PATTERN.search(text)
    if match:
        return match.group(1).lower()

    # Try extracting location name
    location_pattern = re.compile(
        r"\b(?:go|walk|run|move|head|travel)\s+(?:to|towards?|into?)\s+(?:the\s+)?(.+?)(?:\.|$)",
        re.I,
    )
    match = location_pattern.search(text)
    if match:
        return match.group(1).strip()

    return None


def extract_dialogue(text: str) -> str | None:
    """Extract quoted dialogue from player input."""
    match = DIALOGUE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


class PatternIntentParser:
    """Rule-based intent parser using regex patterns."""

    def parse(self, player_input: str) -> Intent:
        """
        Parse player input into an Intent using pattern matching.

        Args:
            player_input: Raw text from the player

        Returns:
            Intent object with parsed information
        """
        text = player_input.strip()

        # Try each intent type's patterns
        matched_type = IntentType.UNCLEAR
        confidence = 0.5

        for intent_type, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(text):
                    matched_type = intent_type
                    confidence = 0.8
                    break
            if matched_type != IntentType.UNCLEAR:
                break

        # Extract additional information based on intent type
        target_name = extract_target(text)
        destination = None
        dialogue = None
        method = None

        if matched_type == IntentType.MOVE:
            destination = extract_destination(text)
            target_name = None  # Don't confuse destination with target

        elif matched_type == IntentType.TALK:
            dialogue = extract_dialogue(text)

        elif matched_type == IntentType.ATTACK:
            # Try to extract weapon/method
            weapon_pattern = re.compile(r"\bwith\s+(?:my\s+)?(.+?)(?:\.|$)", re.I)
            match = weapon_pattern.search(text)
            if match:
                method = match.group(1).strip()

        return Intent(
            type=matched_type,
            confidence=confidence,
            target_name=target_name,
            destination=destination,
            dialogue=dialogue,
            method=method,
            original_input=text,
            reasoning=f"Matched pattern for {matched_type.value}",
        )


class MockLLMParser:
    """Mock LLM parser for testing."""

    def __init__(self, default_intent_type: IntentType = IntentType.UNCLEAR) -> None:
        self.default_intent_type = default_intent_type
        self.call_count = 0

    async def parse_intent(self, player_input: str, context: str = "") -> Intent:
        """Return a mock intent for testing."""
        self.call_count += 1

        # Use pattern parser as base, but mark as LLM-parsed
        pattern_parser = PatternIntentParser()
        intent = pattern_parser.parse(player_input)

        # Override if pattern couldn't determine
        if intent.type == IntentType.UNCLEAR:
            intent.type = self.default_intent_type

        intent.confidence = 0.95
        intent.reasoning = "Parsed by MockLLM"
        return intent


class HybridIntentParser:
    """
    Hybrid intent parser combining pattern matching and LLM.

    Uses fast pattern matching for clear intents,
    falls back to LLM for ambiguous cases.
    """

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.pattern_parser = PatternIntentParser()
        self.llm_provider = llm_provider
        self.confidence_threshold = confidence_threshold

    async def parse(self, player_input: str, context: str = "") -> Intent:
        """
        Parse player input, using LLM if pattern matching is uncertain.

        Args:
            player_input: Raw text from the player
            context: Optional context string for LLM

        Returns:
            Intent object with parsed information
        """
        # Try pattern matching first
        intent = self.pattern_parser.parse(player_input)

        # If confident enough, return pattern result
        if intent.confidence >= self.confidence_threshold:
            return intent

        # Fall back to LLM if available
        if self.llm_provider is not None:
            import contextlib

            with contextlib.suppress(Exception):
                intent = await self.llm_provider.parse_intent(player_input, context)

        return intent
