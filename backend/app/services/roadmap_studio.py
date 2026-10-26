"""Local-first roadmap authoring with separately retrieved, attributable study sources."""
from __future__ import annotations

import asyncio
import json
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, model_validator


class RoadmapGenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=180)
    profession: str = Field(default="", max_length=120)
    level: str = Field(default="beginner", pattern="^(beginner|intermediate|advanced)$")
    goal: str = Field(default="", max_length=400)
    study_hours_per_week: int = Field(default=0, ge=0, le=80)
    learning_preferences: list[str] = Field(default_factory=list, max_length=6)
    language: str = Field(default="pt", pattern="^(pt|en|ru|uk)$")
    model: str | None = Field(default=None, max_length=160)


class RoadmapSource(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=1000)
    kind: Literal["encyclopedia", "research", "book"] = "encyclopedia"

    @model_validator(mode="after")
    def trusted_search_link(self) -> "RoadmapSource":
        parsed = urlparse(self.url)
        if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.query or parsed.fragment):
            raise ValueError("External sources must come from the trusted search response")
        host = parsed.hostname
        path = parsed.path
        if self.kind == "encyclopedia":
            valid = host in {"pt.wikipedia.org", "en.wikipedia.org", "ru.wikipedia.org", "uk.wikipedia.org"} and path.startswith("/wiki/")
        elif self.kind == "research":
            valid = (host == "doi.org" and path.startswith("/10.") and len(path) > 6) or (
                host == "openalex.org" and path.startswith("/W") and path[2:].isdigit())
        else:
            valid = host == "openlibrary.org" and path.startswith("/works/OL") and path.endswith("W") and path[9:-1].isdigit()
        if not valid:
            raise ValueError("External source URL has an untrusted host or format")
        return self


class RoadmapTopic(BaseModel):
    title: str = Field(min_length=2, max_length=140)
    description: str = Field(min_length=10, max_length=1200)
    outcome: str = Field(min_length=5, max_length=300)
    stage: int = Field(ge=0, le=5)
    estimated_minutes: int = Field(ge=15, le=1200)
    prerequisites: list[int] = Field(default_factory=list, max_length=5)
    resources: list[RoadmapSource] = Field(default_factory=list, max_length=3)


class RoadmapPlan(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=1000)
    topics: list[RoadmapTopic] = Field(min_length=5, max_length=18)

    @model_validator(mode="after")
    def ordered_topics(self) -> "RoadmapPlan":
        for index, topic in enumerate(self.topics):
            if len(set(topic.prerequisites)) != len(topic.prerequisites):
                raise ValueError("Repeated roadmap prerequisites")
            if any(prerequisite < 0 or prerequisite >= index for prerequisite in topic.prerequisites):
                raise ValueError("Roadmap prerequisites must reference earlier topics")
        return self


class RoadmapPreview(RoadmapPlan):
    subject: str = Field(min_length=2, max_length=180)
    language: str = Field(default="pt", pattern="^(pt|en|ru|uk)$")
    resource_search_status: str = Field(default="unavailable", pattern="^(available|limited|unavailable)$")

    @model_validator(mode="after")
    def validate_learning_sequence(self) -> "RoadmapPreview":
        for i, topic in enumerate(self.topics):
            if any(not isinstance(prereq, int) or prereq < 0 or prereq >= i for prereq in topic.prerequisites):
                raise ValueError("Prerequisites must refer to earlier roadmap topics")
            if len(set(topic.prerequisites)) != len(topic.prerequisites):
                raise ValueError("Repeated roadmap prerequisites")
        return self


