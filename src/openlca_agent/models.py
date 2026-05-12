from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BomItem(AgentModel):
    name: str
    material: str
    quantity: float
    unit: str
    supplier: str | None = None
    location: str | None = None
    notes: str | None = None

    @field_validator("name", "material", "unit")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("quantity")
    @classmethod
    def require_positive_quantity(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value


class Descriptor(AgentModel):
    id: str
    name: str
    category: str | None = None
    location: str | None = None
    model_type: str | None = None


class ProcessCandidate(Descriptor):
    score: float = 0.0
    reason: str | None = None


class MappingDecision(AgentModel):
    item: BomItem
    candidates: list[ProcessCandidate] = Field(default_factory=list)
    selected_candidate: ProcessCandidate | None = None
    confidence: float = 0.0
    reason: str = ""
    unresolved_reason: str | None = None


class ProductModel(AgentModel):
    product_name: str
    functional_unit: str = "1 piece"
    items: list[BomItem] = Field(default_factory=list)
    mapping_decisions: list[MappingDecision] = Field(default_factory=list)
    unresolved_items: list[BomItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)


class ImpactResult(AgentModel):
    impact_category: str
    value: float
    unit: str | None = None


class Hotspot(AgentModel):
    name: str
    value: float
    unit: str | None = None
    contribution: float | None = None
    dimension: str = "process"


class CalculationRun(AgentModel):
    run_id: str
    product_system: dict[str, Any]
    impact_method: dict[str, Any]
    total_impacts: list[ImpactResult] = Field(default_factory=list)
    hotspots: list[Hotspot] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    product_model: ProductModel | None = None
    run_handle: str | None = None

    def output_dir(self, output_root: Path) -> Path:
        return output_root / self.run_id


class ComplianceReport(AgentModel):
    summary: str
    method_version: str | None = None
    data_sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    impact_results: list[ImpactResult] = Field(default_factory=list)
    hotspots: list[Hotspot] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    pcf_epd_cbam_dpp_notes: dict[str, str] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)


def to_plain(model: BaseModel | dict[str, Any] | list[Any] | Any) -> Any:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json")
    if isinstance(model, dict):
        return {key: to_plain(value) for key, value in model.items()}
    if isinstance(model, list):
        return [to_plain(value) for value in model]
    return model
