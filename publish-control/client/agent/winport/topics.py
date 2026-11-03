"""Topic input normalisation shared by the panel and the publish chain.

Customers type topics in many ways: with or without a leading ``#``, separated
by spaces or commas.  The publish plan and the approval fingerprint only ever
see one canonical form: ``["#a", "#b"]``.  Empty input is valid and means "do
not fill a topic".
"""

from __future__ import annotations

import re

MAX_INPUT_CHARS = 2000
MAX_TOPICS = 50
MAX_TOPIC_CHARS = 100

#: spaces (including the ideographic space), commas and semicolons
_SEPARATORS = re.compile(r"[\s,\u3001\uFF0C;\uFF1B]+")


def normalize_topics(value) -> list[str]:
    """Return a de-duplicated ``["#topic", ...]`` list, preserving order.

    ``value`` may be a string (ASCII or full-width commas/semicolons, spaces)
    or an already split sequence.  Leading ``#`` characters are removed before
    one canonical ``#`` is added back, so ``##a`` and ``#a`` both become
    ``#a``.  Blank and ``#``-only fragments are dropped.
    """
    if value is None:
        return []
    if isinstance(value, str):
        raw_parts = [value]
    elif isinstance(value, (list, tuple)):
        raw_parts = list(value)
    else:
        raise ValueError("topics must be text or a list of text")

    total = 0
    topics: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        if not isinstance(part, str):
            raise ValueError("each topic must be text")
        total += len(part)
        if total > MAX_INPUT_CHARS:
            raise ValueError("topics input is too long")
        for token in _SEPARATORS.split(part):
            token = token.strip().lstrip("#").strip()
            if not token:
                continue
            if len(token) > MAX_TOPIC_CHARS:
                raise ValueError("one topic is too long")
            topic = "#" + token
            if topic in seen:
                continue
            seen.add(topic)
            topics.append(topic)
            if len(topics) > MAX_TOPICS:
                raise ValueError("too many topics")
    return topics


def format_topics(value) -> str:
    """Customer-facing one-line form: ``#a #b`` (empty input -> ``""``)."""
    return " ".join(normalize_topics(value))