async def find_study_sources(topics: list[RoadmapTopic], language: str) -> tuple[list[list[RoadmapSource]], str]:
    """Retrieve verified metadata from bounded public catalogs, not model-supplied URLs.

    Research papers and book catalogs are explicitly distinguished from tutorials;
    a catalog link does not promise that a book or paper is freely readable.
    """
    locale = language if language in {"pt", "en", "ru", "uk"} else "en"
    semaphore = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=httpx.Timeout(6.0), follow_redirects=False,
                                  headers={"User-Agent": "JEWStudyRoadmap/1.0 (local learning app)"}) as http:
        async def fetch(url: str, params: dict) -> dict:
            try:
                # Stream with a hard bound: checking response.content after a
                # normal get() would allocate the entire untrusted body first.
                async with http.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(raw) + len(chunk) > 256_000:
                            return {}
                        raw.extend(chunk)
                payload = json.loads(raw)
                return payload if isinstance(payload, dict) else {}
            except (httpx.HTTPError, ValueError, UnicodeError):
                return {}

        def source(label: object, url: object, kind: str) -> RoadmapSource | None:
            if not isinstance(label, str) or not isinstance(url, str):
                return None
            try:
                return RoadmapSource(label=label.strip()[:200], url=url, kind=kind)
            except ValueError:
                return None

        async def query(topic: RoadmapTopic) -> list[RoadmapSource]:
            async with semaphore:
                sources: list[RoadmapSource] = []
                wiki = await fetch(f"https://{locale}.wikipedia.org/w/api.php", {
                    "action": "query", "generator": "search", "gsrsearch": topic.title,
                    "gsrlimit": 2, "prop": "info", "inprop": "url", "format": "json",
                })
                pages = wiki.get("query", {}).get("pages", {}) if isinstance(wiki.get("query"), dict) else {}
                if isinstance(pages, dict):
                    entries = [value for value in pages.values() if isinstance(value, dict)]
                    for item in sorted(entries, key=lambda item: item.get("index", 999))[:2]:
                        result = source(item.get("title"), item.get("fullurl"), "encyclopedia")
                        if result:
                            sources.append(result)

                # Independent fallback: OpenAlex has been reachable in environments
                # where the Wikipedia API returned 403. One result avoids saturating
                # a beginner's roadmap with academic papers.
                if not sources:
                    data = await fetch("https://api.openalex.org/works", {
                        "search": topic.title, "per-page": 2,
                        "select": "id,title,doi,publication_year",
                    })
                    entries = data.get("results", [])
                    if isinstance(entries, list):
                        for item in entries[:2]:
                            if not isinstance(item, dict):
                                continue
                            # DOI is resolvable and points to the specific publication.
                            doi = item.get("doi")
                            identifier = item.get("id")
                            url = doi if isinstance(doi, str) and doi.startswith("https://doi.org/10.") else identifier
                            result = source(item.get("title"), url, "research")
                            if result:
                                sources.append(result)
                                break

                # A book catalog is a final fallback when neither general reference
                # nor scholarly metadata can be retrieved.
                if not sources:
                    books = await fetch("https://openlibrary.org/search.json", {
                        "q": topic.title, "limit": 2, "fields": "key,title",
                    })
                    docs = books.get("docs", [])
                    if isinstance(docs, list):
                        for item in docs[:2]:
                            if not isinstance(item, dict):
                                continue
                            key = item.get("key")
                            result = source(item.get("title"), f"https://openlibrary.org{key}" if isinstance(key, str) else None, "book")
                            if result:
                                sources.append(result)
                                break
                return sources[:3]

        # A failing catalog must not hold the entire preview for a minute.
        # Keep completed sources on deadline instead of losing partial results.
        tasks = [asyncio.create_task(query(topic)) for topic in topics[:12]]
        try:
            done, pending = await asyncio.wait(tasks, timeout=25)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            sources = []
            for task in tasks:
                if task not in done or task.cancelled():
                    sources.append([])
                    continue
                try:
                    sources.append(task.result())
                except Exception:
                    # An unexpected failure in one catalog query must not
                    # discard valid references collected for other topics.
                    sources.append([])
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    padded = [*sources, *([[]] * max(0, len(topics) - len(sources)))]
    found = sum(bool(matches) for matches in sources)
    state = "available" if found == len(topics) and found else "limited" if found else "unavailable"
    return padded, state


async def generate_roadmap_preview(ollama, model: str, request: RoadmapGenerateRequest,
                                   memory_hint: str = "") -> RoadmapPreview:
    """Use Ollama for sequencing and independently retrieved source metadata."""
    context = request.model_dump(exclude={"model"})
    if memory_hint:
        # Auxiliary notes are untrusted data and never become system instructions.
        context["prior_learning_notes_untrusted"] = memory_hint[:1200]
    plan = await ollama.generate_roadmap(model, context, RoadmapPlan)
    normalized = []
    for i, topic in enumerate(plan.topics):
        prerequisites = sorted(set(p for p in topic.prerequisites if 0 <= p < i))
        if i and not prerequisites and topic.stage > 0:
            earlier = [j for j in range(i) if plan.topics[j].stage < topic.stage]
            if earlier:
                prerequisites = [earlier[-1]]
        normalized.append(topic.model_copy(update={"prerequisites": prerequisites, "resources": []}))
    resources, status = await find_study_sources(normalized, request.language)
    return RoadmapPreview(title=plan.title, subject=request.topic.strip(), description=plan.description,
                          language=request.language, resource_search_status=status,
                          topics=[t.model_copy(update={"resources": sources}) for t, sources in zip(normalized, resources)])
