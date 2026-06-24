from typing import Dict, List

from ddgs import DDGS


def run(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    limit = max(1, min(int(max_results), 10))
    rows = list(DDGS().text(query, max_results=limit))
    results: List[Dict[str, str]] = []

    for row in rows:
        title = row.get("title") or "Untitled"
        url = row.get("href") or row.get("url") or ""
        snippet = row.get("body") or row.get("snippet") or ""
        if not url:
            continue
        results.append(
            {
                "title": str(title),
                "url": str(url),
                "snippet": str(snippet),
            }
        )
        if len(results) >= limit:
            break
    return results
