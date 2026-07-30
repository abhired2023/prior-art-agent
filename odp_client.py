%%writefile odp_client.py
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


def _build_query_string(query: str, broad: bool = False) -> str:
    query = query.strip().strip('"').strip("'").strip()
    if not broad:
        return f'applicationMetaData.inventionTitle:"{query}"'
    stopwords = {"a", "an", "the", "for", "of", "in", "on", "and", "or", "to", "with"}
    terms = [w for w in query.split() if w.lower() not in stopwords]
    if not terms:
        terms = query.split()
    return f'applicationMetaData.inventionTitle:({" OR ".join(terms)})'


def search_patents(query: str, limit: int = 50, offset: int = 0):
    if not USPTO_API_KEY:
        raise ValueError("Set USPTO_API_KEY.")
    headers = {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY}

    def do_request(q_string):
        params = {"q": q_string, "offset": offset, "limit": limit}
        return requests.get(SEARCH_URL, params=params, headers=headers)

    used_broad = False
    response = do_request(_build_query_string(query, broad=False))
    if response.status_code == 404:
        used_broad = True
        response = do_request(_build_query_string(query, broad=True))
    if response.status_code == 404:
        return []
    if response.status_code != 200:
        raise RuntimeError(f"ODP returned HTTP {response.status_code} for '{query}':\n{response.text[:500]}")

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
            "matched_broad": used_broad,
        })
    return results


def inspect_raw(query: str, limit: int = 1):
    headers = {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY}
    response = requests.get(SEARCH_URL, params={"q": _build_query_string(query), "offset": 0, "limit": limit}, headers=headers)
    print(f"HTTP {response.status_code}")
    data = response.json()
    bag = data.get("patentFileWrapperDataBag", [])
    print(json.dumps(bag[0], indent=2) if bag else json.dumps(data, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    if "--inspect" in sys.argv:
        inspect_raw(" ".join(a for a in sys.argv[1:] if a != "--inspect"))
        sys.exit(0)
    query = " ".join(sys.argv[1:])
    hits = search_patents(query)
    print(f"\n{len(hits)} results for '{query}':\n")
    for r in hits:
        print(f"- {r['application_number']}: {r['title']}")
