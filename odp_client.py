import os
import sys
import json
import requests

SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"
USPTO_API_KEY = os.environ.get("USPTO_API_KEY", "rsyaucihvxwbnculpdgbigzsnqolfl")

CPC_FIELD_CANDIDATES = ["cpcClassificationBag", "cpcCodeBag", "classificationBag"]


def _dig_cpc_codes(meta: dict):
    for field in CPC_FIELD_CANDIDATES:
        value = meta.get(field)
        if value:
            codes = []
            for item in value:
                if isinstance(item, str):
                    codes.append(item)
                elif isinstance(item, dict):
                    for k in ("cpcClassificationCode", "classificationCode", "code"):
                        if k in item:
                            codes.append(item[k])
                            break
            if codes:
                return codes
    return []


def search_patents(query: str, limit: int = 50, offset: int = 0):
    if not USPTO_API_KEY:
        raise ValueError("Set USPTO_API_KEY.")
    headers = {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY}

    # If the planner already produced a fully field-qualified query string
    # (applicationMetaData.inventionTitle:"..." AND ...Utility), use it
    # exactly as-is -- no broadening fallback, since loose OR-of-words
    # matching was the actual source of irrelevant results (e.g. matching
    # on the single word "management" across unrelated patents).
    q_string = query.strip()
    if not q_string.startswith("applicationMetaData."):
        q_string = f'applicationMetaData.inventionTitle:"{q_string}"'

    response = requests.get(SEARCH_URL, params={"q": q_string, "offset": offset, "limit": limit}, headers=headers)

    if response.status_code == 404:
        return []
    if response.status_code != 200:
        raise RuntimeError(f"ODP returned HTTP {response.status_code} for '{q_string}':\n{response.text[:500]}")

    data = response.json()
    results = []
    for item in data.get("patentFileWrapperDataBag", []):
        meta = item.get("applicationMetaData", {})
        results.append({
            "application_number": item.get("applicationNumberText"),
            "title": meta.get("inventionTitle"),
            "publication_number": meta.get("earliestPublicationNumber"),
            "cpc_codes": _dig_cpc_codes(meta),
            "filing_date": meta.get("filingDate"),
        })
    return results


if __name__ == "__main__":
    query = " ".join(sys.argv[1:])
    hits = search_patents(query)
    print(f"\n{len(hits)} results for '{query}':\n")
    for r in hits:
        print(f"- {r['application_number']}: {r['title']}")
