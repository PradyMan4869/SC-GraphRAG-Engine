"""
Optional lean entity-extraction system prompt for small local models.

LightRAG's default extraction system prompt is ~3,000 tokens (long instructions
plus worked examples). A 1.5B model tends to lose track of it: it repeats the
same entity lines until the token limit and never reaches the relations. This
prompt is ~400 tokens, has hard output limits and a no-repeat rule, and keeps the
exact record format LightRAG's parser requires.

Enabled with EXTRACT_PROMPT=lean (default: LightRAG's own prompt, unchanged).
Call apply_if_enabled() before any extraction.
"""
from __future__ import annotations

import os

from lightrag.prompt import PROMPTS

LEAN_SYSTEM_PROMPT = """You extract a knowledge graph from the text of an Indian Supreme Court judgment.

Output ONLY lines in these two formats. The separator is {tuple_delimiter} and must never appear inside a field.
entity{tuple_delimiter}NAME{tuple_delimiter}TYPE{tuple_delimiter}ONE-SENTENCE DESCRIPTION
relation{tuple_delimiter}SOURCE{tuple_delimiter}TARGET{tuple_delimiter}KEYWORDS{tuple_delimiter}ONE-SENTENCE DESCRIPTION

Rules:
- TYPE must be one of: {entity_types}. Use Other if none fits.
- Entities: statutes and sections (e.g. Section 138, Negotiable Instruments Act), constitutional articles, courts, named parties, case names, legal doctrines, key events. Skip generic words (court, appellant, order, judgment) unless they name a specific party or body.
- List each entity ONCE. At most 12 entities, then at most 12 relations. Never repeat a line.
- Relations link two entities from your own entity list, using exactly the same names. Pick the most important relations.
- Write all entities first, then all relations, then the final line {completion_delimiter}

Example output:
entity{tuple_delimiter}Article 21{tuple_delimiter}Law{tuple_delimiter}Constitutional guarantee of life and personal liberty.
entity{tuple_delimiter}Maneka Gandhi v. Union of India{tuple_delimiter}Event{tuple_delimiter}Case that widened the meaning of Article 21.
relation{tuple_delimiter}Maneka Gandhi v. Union of India{tuple_delimiter}Article 21{tuple_delimiter}interpretation, due process{tuple_delimiter}The case interpreted Article 21 to require a fair procedure.
{completion_delimiter}
"""


def enabled() -> bool:
    return os.getenv("EXTRACT_PROMPT", "").lower() == "lean"


def apply_if_enabled() -> bool:
    """Swap LightRAG's extraction system prompt for the lean one. Returns True if applied."""
    if enabled():
        PROMPTS["entity_extraction_system_prompt"] = LEAN_SYSTEM_PROMPT
        return True
    return False
