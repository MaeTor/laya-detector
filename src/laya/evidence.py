"""Evidence passages from an OpenRouter LLM with web search. The LLM gathers sources; it never gives the verdict."""
import os

import httpx

MODEL = "deepseek/deepseek-v4.1-flash"
URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_PASSAGES = 5
MAX_CHARS = 2000
PROMPT = ("Search for reliable sources about the following claim and quote the facts they state that bear on it. "
          "Report what the sources say; do not say whether the claim is true.\n\nClaim: {claim}")


class EvidenceError(Exception):
    pass


def parse_passages(message):
    """Chat completion message -> passages. One per cited URL (its content, else the cited span of the answer); with no
    citations, the whole answer as one unsourced passage."""
    text = message.get("content") or ""
    out, seen = [], set()
    for a in message.get("annotations") or []:
        c = a.get("url_citation") if a.get("type") == "url_citation" else None
        if not c or c["url"] in seen:
            continue
        seen.add(c["url"])
        body = c.get("content") or text[c.get("start_index", 0):c.get("end_index", 0)] or text
        out.append({"text": body[:MAX_CHARS], "url": c["url"], "title": c.get("title"), "sourced": True})
    if not out and text.strip():
        out.append({"text": text[:MAX_CHARS], "url": None, "title": None, "sourced": False})
    return out[:MAX_PASSAGES]


class Evidence:
    def __init__(self, api_key=None, model=MODEL, client=None):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self.model = model
        self.client = client or httpx.Client(timeout=90)

    @property
    def enabled(self):
        return bool(self.api_key)

    def fetch(self, claim):
        try:
            r = self.client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, json={
                "model": self.model,
                "messages": [{"role": "user", "content": PROMPT.format(claim=claim)}],
                "tools": [{"type": "openrouter:web_search"}],
            })
            r.raise_for_status()
            return parse_passages(r.json()["choices"][0]["message"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise EvidenceError(f"{type(e).__name__}: {e}") from e
