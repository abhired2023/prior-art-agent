import argparse
import json
import math
from datetime import datetime, timezone

from planner import get_plan, get_replan_query
from odp_client import search_patents
from llm_scorer import score_batch
from dedupe import dedupe_pool
from scrape_abstracts import scrape_shortlist
from final_report import score_with_abstracts, generate_report

CANDIDATES_PER_QUERY = 50
TOP_PERCENT_PER_QUERY = 0.20
FINAL_SHORTLIST_SIZE = (5, 10)
MIN_RELEVANCE_SCORE = 5
SEARCH_BUDGET = 8
STRONG_MATCH_SCORE = 8
STRONG_MATCH_STOP_COUNT = 5


def run_step1(invention_description, queries=None, model=None):
    log = {
        "invention_description": invention_description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queries": [],
        "replans": [],
    }
    searches_used = 0

    if queries is None:
        print("Calling planner for search queries...")
        plan = get_plan(invention_description, model=model)
        queries = plan["queries"]
        log["plan"] = plan
        print(f"Planner returned {len(queries)} queries: {queries}")

    candidate_pool = []
    num_original_queries = len(queries)

    for i, query in enumerate(queries):
        if searches_used >= SEARCH_BUDGET:
            print(f"\nSearch budget ({SEARCH_BUDGET}) reached -- stopping.")
            break

        print(f"\n--- Query: '{query}' ---")
        query_log = {"query": query}
        searches_used += 1

        try:
            records = search_patents(query, limit=CANDIDATES_PER_QUERY)
        except Exception as e:
            print(f"  ERROR searching '{query}': {e}")
            query_log["error"] = str(e)
            records = None

        if records is None:
            records = []
        query_log["raw_hit_count"] = len(records)
        print(f"  Got {len(records)} raw candidates.")

        scored = []
        best_score = -1
        if records:
            scored = score_batch(invention_description, records, model=model)
            scored.sort(key=lambda r: r["score"], reverse=True)
            best_score = scored[0]["score"] if scored else -1

        needs_replan = (len(records) == 0) or (best_score < MIN_RELEVANCE_SCORE)
        if needs_replan and searches_used < SEARCH_BUDGET:
            reason = "0 raw candidates" if len(records) == 0 else f"best score only {best_score} (below threshold {MIN_RELEVANCE_SCORE})"
            print(f"  Query underperformed ({reason}) -- asking planner to replan...")
            replacement_query = get_replan_query(invention_description, query, reason, model=model)
            searches_used += 1

            replan_record = {"original_query": query, "reason": reason, "replacement_query": replacement_query}

            if replacement_query:
                print(f"  Replan produced: '{replacement_query}'")
                try:
                    replacement_records = search_patents(replacement_query, limit=CANDIDATES_PER_QUERY)
                except Exception as e:
                    replacement_records = []
                    replan_record["error"] = str(e)

                replan_record["replacement_hit_count"] = len(replacement_records) if replacement_records else 0
                print(f"  Replacement query got {replan_record['replacement_hit_count']} raw candidates.")

                if replacement_records:
                    replacement_scored = score_batch(invention_description, replacement_records, model=model)
                    replacement_scored.sort(key=lambda r: r["score"], reverse=True)
                    for r in replacement_scored:
                        r["found_by_queries"] = [replacement_query]
                    keep_n = max(1, math.ceil(len(replacement_scored) * TOP_PERCENT_PER_QUERY))
                    candidate_pool.extend(replacement_scored[:keep_n])
                    replan_record["replacement_top_score"] = replacement_scored[0]["score"]
            else:
                print("  Replan failed to produce a usable query -- skipping.")

            log["replans"].append(replan_record)

        if scored:
            for r in scored:
                r["found_by_queries"] = [query]
            keep_n = max(1, math.ceil(len(scored) * TOP_PERCENT_PER_QUERY))
            top_slice = scored[:keep_n]
            query_log["kept_top_percent"] = keep_n
            query_log["cutoff_score"] = top_slice[-1]["score"] if top_slice else None
            print(f"  Kept top {keep_n} (cutoff score: {query_log['cutoff_score']}).")
            candidate_pool.extend(top_slice)

        log["queries"].append(query_log)

        strong_count = sum(1 for r in candidate_pool if r.get("score", 0) >= STRONG_MATCH_SCORE)
        queries_completed = i + 1
        if queries_completed >= num_original_queries and strong_count >= STRONG_MATCH_STOP_COUNT:
            print(f"\nAll {num_original_queries} planned queries done, found {strong_count} strong matches (score >= {STRONG_MATCH_SCORE}) -- stopping.")
            break
        elif strong_count >= STRONG_MATCH_STOP_COUNT:
            print(f"  ({strong_count} strong matches so far, but continuing through remaining planned queries before stopping.)")

    print(f"\nTotal searches used: {searches_used}/{SEARCH_BUDGET}")
    print(f"Candidate pool before dedup: {len(candidate_pool)}")
    deduped_pool = dedupe_pool(candidate_pool)
    print(f"Candidate pool after dedup: {len(deduped_pool)}")

    relevant_pool = [r for r in deduped_pool if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
    filtered_out = len(deduped_pool) - len(relevant_pool)
    if filtered_out:
        print(f"Filtered out {filtered_out} candidate(s) scoring below {MIN_RELEVANCE_SCORE}.")

    relevant_pool.sort(key=lambda r: r["score"], reverse=True)
    target = min(FINAL_SHORTLIST_SIZE[1], len(relevant_pool))
    shortlist = relevant_pool[:target]

    log["candidate_pool_size_before_dedup"] = len(candidate_pool)
    log["candidate_pool_size_after_dedup"] = len(deduped_pool)
    log["filtered_out_below_min_score"] = filtered_out
    log["final_shortlist_size"] = len(shortlist)
    log["total_searches_used"] = searches_used
    return shortlist, log


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full prior-art research agent end to end.")
    parser.add_argument("invention_description")
    parser.add_argument("--queries", nargs="+", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    shortlist, log = run_step1(args.invention_description, queries=args.queries, model=args.model)
    with open("shortlist.json", "w") as f:
        json.dump(shortlist, f, indent=2)
    with open("log.json", "w") as f:
        json.dump(log, f, indent=2)

    print(f"\nStep 1 done. {len(shortlist)} patents shortlisted -> shortlist.json")

    print("\n--- Scraping abstracts for shortlisted patents ---")
    scraped = scrape_shortlist(shortlist_path="shortlist.json", output_path="patents_with_abstracts.json")

    print("\n--- Scoring with full abstracts and writing final report ---")
    scored_patents = [p for p in scraped if p.get("abstract")]
    if scored_patents:
        ranked = score_with_abstracts(args.invention_description, scored_patents, model=args.model)
        ranked.sort(key=lambda p: p["abstract_score"], reverse=True)
        with open("final_ranked.json", "w") as f:
            json.dump(ranked, f, indent=2)
        generate_report(args.invention_description, ranked, log_path="log.json", output_path="report.md")
        print("\nFinal ranking:")
        for p in ranked[:10]:
            print(f"  [{p['abstract_score']}] {p.get('title') or p.get('odp_title')}")
    else:
        print("No abstracts were successfully scraped -- skipping final report.")

    print("\n=== DONE ===")
