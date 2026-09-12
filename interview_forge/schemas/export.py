import inspect
import json
from pydantic import BaseModel
from interview_forge.schemas import models
from interview_forge.corpus import models as corpus_models
from interview_forge.materials import models as material_models


def export_schemas(output):
    output.mkdir(parents=True, exist_ok=True)
    for module in (models, material_models, corpus_models):
        for name, model in inspect.getmembers(module, inspect.isclass):
            if issubclass(model, BaseModel) and model.__module__ == module.__name__ and name not in {"Model", "MaterialModel", "CapabilityClaim"}:
                (output / f"{name}.schema.json").write_text(
                    json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
