%%writefile llm_scorer.py
import json
import re
from difflib import SequenceMatcher
import requests

OLLAMA_API_URL = "http://localhost:11434/api/generate"


def call_ollama(prompt: str, model: str = "llama3.1") -> str:
    response = requests.post(OLLAMA_API_URL, json={"model": model, "prompt": prompt, "stream": False})
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _extract_json_array(text: str):
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
    start, end = text.find("["), text.rfind("]")
    sliced = text[start:end + 1] if (start != -1 and end != -1 and end > start) else text
    result = try_parse(sliced)
    if result is not None:
        return result
    return try_parse(re.sub(r"[\r\n]+", " ", sliced))


def _title_matches(claimed, actual):
    if not claimed or not actual:
        return False
    claimed, actual = claimed.lower().strip(), actual.lower().strip()
    if claimed in actual or actual in claimed:
        return True
    return SequenceMatcher(None, claimed, actual).ratio() > 0.5


def score_batch(invention_description: str, records: list, model: str = "llama3.1", max_retries: int = 2):
    if not records:
        return records
    numbered_list = "\n".join(f'{i}. Title: "{r["title"]}" | CPC: {r.get("cpc_codes") or "none"}' for i, r in enumerate(records))
    base_prompt = f"""You are scoring patent search results for relevance to an invention.

Invention description:
\"\"\"{invention_description}\"\"\"

Candidates (numbered):
{numbered_list}

For EVERY candidate, output a relevance score (0-10) and a one-sentence justification.
Also echo the first few words of that candidate's actual title, to confirm you're scoring the right item.

Respond with ONLY a valid JSON array:
[{{"id": 0, "title_snippet": "...", "score": 7, "justification": "..."}}]

Include one entry for every id from 0 to {len(records) - 1}. JSON array:"""
    prompt = base_prompt
    parsed, raw = None, ""
    for attempt in range(max_retries + 1):
        raw = call_ollama(prompt, model=model)
        parsed = _extract_json_array(raw)
        if parsed is not None:
            break
        prompt = base_prompt + "\n\nIMPORTANT: output ONLY the raw JSON array."

    score_map = {}
    if parsed:
        for entry in parsed:
            try:
                idx = int(entry["id"])
                if idx < 0 or idx >= len(records):
                    continue
                if not _title_matches(entry.get("title_snippet", ""), records[idx]["title"]):
                    continue
                score_map[idx] = (int(entry.get("score", 0)), entry.get("justification", ""))
            except (KeyError, ValueError, TypeError):
                continue

    for i, r in enumerate(records):
        score, justification = score_map.get(i, (0, "LLM did not return a verifiable score for this item."))
        r["score"] = score
        r["justification"] = justification
    return records
