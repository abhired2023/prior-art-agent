"""
uspto_client.py

Purpose:
    Search USPTO patent applications by keyword and return
    titles + abstracts. This is the data retrieval layer
    used by the agent's Act Mode.

Usage:
    python3 uspto_client.py "glucose monitoring"
"""

import requests
import sys
import xml.etree.ElementTree as ET

USPTO_API_KEY = "rsyaucihvxwbnculpdgbigzsnqolfl"
SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"

def search_patents(query: str, limit: int = 10):
    """
    Search USPTO patent applications by keyword.

    Returns:
        List of dicts containing:
        - application_number
        - title
        - publication_number
    """
    if USPTO_API_KEY == "PASTE_YOUR_KEY_HERE":
        raise ValueError("Insert your USPTO API key into USPTO_API_KEY.")

    payload = {
        "q": query,
        "fields": [
            "applicationNumberText",
            "applicationMetaData.inventionTitle",
            "earliestPublicationNumber"
        ],
        "pagination": {"offset": 0, "limit": limit}
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api_key": USPTO_API_KEY
    }

    response = requests.post(SEARCH_URL, json=payload, headers=headers)

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"USPTO returned non-JSON:\n{response.text}")

    results = []
    for item in data.get("patentFileWrapperDataBag", []):
        results.append({
            "application_number": item.get("applicationNumberText"),
            "title": item["applicationMetaData"].get("inventionTitle"),
            "publication_number": item["applicationMetaData"].get("earliestPublicationNumber")
        })

    return results


def fetch_abstract(publication_number: str):
    """
    Fetch the abstract from the USPTO full-text XML.

    Returns:
        str: abstract text or None
    """
    if not publication_number:
        return None

    # Convert "US 2014-0167116 A1" → "20140167116"
    pub_num_clean = publication_number.replace("US", "").replace(" ", "").replace("-", "")
    xml_url = f"https://bulkdata.uspto.gov/data/patent/application/redbook/fulltext/{pub_num_clean}.xml"

    response = requests.get(xml_url)

    if response.status_code != 200:
        return None

    try:
        root = ET.fromstring(response.text)
        abstract = root.find(".//abstract")
        return abstract.text if abstract is not None else None
    except Exception:
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 uspto_client.py \"search keywords\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    hits = search_patents(query)

    print("\nSearch Results:")
    for r in hits:
        abstract = fetch_abstract(r["publication_number"])
        print(f"- {r['application_number']}: {r['title']}")
        print(f"  Abstract: {abstract}\n")

