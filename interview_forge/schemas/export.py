import inspect
import json
from interview_forge.schemas import models


def export_schemas(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, model in inspect.getmembers(models, inspect.isclass):
        if issubclass(model, models.Model) and model is not models.Model:
            (output / f"{name}.schema.json").write_text(
                json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
