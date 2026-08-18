import json
import re
import time
import requests
from selectolax.parser import HTMLParser

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

REQUEST_DELAY_SECONDS = 1.5


def normalize_patent_id(publication_number: str) -> str:
    if not publication_number:
        return None
    return re.sub(r"[\s\-/]", "", publication_number).upper()


def build_url(patent_id: str) -> str:
    return f"https://patents.google.com/patent/{patent_id}/en"


def scrape_one(patent_id: str):
    url = build_url(patent_id)
    result = {"patent_id": patent_id, "url": url, "title": None, "abstract": None, "error": None}

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        result["error"] = f"Request failed: {e}"
        return result

    tree = HTMLParser(response.text)

    title_tag = tree.css_first('meta[name="DC.title"]')
    title_content = title_tag.attributes.get("content") if title_tag else None
    result["title"] = title_content.strip() if title_content else None

    abstract_div = tree.css_first("div.abstract")
    result["abstract"] = abstract_div.text(strip=True) if abstract_div else None

    if not result["abstract"]:
        result["error"] = "No abstract found -- design patent or not indexed on Google Patents yet."

    return result


def scrape_shortlist(shortlist_path: str = "shortlist.json", output_path: str = "patents_with_abstracts.json"):
    with open(shortlist_path) as f:
        shortlist = json.load(f)

    results = []
    for i, record in enumerate(shortlist):
        raw_id = record.get("publication_number") or record.get("application_number")
        patent_id = normalize_patent_id(raw_id)

        if not patent_id:
            results.append({
                "patent_id": None, "url": None, "title": record.get("title"),
                "abstract": None, "error": "No publication_number or application_number available.",
                "odp_score": record.get("score"),
            })
            continue

        print(f"[{i+1}/{len(shortlist)}] Fetching {patent_id} ...")
        scraped = scrape_one(patent_id)
        scraped["odp_title"] = record.get("title")
        scraped["odp_score"] = record.get("score")
        results.append(scraped)

        if scraped["error"]:
            print(f"  WARNING: {scraped['error']}")
        else:
            print(f"  OK -- abstract length: {len(scraped['abstract'])} chars")

        time.sleep(REQUEST_DELAY_SECONDS)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    ok_count = sum(1 for r in results if r["abstract"])
    print(f"\nDone. {ok_count}/{len(results)} abstracts scraped successfully -> {output_path}")

    return results


if __name__ == "__main__":
    scrape_shortlist()
