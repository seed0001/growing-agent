"""Web search via DuckDuckGo."""


async def search_web(query: str, max_results: int = 8) -> str:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                results.append(f"**{title}**\n{body}\n{href}")
        if not results:
            return f"No results for: {query}"
        return f"Search: {query}\n\n" + "\n\n---\n\n".join(results)
    except Exception as e:
        return f"Error searching web: {e}"
