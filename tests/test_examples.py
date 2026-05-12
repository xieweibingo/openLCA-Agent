from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_elcd_bottles_example_uses_known_demo_ids() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "run_elcd_bottles.py"
    spec = spec_from_file_location("run_elcd_bottles", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PRODUCT_SYSTEM_ID == "0fff6db0-464b-44f3-81af-381d88e7a1c3"
    assert module.IMPACT_METHOD_ID == "787c02f1-d1f2-36d6-8e06-2307cc3ebebc"
