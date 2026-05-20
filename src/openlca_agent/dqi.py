from __future__ import annotations

from openlca_agent.models import BomItem, DqiScore, ProcessCandidate


def _geo_score(item: BomItem, candidate: ProcessCandidate) -> float:
    item_loc = (item.location or "").strip().upper()
    cand_loc = (candidate.location or "").strip().upper()

    if not cand_loc:
        return 20.0
    if item_loc == cand_loc:
        return 100.0
    if cand_loc == "GLO":
        return 50.0
    if cand_loc == "ROW":
        return 40.0
    return 60.0


def _tech_similarity(item: BomItem, candidate: ProcessCandidate) -> float:
    from openlca_agent.mapping import _similarity

    query = " ".join(p for p in [item.material, item.name] if p)
    base = _similarity(query, candidate.name) * 100.0
    mat_lower = (item.material or "").lower()
    cat_lower = (candidate.category or "").lower()
    if mat_lower and mat_lower in cat_lower:
        base = min(100.0, base + 10.0)
    return base


def _completeness(candidate: ProcessCandidate) -> float:
    score = 0.0
    if candidate.name:
        score += 25.0
    if candidate.id:
        score += 25.0
    if candidate.category:
        score += 25.0
    if candidate.location:
        score += 25.0
    return score


def compute_dqi(item: BomItem, candidate: ProcessCandidate) -> DqiScore:
    geo = _geo_score(item, candidate)
    tech = _tech_similarity(item, candidate)
    temp = 50.0
    comp = _completeness(candidate)
    overall = geo * 0.35 + tech * 0.35 + temp * 0.15 + comp * 0.15

    if overall >= 80:
        band = "high"
    elif overall >= 50:
        band = "medium"
    else:
        band = "low"

    flags: list[str] = []
    if geo < 50:
        flags.append(f"low geographical representativeness (score={geo:.0f})")
    if tech < 50:
        flags.append(f"low technological representativeness (score={tech:.0f})")
    flags.append("temporal representativeness could not be assessed (default score=50)")
    if comp < 75:
        flags.append(f"incomplete process metadata (score={comp:.0f}/100)")

    return DqiScore(
        overall=round(overall, 1),
        geographical=round(geo, 1),
        technological=round(tech, 1),
        temporal=round(temp, 1),
        completeness=round(comp, 1),
        confidence_band=band,
        flags=flags,
    )
