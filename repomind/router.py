from __future__ import annotations

from .providers.base import Provider, ProviderError, complete

ROUTER_SYSTEM_PROMPT = """You are a routing classifier inside a codebase assistant. \
You will see a user's question about a codebase, along with the file names of \
the snippets retrieved for it. Decide whether the question is:

SIMPLE - a routine lookup a competent local model can answer well: \
"where is X defined", "what does this function do", "what does this error mean", \
"show me the signature of Y", straightforward factual/definitional questions.

COMPLEX - needs deeper reasoning: cross-file architectural questions, \
multi-step debugging, refactor proposals, trade-off analysis, anything \
where getting it subtly wrong would be costly.

Respond with exactly one word: SIMPLE or COMPLEX. Nothing else."""

# Used only when the local model can't be reached at all, so the app
# still does *something* sensible instead of failing outright.
_COMPLEX_HINT_WORDS = (
    "refactor", "architecture", "design", "trade-off", "tradeoff", "why does",
    "debug", "root cause", "performance", "scal", "security", "vulnerab",
    "migrate", "best practice", "should i", "compare", "rewrite",
)


def heuristic_classify(question: str) -> str:
    q = question.lower()
    if len(q) > 400 or any(w in q for w in _COMPLEX_HINT_WORDS):
        return "COMPLEX"
    return "SIMPLE"


async def classify(local_provider: Provider, question: str, snippet_files: list[str]) -> tuple[str, bool]:
    """Returns (verdict, used_local_model). verdict is "SIMPLE" or "COMPLEX".
    used_local_model is False when we had to fall back to the heuristic.
    """
    files_note = f"Snippets retrieved from: {', '.join(snippet_files[:6])}" if snippet_files else "No snippets retrieved."
    try:
        answer = await complete(
            local_provider,
            messages=[{"role": "user", "content": f"{files_note}\n\nQuestion: {question}"}],
            system=ROUTER_SYSTEM_PROMPT,
            temperature=0.0,
        )
        verdict = answer.strip().upper()
        if "COMPLEX" in verdict:
            return "COMPLEX", True
        if "SIMPLE" in verdict:
            return "SIMPLE", True
        # Unparseable response from the local model -- fall back rather than guess wrong.
        return heuristic_classify(question), False
    except ProviderError:
        return heuristic_classify(question), False
