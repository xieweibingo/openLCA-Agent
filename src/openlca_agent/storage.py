from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from openlca_agent.models import CalculationRun, ProductModel, to_plain

T = TypeVar("T", bound=BaseModel)


class RunStore:
    def __init__(self, output_root: str | Path = "outputs") -> None:
        self.output_root = Path(output_root)

    def save_run(self, run: CalculationRun) -> None:
        self._write_json(self.run_path(run.run_id), run)

    def load_run(self, run_id: str) -> CalculationRun:
        return self._read_model(self.run_path(run_id), CalculationRun)

    def save_product_model(self, run_id: str, model: ProductModel) -> None:
        self._write_json(self.output_root / run_id / "product_model.json", model)

    def load_product_model(self, run_id: str) -> ProductModel | None:
        path = self.output_root / run_id / "product_model.json"
        if not path.exists():
            return None
        return self._read_model(path, ProductModel)

    def run_path(self, run_id: str) -> Path:
        return self.output_root / run_id / "run.json"

    def run_dir(self, run_id: str) -> Path:
        path = self.output_root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_plain(value), ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_model(self, path: Path, model_type: type[T]) -> T:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model_type.model_validate(data)
