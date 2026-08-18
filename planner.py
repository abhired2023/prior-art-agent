import json
import re
import sys
from llm_client import call_llm


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


def get_plan(invention_description: str, model: str = None, max_retries: int = 3) -> dict:
    base_prompt = f"""You are a patent researcher. Given an invention description, produce search queries for the USPTO Open Data Portal API.

IMPORTANT: Queries must use this exact field-qualified format:
  applicationMetaData.inventionTitle:"your phrase here"

Rules:
- The phrase goes inside double quotes after the colon
- Always append: AND applicationMetaData.applicationTypeLabelName:Utility
- Use exactly 2 words per phrase
- Each phrase must combine TWO DIFFERENT concepts from the invention (e.g. "wearable glucose", not just "glucose")
- Produce 5 queries covering different combinations of concepts

Example output for "a solar-powered water purification device":
{{
  "concepts": ["solar water purification", "photovoltaic desalination", "UV water treatment"],
  "queries": [
    "applicationMetaData.inventionTitle:\\"solar water\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"water purification\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"solar purification\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"photovoltaic water\\" AND applicationMetaData.applicationTypeLabelName:Utility",
    "applicationMetaData.inventionTitle:\\"UV purification\\" AND applicationMetaData.applicationTypeLabelName:Utility"
  ],
  "cpc_codes": ["C02F1/30", "C02F1/32"]
}}

Invention: "{invention_description}"

Respond with ONLY valid JSON, no other text."""

    strict_suffix = "\n\nYour queries MUST combine two different concepts per 2-word phrase, not a single generic term. Start with applicationMetaData.inventionTitle."

    prompt = base_prompt
    raw = ""
    for attempt in range(max_retries + 1):
        kwargs = {"model": model} if model else {}
        raw = call_llm(prompt, **kwargs)
        parsed = _extract_json_block(raw)
        if parsed is not None and all(k in parsed for k in ("concepts", "queries", "cpc_codes")):
            queries_ok = all(q.strip().startswith("applicationMetaData.inventionTitle") for q in parsed["queries"])
            if queries_ok:
                return parsed
        prompt = base_prompt + strict_suffix
    raise ValueError(f"Model did not return valid field-qualified queries after {max_retries + 1} attempts.\nRaw:\n{raw}")


def get_replan_query(invention_description: str, failed_query: str, reason: str, model: str = None, max_retries: int = 2) -> str:
    prompt = f"""You are a patent researcher revising a failed search strategy.

Invention description:
'''{invention_description}'''

This query FAILED: {failed_query}
Reason it failed: {reason}

Produce ONE replacement query combining TWO DIFFERENT concepts from the invention
in a 2-word phrase (not a single generic term). Use this exact format:
  applicationMetaData.inventionTitle:"your phrase here" AND applicationMetaData.applicationTypeLabelName:Utility

Respond with ONLY the query string, no JSON, no explanation."""

    for attempt in range(max_retries + 1):
        kwargs = {"model": model} if model else {}
        raw = call_llm(prompt, **kwargs).strip()
        raw = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw)
        if raw.startswith("applicationMetaData.inventionTitle"):
            return raw
        prompt += "\n\nIMPORTANT: respond with ONLY the raw query string starting with applicationMetaData.inventionTitle."

    return None


if __name__ == "__main__":
    invention = " ".join(sys.argv[1:])
    plan = get_plan(invention)
    print(json.dumps(plan, indent=2))
