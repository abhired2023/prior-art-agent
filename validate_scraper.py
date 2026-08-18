import argparse
import json
import random


def load_results(path: str = "patents_with_abstracts.json"):
    with open(path) as f:
        return json.load(f)


def print_entry(entry: dict, index: int = None):
    label = f"#{index}" if index is not None else ""
    print("=" * 80)
    print(f"{label} Patent ID: {entry.get('patent_id')}")
    print(f"Title (scraped):      {entry.get('title')}")
    print(f"Title (from ODP):     {entry.get('odp_title')}")
    print(f"URL:                  {entry.get('url')}")
    print("-" * 80)
    print("Abstract (scraped):")
    print(entry.get("abstract") or "(none captured)")
    print("=" * 80)
    print("--> Open the URL above, find the Abstract section, and compare by eye.\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="patents_with_abstracts.json")
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--id", default=None)
    args = parser.parse_args()

    results = load_results(args.path)
    successful = [r for r in results if r.get("abstract")]

    if not successful:
        print("No entries with a scraped abstract found -- nothing to validate.")
        return

    if args.id:
        matches = [r for r in results if r.get("patent_id") == args.id]
        if not matches:
            print(f"No entry found with patent_id '{args.id}'.")
            return
        sample = matches
    else:
        n = min(args.n, len(successful))
        sample = random.sample(successful, n)

    print(f"Spot-checking {len(sample)} entr{'y' if len(sample) == 1 else 'ies'}.\n")
    for i, entry in enumerate(sample, 1):
        print_entry(entry, index=i)


if __name__ == "__main__":
    main()
