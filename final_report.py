import json
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone
from llm_client import call_llm


def _extract_json_array(text):
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


def score_with_abstracts(invention_description, patents, model=None, max_retries=2):
    numbered_list = "\n".join(
        f'{i}. Title: "{p.get("title") or p.get("odp_title")}"\n   Abstract: "{p.get("abstract")}"'
        for i, p in enumerate(patents)
    )

    prompt = f"""You are scoring patents for relevance to an invention, using their full abstracts.

Invention description:
'''{invention_description}'''

Scoring rubric:
- 0-2: Unrelated field entirely
- 3-5: Same broad domain but different mechanism or purpose
- 6-8: Same specific problem area, real technical overlap, but not a close match
- 9-10: Same core mechanism/purpose as the invention description

Candidates:
{numbered_list}

For EVERY candidate, output a relevance score (0-10) and a 1-2 sentence justification
based on the ABSTRACT content, not just the title. Echo the first few words of the title
to confirm you're scoring the right item.

Respond with ONLY a valid JSON array:
[{{"id": 0, "title_snippet": "...", "score": 8, "justification": "..."}}]

Include one entry for every id from 0 to {len(patents) - 1}. JSON array:"""

    parsed, raw = None, ""
    for attempt in range(max_retries + 1):
        kwargs = {"model": model} if model else {}
        raw = call_llm(prompt, **kwargs)
        parsed = _extract_json_array(raw)
        if parsed is not None:
            break
        prompt += "\n\nIMPORTANT: output ONLY the raw JSON array."

    score_map = {}
    if parsed:
        for entry in parsed:
            try:
                idx = int(entry["id"])
                if idx < 0 or idx >= len(patents):
                    continue
                actual_title = patents[idx].get("title") or patents[idx].get("odp_title")
                if not _title_matches(entry.get("title_snippet", ""), actual_title):
                    continue
                score_map[idx] = (int(entry.get("score", 0)), entry.get("justification", ""))
            except (KeyError, ValueError, TypeError):
                continue

    for i, p in enumerate(patents):
        score, justification = score_map.get(i, (0, "LLM did not return a verifiable score for this item."))
        p["abstract_score"] = score
        p["abstract_justification"] = justification

    return patents


def generate_report(invention_description, ranked_patents, log_path="log.json", min_score=5, output_path="report.md"):
    try:
        with open(log_path) as f:
            log = json.load(f)
        queries_used = [q["query"] for q in log.get("queries", [])]
        replans = log.get("replans", [])
    except FileNotFoundError:
        queries_used = []
        replans = []

    relevant = [p for p in ranked_patents if p.get("abstract_score", 0) >= min_score]
    top = relevant[:10]

    lines = []
    lines.append("# Prior-Art Research Report\n")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    lines.append(f"**Invention Description:**\n> {invention_description}\n")

    lines.append("## Search Strategy\n")
    if queries_used:
        lines.append("The following ODP search queries were used:\n")
        for q in queries_used:
            lines.append(f"- `{q}`")
    lines.append("")

    if replans:
        lines.append("## Adaptations (Replans)\n")
        lines.append("The agent revised its strategy mid-run when a query underperformed:\n")
        for r in replans:
            lines.append(f"- **Original query:** `{r.get('original_query')}`")
            lines.append(f"  - **Reason for replan:** {r.get('reason')}")
            lines.append(f"  - **Replacement query:** `{r.get('replacement_query')}`")
            hit_count = r.get('replacement_hit_count')
            if hit_count is not None:
                lines.append(f"  - **Replacement result:** {hit_count} candidates found")
        lines.append("")

    lines.append(f"## Top {len(top)} Relevant Prior Art\n")
    if not top:
        lines.append("*No candidates met the minimum relevance threshold.*\n")
    for i, p in enumerate(top, 1):
        title = p.get("title") or p.get("odp_title") or "Unknown title"
        score = p.get("abstract_score", "N/A")
        justification = p.get("abstract_justification", "")
        url = p.get("url", "")
        patent_id = p.get("patent_id", "")

        lines.append(f"### {i}. {title}")
        lines.append(f"**Patent ID:** {patent_id}  ")
        lines.append(f"**Relevance Score:** {score}/10  ")
        lines.append(f"**URL:** {url}\n")
        lines.append(f"**Why it matters:** {justification}\n")

    excluded_count = len(ranked_patents) - len(relevant)
    if excluded_count:
        lines.append(f"\n*{excluded_count} additional candidate(s) were scored but excluded from this report for scoring below {min_score}/10 relevance.*")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Report written to {output_path}")
