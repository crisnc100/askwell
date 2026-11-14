"""Feature switches: each v0.3 feature that can turn a refusal into an answer can be
switched off, by name, with `ASKWELL_FEATURES_OFF` (comma-separated). Off, Askwell
behaves as it did before the feature: the registry is built, the prompt is written and
the validator refuses exactly as then. The deploy gate (ADR-008) uses them to ship a
release with a feature that measured badly left off.

Code takes the set of features that are on, never reads the environment itself.
"""

from __future__ import annotations

# link_roles: name one of two links between the same tables.
# inferred_links: more links from column names, checked against the data.
# numeric_text: a text column that holds only numbers is a number.
FEATURES: frozenset[str] = frozenset({"link_roles", "inferred_links", "numeric_text"})
Features = frozenset[str]
ALL: Features = FEATURES


def parse_off(text: str) -> Features:
    """The features named in `text`, which must all exist."""
    names = {part.strip() for part in text.split(",") if part.strip()}
    unknown = sorted(names - FEATURES)
    if unknown:
        raise ValueError(f"unknown features {unknown}; known: {sorted(FEATURES)}")
    return frozenset(names)
