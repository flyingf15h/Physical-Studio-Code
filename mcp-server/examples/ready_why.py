"""Writes the one-line "why" for every step of the ready-made guides that don't have one yet (one OpenAI call
per guide). New guides get theirs from the planner or the CAD designer.

    set -a && . ../../.physical-studio-secrets.env && set +a && uv run python examples/ready_why.py
"""

import json
import os
from pathlib import Path

import openai

READY = Path(__file__).resolve().parent.parent / "physical_studio" / "bench" / "ready"
MODEL = os.environ.get("OPENAI_STUDIO_MODEL", "gpt-6.1-sol")
client = openai.OpenAI()

for path in sorted(READY.glob("*/build.json")):
    data = json.loads(path.read_text())
    steps = data["plan"]["steps"]
    if all(s.get("why") for s in steps):
        continue
    listing = "\n".join(f"{s['number']}. {s['title']}: {s['instruction'][:400]}" for s in steps)
    prompt = (f"Project: {data['plan']['title']}. {data['plan']['summary']}\n\nAssembly steps:\n{listing}\n\n"
              "For each step write one short line (at most 20 words, plain words, no jargon) on what the step is for "
              "in the finished project, like an IKEA manual's caption: e.g. 'This LED is the red light; the resistor "
              "stops it burning out.' Don't repeat the instruction. Reply with JSON: {\"why\": [one string per step, in order]}.")
    reply = client.responses.create(model=MODEL, input=prompt, text={"format": {"type": "json_object"}})
    why = json.loads(reply.output_text)["why"]
    assert len(why) == len(steps), (path.parent.name, len(why), len(steps))
    for s, w in zip(steps, why):
        s["why"] = w.strip()
    for s, w in zip((data.get("internal") or {}).get("plan", {}).get("steps", []), why):
        s["why"] = w.strip()
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(path.parent.name, "->", why[0])
