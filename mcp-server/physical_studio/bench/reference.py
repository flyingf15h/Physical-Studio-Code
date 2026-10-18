# Reference pictures for photo checks on CAD (hardware) builds: export writes step-01.png, step-02.png, ...
# next to design.steps.json (the build after each step, new parts highlighted) and names it in each step's
# `picture`. A photo check sends the AI that picture beside the builder's photos, so it can say exactly
# which part sits wrong instead of guessing from the step text.
import json
from pathlib import Path

from PIL import Image

NOTE = ("The LAST image is a CAD render of what this step should look like, its new parts highlighted. Real parts "
        "look different (colours, labels, cables), but positions and which way each part faces must match it.")


def reference_images(folder: Path, step_index: int) -> list[Image.Image]:
    """The reference render for step `step_index` (0-based) of the design exported to `folder`, or [] when
    the design has none (older exports, or a missing file)."""
    try:
        doc = json.loads((Path(folder) / "design.steps.json").read_text())
        name = doc["steps"][step_index].get("picture")
        if not name or "/" in name or "\\" in name:
            return []
        with Image.open(Path(folder) / name) as im:
            return [im.convert("RGB")]
    except (OSError, ValueError, KeyError, IndexError):
        return []
