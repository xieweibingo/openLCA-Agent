from __future__ import annotations

from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback for stripped deployments.
    fuzz = None

from openlca_agent.models import BomItem, MappingDecision, ProcessCandidate

CONFIDENCE_THRESHOLD = 0.70
GEOGRAPHY_PRIORITY = {"CN": 0.08, "GLO": 0.05, "RoW": 0.03, "RER": 0.02}

# Semantic expansion pairs: expanded terms are added as extra search queries,
# covering common synonyms, abbreviations, and LCA process naming variants.
_TERM_EXPANSIONS: dict[str, list[str]] = {
    "hdpe": ["high density polyethylene", "polyethylene high density"],
    "ldpe": ["low density polyethylene", "polyethylene low density"],
    "pp": ["polypropylene"],
    "pet": ["polyethylene terephthalate", "polyester"],
    "ps": ["polystyrene"],
    "eps": ["expanded polystyrene"],
    "pu": ["polyurethane"],
    "pvc": ["polyvinyl chloride"],
    "abs": ["acrylonitrile butadiene styrene"],
    "pa": ["polyamide", "nylon"],
    "pc": ["polycarbonate"],
    "pmma": ["acrylic", "acrylic glass"],
    "pe": ["polyethylene"],
    "hips": ["high impact polystyrene"],
    "sbr": ["styrene butadiene rubber"],
    "epdm": ["ethylene propylene diene monomer"],
    "co2": ["carbon dioxide"],
    "ch4": ["methane"],
    "n2o": ["nitrous oxide"],
    "sf6": ["sulphur hexafluoride"],
    "steel": ["steel", "low alloyed steel", "steel hot rolling"],
    "stainless": ["stainless steel", "chromium steel"],
    "aluminium": ["aluminum", "aluminium ingot", "wrought aluminium"],
    "aluminum": ["aluminium", "aluminium ingot", "wrought aluminium"],
    "cardboard": ["paperboard", "containerboard", "corrugated board"],
    "paper": ["kraft paper", "graphic paper", "paper waste"],
    "glass": ["flat glass", "container glass", "borosilicate glass"],
    "copper": ["copper cathode", "wrought copper"],
    "concrete": ["cext%", "concrete block", "cement mortar"],
    "wood": ["timber", "softwood", "hardwood", "plywood"],
    "cotton": ["cotton fibre", "cotton fabric"],
}


def search_strategies(item: BomItem) -> list[str]:
    """Generate multiple search queries from a BOM item.

    Returns a priority-ordered list of search terms, from most specific to
    most general, to maximize the chance of finding relevant openLCA processes.
    """
    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> None:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)

    material = (item.material or "").strip()
    name = (item.name or "").strip()
    supplier = (item.supplier or "").strip()

    # 1. material + name (most specific)
    if material and name and material.lower() != name.lower():
        _add(f"{material} {name}")

    # 2. material alone
    if material:
        _add(material)

    # 3. name alone
    if name and name.lower() != (material or "").lower():
        _add(name)

    # 4. supplier
    if supplier:
        _add(supplier)

    # 5. expanded terms from material
    if material:
        for expansion in expand_query(material):
            _add(expansion)

    # 6. sub-terms (e.g., "HDPE granulate" → "HDPE", "granulate")
    if material and " " in material:
        for part in material.split():
            part = part.strip()
            if len(part) > 2:
                _add(part)
                for expansion in expand_query(part):
                    _add(expansion)

    return queries[:8]


def expand_query(query: str) -> list[str]:
    """Expand a single query into alternative search terms using a
    lightweight synonym dictionary. Returns terms the caller can use as
    additional search queries to broaden coverage.
    """
    key = query.strip().lower()
    if key in _TERM_EXPANSIONS:
        return _TERM_EXPANSIONS[key]
    return []


def map_bom_item_to_processes(
    item: BomItem,
    candidates: list[ProcessCandidate],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> MappingDecision:
    scored = [_score_candidate(item, candidate) for candidate in candidates]
    scored.sort(
        key=lambda candidate: (
            candidate.score,
            _location_rank(item.location, candidate.location),
        ),
        reverse=True,
    )
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


def _location_rank(item_location: str | None, candidate_location: str | None) -> float:
    if not candidate_location:
        return 0.0
    if item_location and item_location.lower() == candidate_location.lower():
        return 1.0
    return GEOGRAPHY_PRIORITY.get(candidate_location, 0.0)
