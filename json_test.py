"""
json_test.py

Purpose: This model aims to reliably produce structured JSON output for an arbitrary 
    invention description from a local LLM. This script represents the "planner" block
    of an agentic system: extracting key concepts, generating search queries, and
    proposing CPC codes. 

import json
import subprocess
import sys

def call_ollama(prompt: str, model: str = "llama3.1"):
    """
    Calls Ollama via subprocess and returns raw text.
    """
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        capture_output=True
    )
    return result.stdout.strip()

def get_structured_json(invention_description: str):
    """
    Request structured LLM based on the invention description
    """
    prompt = f"""
You are a JSON-only model.

Given the following invention description:
\"\"\"{invention_description}\"\"\"

Extract:
- "concepts": the key technical ideas involved
- "queries": 3–5 search queries that should be used to find similar prior art
- "cpc_codes":  CPC classification codes related to the invention

Respond with JSON
"""

    raw = call_ollama(prompt)
    print("Raw model output:\n", raw)

    try:
        data = json.loads(raw)
        print("\nParsed JSON:\n", json.dumps(data, indent=2))
    except json.JSONDecodeError:
        print("\nERROR: Model did not return valid JSON.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 json_test.py \"user invention description\"")
        sys.exit(1)

    invention = " ".join(sys.argv[1:])
    get_structured_json(invention)

