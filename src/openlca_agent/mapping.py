from __future__ import annotations

from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback for stripped deployments.
    fuzz = None

from openlca_agent.models import BomItem, MappingDecision, ProcessCandidate

CONFIDENCE_THRESHOLD = 0.70
GEOGRAPHY_PRIORITY = {"CN": 0.08, "GLO": 0.05, "RoW": 0.03, "RER": 0.02}


def map_bom_item_to_processes(
    item: BomItem,
    candidates: list[ProcessCandidate],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> MappingDecision:
    scored = [_score_candidate(item, candidate) for candidate in candidates]
    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    best = scored[0] if scored else None
    if best is None or best.score < threshold:
        return MappingDecision(
            item=item,
            candidates=scored,
            confidence=best.score if best else 0.0,
            reason="No candidate exceeded the confidence threshold.",
            unresolved_reason=f"No process candidate reached confidence {threshold:.2f}.",
        )

    reason = best.reason or "Selected by material/name similarity."
    return MappingDecision(
        item=item,
        candidates=scored,
        selected_candidate=best,
        confidence=best.score,
        reason=reason,
    )


def _score_candidate(item: BomItem, candidate: ProcessCandidate) -> ProcessCandidate:
    query = " ".join(part for part in [item.material, item.name] if part)
    similarity = _similarity(query, candidate.name)
    geography_bonus = _geography_bonus(item.location, candidate.location)
    category_bonus = 0.02 if item.material.lower() in (candidate.category or "").lower() else 0.0
    score = min(1.0, similarity + geography_bonus + category_bonus)

    reason_parts = [f"name similarity {similarity:.2f}"]
    if geography_bonus:
        reason_parts.append(f"geography bonus {geography_bonus:.2f}")
    if category_bonus:
        reason_parts.append("category/material hint")

    return candidate.model_copy(
        update={
            "score": round(score, 4),
            "reason": "; ".join(reason_parts),
        }
    )


def _similarity(left: str, right: str) -> float:
    left = left.lower()
    right = right.lower()
    if fuzz is not None:
        return fuzz.token_set_ratio(left, right) / 100.0
    return SequenceMatcher(a=left, b=right).ratio()


def _geography_bonus(item_location: str | None, candidate_location: str | None) -> float:
    if not candidate_location:
        return 0.0
    if item_location and item_location.lower() == candidate_location.lower():
        return GEOGRAPHY_PRIORITY.get(candidate_location, 0.06)
    return GEOGRAPHY_PRIORITY.get(candidate_location, 0.0) / 2
