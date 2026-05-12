from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_bom_auto_model_example_declares_demo_bom_and_method() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "run_bom_auto_model.py"
    spec = spec_from_file_location("run_bom_auto_model", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.DEMO_PRODUCT_NAME == "AI demo PC bottle shell"
    assert "Polycarbonate granulate" in module.DEMO_BOM
    assert "Electricity grid mix" in module.DEMO_BOM
    assert module.IMPACT_METHOD_ID == "787c02f1-d1f2-36d6-8e06-2307cc3ebebc"
