import argparse
import json
import math
from datetime import datetime, timezone

from planner import get_plan
from odp_client import search_patents
from llm_scorer import score_batch
from dedupe import dedupe_pool

CANDIDATES_PER_QUERY = 50
TOP_PERCENT_PER_QUERY = 0.20
FINAL_SHORTLIST_SIZE = (15, 20)
MIN_RELEVANCE_SCORE = 5  # candidates scoring below this never make the final shortlist




def run_step1(invention_description, queries=None, model="llama3.1"):
    log = {"invention_description": invention_description, "timestamp": datetime.now(timezone.utc).isoformat(), "queries": []}

    if queries is None:
        print("Calling planner for search queries...")
        plan = get_plan(invention_description, model=model)
        queries = plan["queries"]
        log["plan"] = plan
        print(f"Planner returned {len(queries)} queries: {queries}")

    candidate_pool = []
    for query in queries:
        print(f"\n--- Query: '{query}' ---")
        query_log = {"query": query}
        try:
            records = search_patents(query, limit=CANDIDATES_PER_QUERY)
        except Exception as e:
            print(f"  ERROR searching '{query}': {e}")
            query_log["error"] = str(e)
            log["queries"].append(query_log)
            continue

        if records is None:
            records = []
        query_log["raw_hit_count"] = len(records)
        print(f"  Got {len(records)} raw candidates.")
        if not records:
            log["queries"].append(query_log)
            continue

        scored = score_batch(invention_description, records, model=model)
        scored.sort(key=lambda r: r["score"], reverse=True)
        keep_n = max(1, math.ceil(len(scored) * TOP_PERCENT_PER_QUERY))
        top_slice = scored[:keep_n]
        for r in top_slice:
            r["found_by_queries"] = [query]
        query_log["kept_top_percent"] = keep_n
        query_log["cutoff_score"] = top_slice[-1]["score"] if top_slice else None
        log["queries"].append(query_log)
        print(f"  Kept top {keep_n} (cutoff score: {query_log['cutoff_score']}).")
        candidate_pool.extend(top_slice)

    print(f"\nCandidate pool before dedup: {len(candidate_pool)}")
    deduped_pool = dedupe_pool(candidate_pool)
    print(f"Candidate pool after dedup: {len(deduped_pool)}")

    # Filter out anything below the relevance floor BEFORE taking the final
    # top N -- a shorter, clean shortlist beats a padded one with junk in it.
    relevant_pool = [r for r in deduped_pool if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    filtered_out = len(deduped_pool) - len(relevant_pool)
    if filtered_out:
        print(f"Filtered out {filtered_out} candidate(s) scoring below {MIN_RELEVANCE_SCORE} (irrelevant, not included in shortlist).")

    relevant_pool.sort(key=lambda r: r["score"], reverse=True)
    target = min(FINAL_SHORTLIST_SIZE[1], len(relevant_pool))
    shortlist = relevant_pool[:target]

    log["candidate_pool_size_before_dedup"] = len(candidate_pool)
    log["candidate_pool_size_after_dedup"] = len(deduped_pool)
    log["filtered_out_below_min_score"] = filtered_out
    log["final_shortlist_size"] = len(shortlist)
    return shortlist, log


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("invention_description")
    parser.add_argument("--queries", nargs="+", default=None)
    parser.add_argument("--model", default="llama3.1")
    args = parser.parse_args()

    shortlist, log = run_step1(args.invention_description, queries=args.queries, model=args.model)
    with open("shortlist.json", "w") as f:
        json.dump(shortlist, f, indent=2)
    with open("log.json", "w") as f:
        json.dump(log, f, indent=2)

    print(f"\nDone. {len(shortlist)} patents shortlisted -> shortlist.json")
    print("Full audit trail -> log.json")
    print("\nTop of shortlist:")
    for r in shortlist[:5]:
        print(f"  [{r['score']}] {r['title']} ({r.get('application_number')})")
