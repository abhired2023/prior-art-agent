import argparse
import json
import random


def load_results(path="patents_with_abstracts.json"):
    with open(path) as f:
        return json.load(f)


def print_entry(entry, index=None):
    print("=" * 80)
    print(f"#{index} Patent ID: {entry.get('patent_id')}")
    print(f"Title (scraped):      {entry.get('title')}")
    print(f"Title (from ODP):     {entry.get('odp_title')}")
    print(f"URL:                  {entry.get('url')}")
    print("-" * 80)
    print("Abstract (scraped):")
    print(entry.get("abstract"))
    print("=" * 80)
    print("--> Open the URL above, find the Abstract section, and compare by eye.\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="patents_with_abstracts.json")
    parser.add_argument("--n", type=int, default=3)
    args = parser.parse_args()

    results = load_results(args.path)
    successful = [r for r in results if r.get("abstract")]
    sample = random.sample(successful, min(args.n, len(successful)))

    for i, entry in enumerate(sample, 1):
        print_entry(entry, index=i)


if __name__ == "__main__":
    main()
