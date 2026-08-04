import json
import re
import sys
import requests

OLLAMA_API_URL = "http://localhost:11434/api/generate"


def call_ollama(prompt: str, model: str = "llama3.1", temperature: float = 0.2) -> str:
    response = requests.post(OLLAMA_API_URL, json={
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature}
    })
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


def get_plan(invention_description: str, model: str = "llama3.1", max_retries: int = 3) -> dict:
    base_prompt = f"""You are a patent researcher. Given an invention description, produce search queries for the USPTO Open Data Portal API.

IMPORTANT: Queries must use this exact field-qualified format:
  applicationMetaData.inventionTitle:"your phrase here"

Rules:
- The phrase goes inside double quotes after the colon
- Always append: AND applicationMetaData.applicationTypeLabelName:Utility
- Use exactly 2 words per phrase, common patent-title terminology (e.g. "glucose monitoring", "wearable sensor") rather than specific/uncommon 3-4 word phrases, since shorter common phrases are more likely to literally appear in real patent titles
- Produce 3 queries covering different technical angles of the invention

Example output for "a solar-powered water purification device":
{{
  "concepts": ["solar water purification", "photovoltaic desalination", "UV water treatment"],
  "queries": [
    "applicationMetaData.inventionTitle:\\"solar water\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"water purification\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"water treatment\\" AND applicationMetaData.applicationTypeLabelName:Utility"
  ],
  "cpc_codes": ["C02F1/30", "C02F1/32"]
}}

Invention: "{invention_description}"

Respond with ONLY valid JSON, no other text."""

    strict_suffix = "\n\nYour queries MUST start with applicationMetaData.inventionTitle and contain quoted 2-word phrases. Do not write plain English sentences or phrases longer than 2 words."

    prompt = base_prompt
    raw = ""
    for attempt in range(max_retries + 1):
        raw = call_ollama(prompt, model=model)
        parsed = _extract_json_block(raw)
        if parsed is not None and all(k in parsed for k in ("concepts", "queries", "cpc_codes")):
            queries_ok = all(q.strip().startswith("applicationMetaData.inventionTitle") for q in parsed["queries"])
            if queries_ok:
                return parsed
            print(f"  NOTE: attempt {attempt+1} returned plain-English queries, retrying with stricter instruction.")
        prompt = base_prompt + strict_suffix
    raise ValueError(f"Model did not return valid field-qualified queries after {max_retries + 1} attempts.\nRaw:\n{raw}")


if __name__ == "__main__":
    invention = " ".join(sys.argv[1:])
    plan = get_plan(invention)
    print(json.dumps(plan, indent=2))
