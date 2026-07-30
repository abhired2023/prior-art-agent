
import json
import re
import sys
import requests

OLLAMA_API_URL = "http://localhost:11434/api/generate"


def call_ollama(prompt: str, model: str = "llama3.1") -> str:
    response = requests.post(OLLAMA_API_URL, json={"model": model, "prompt": prompt, "stream": False})
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _extract_json_block(text: str):
    text = text.strip()
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()

    def try_parse(c):
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            return None

    result = try_parse(text)
    if result is not None:
        return result
    start, end = text.find("{"), text.rfind("}")
    sliced = text[start:end + 1] if (start != -1 and end != -1 and end > start) else text
    result = try_parse(sliced)
    if result is not None:
        return result
    return try_parse(re.sub(r"[\r\n]+", " ", sliced))


def get_plan(invention_description: str, model: str = "llama3.1", max_retries: int = 2) -> dict:
    base_prompt = f"""You are a JSON-only model. Respond with ONLY a single valid JSON object, no explanation or markdown.

Given the following invention description:
\"\"\"{invention_description}\"\"\"

Return a JSON object with exactly these keys:
- "concepts": array of strings
- "queries": array of 3-5 strings, search queries to find similar prior art
- "cpc_codes": array of strings, candidate CPC codes (e.g. "A61B5/145")

JSON:"""
    prompt = base_prompt
    raw = ""
    for attempt in range(max_retries + 1):
        raw = call_ollama(prompt, model=model)
        parsed = _extract_json_block(raw)
        if parsed is not None and all(k in parsed for k in ("concepts", "queries", "cpc_codes")):
            return parsed
        prompt = base_prompt + "\n\nIMPORTANT: previous response was not valid JSON. Output raw JSON only."
    raise ValueError(f"Model did not return valid JSON after {max_retries + 1} attempts.\nRaw:\n{raw}\nRepr:\n{raw!r}")


if __name__ == "__main__":
    invention = " ".join(sys.argv[1:])
    plan = get_plan(invention)
    print(json.dumps(plan, indent=2))
