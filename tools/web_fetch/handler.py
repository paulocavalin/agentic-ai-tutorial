import re
from html import unescape
from typing import Any, Dict

import requests


def _clean_html(raw_html: str) -> str:
    no_script = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.IGNORECASE)
    no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script, flags=re.IGNORECASE)
    no_tags = re.sub(r"<[^>]+>", " ", no_style)
    text = unescape(no_tags)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def run(url: str) -> Dict[str, Any]:
    headers = {
        "User-Agent": "SimpleAgent/1.0",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    }
    response = requests.get(url, timeout=15, headers=headers)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "html" in content_type.lower():
        content = _clean_html(response.text)
    else:
        content = response.text

    return {
        "url": url,
        "status_code": response.status_code,
        "content": content[:3000],
    }
