"""LangChain tools for the portfolio chatbot agent.

Tools are synchronous — LangChain automatically runs them in a thread executor
when invoked from an async agent context (same pattern as yahoo_finance.py in
the investment module).

Two tools:
- list_medium_articles: fetches the RSS feed to get article titles + URLs
- get_medium_article_content: fetches a full article page and extracts the text
"""
import logging
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_MEDIUM_RSS_URL = "https://medium.com/feed/@kelly.roussel"
_MAX_ARTICLE_CHARS = 8000


def build_tools() -> list[Any]:
    """Return the list of LangChain tools for the portfolio agent."""

    @tool
    def list_medium_articles() -> str:
        """List Kelly's most recent Medium articles with their titles, publication dates, and URLs.
        Call this first to discover which articles exist before fetching their content."""
        try:
            feed = feedparser.parse(_MEDIUM_RSS_URL)
            if not feed.entries:
                return "No articles found."
            lines = []
            for entry in feed.entries[:5]:
                title = entry.get("title", "Untitled")
                link = entry.get("link", "")
                published = entry.get("published", "")
                lines.append(f"- {title} ({published})\n  URL: {link}")
            return "\n".join(lines)
        except Exception as e:
            logger.error("Failed to fetch Medium RSS feed: %s", e)
            return f"Error fetching articles: {e}"

    @tool
    def get_medium_article_content(url: str) -> str:
        """Fetch and return the full text content of a Medium article given its URL.
        Use list_medium_articles first to get article URLs."""
        try:
            response = httpx.get(
                url,
                follow_redirects=True,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; PortfolioBot/1.0)"},
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            article = soup.find("article")
            if article:
                text = article.get_text(separator="\n", strip=True)
            else:
                # Fallback: extract all paragraph text
                paragraphs = soup.find_all("p")
                text = "\n".join(p.get_text(strip=True) for p in paragraphs)
            if not text:
                return "Could not extract article content."
            return text[:_MAX_ARTICLE_CHARS]
        except Exception as e:
            logger.error("Failed to fetch Medium article %s: %s", url, e)
            return f"Error fetching article: {e}"

    return [list_medium_articles, get_medium_article_content]
