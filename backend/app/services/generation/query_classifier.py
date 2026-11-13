"""
Keyword-based query classifier — zero LLM calls, zero quota cost.

Logic:
  - Default: 'document' (search docs — safe for a RAG system)
  - 'conversational' only when the WHOLE message is small talk / meta. A
    greeting attached to a real question ("Hi, what is the JLG loan limit?")
    must still retrieve; matching a greeting anywhere in the message used to
    route such questions to an ungrounded conversational answer.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from loguru import logger

from app.core.rag_trace import hash_value


# Phrases that are pure small talk. They are stripped from the message; if
# nothing substantive remains, the message is conversational.
_SMALL_TALK_RE = re.compile(
    r"""
    \b(who|what)\s+are\s+you\b                              |
    \byour\s+(name|purpose|capabilit\w+|features?|function)\b |
    \bwhat\s+can\s+you\s+(do|help\s+(me\s+)?with)\b         |
    \bhow\s+(do\s+you|can\s+you)\s+(work|help|assist)(\s+me)?\b |
    \btell\s+me\s+about\s+yourself\b                        |
    \bintroduce\s+yourself\b                                |
    \bwhat\s+is\s+novera\b                                  |
    \b(hello|hi|hiya|hey|howdy|greetings?)(\s+there)?\b     |
    \bgood\s+(morning|afternoon|evening|day)\b              |
    \b(thanks?(\s+you)?|thank\s+you(\s+so\s+much)?|cheers|appreciate(\s+it)?)\b |
    \b(bye|goodbye|see\s+you|talk\s+later)\b                |
    \bhow\s+are\s+you(\s+doing)?\b                          |
    \bwhat[' ]?s\s+up\b                                     |
    \b(ok|okay|sure|great|cool|nice|got\s+it|yes|no|yep|nope|alright)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Words that carry no retrieval intent once small talk is removed.
_FILLER = {
    "a", "an", "the", "and", "so", "very", "much", "please", "again", "today",
    "for", "that", "this", "me", "you", "it", "all", "well", "oh", "um", "there",
    "can", "could", "would", "will", "i", "we", "novera", "assistant", "bot",
}


def _residual_terms(query: str) -> list[str]:
    stripped = _SMALL_TALK_RE.sub(" ", query)
    words = re.findall(r"[A-Za-z0-9₹$%]+", stripped.lower())
    return [word for word in words if word not in _FILLER]


class QueryClassifier:
    """
    Instant keyword-based intent classifier.

    Latency  : ~0 ms  (no I/O)
    API cost : $0     (no LLM calls)
    When in doubt it searches documents: an unnecessary search costs latency,
    a skipped search produces an ungrounded answer.
    """

    async def classify_query(
        self,
        query: str,
        conversation_history: Optional[list] = None,
    ) -> dict[str, Any]:
        q = query.strip()
        residual = _residual_terms(q)

        if not residual:
            result = {
                "type": "conversational",
                "reasoning": "Message is only greeting / small talk / meta",
                "confidence": "high",
                "cached": True,
            }
        else:
            result = {
                "type": "document",
                "reasoning": "Substantive content: search documents",
                "confidence": "high",
                "cached": True,
            }

        # Never log raw query text: it may contain HR/Finance details.
        logger.info(
            f"Classification: {result['type'].upper()} "
            f"| query_hash={hash_value(q)} | confidence={result['confidence']}"
        )
        return result


# Singleton used throughout the app
query_classifier = QueryClassifier()

__all__ = ["QueryClassifier", "query_classifier"]
