from difflib import SequenceMatcher


def _similar(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def dedupe_pool(records, title_similarity_threshold=0.92):
    deduped = []
    for record in records:
        match_index = None
        for i, existing in enumerate(deduped):
            same_app = record.get("application_number") and record.get("application_number") == existing.get("application_number")
            same_pub = record.get("publication_number") and record.get("publication_number") == existing.get("publication_number")
            fuzzy = _similar(record.get("title", ""), existing.get("title", "")) >= title_similarity_threshold
            if same_app or same_pub or fuzzy:
                match_index = i
                break
        if match_index is None:
            record["found_by_queries"] = list(record.get("found_by_queries", []))
            deduped.append(record)
        else:
            existing = deduped[match_index]
            merged = set(existing.get("found_by_queries", [])) | set(record.get("found_by_queries", []))
            if record.get("score", 0) > existing.get("score", 0):
                record["found_by_queries"] = list(merged)
                deduped[match_index] = record
            else:
                existing["found_by_queries"] = list(merged)
    return deduped
