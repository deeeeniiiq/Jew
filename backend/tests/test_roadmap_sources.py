"""Verified source retrieval remains bounded and independent of the LLM output."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from app.services.roadmap_studio import RoadmapSource, RoadmapTopic, find_study_sources


def topic(title: str) -> RoadmapTopic:
    return RoadmapTopic(title=title, description="Learn the fundamentals through examples.",
                        outcome="Explain the central concepts.", stage=0, estimated_minutes=45)


class RoadmapSourceTests(unittest.IsolatedAsyncioTestCase):
    async def fetch_with(self, handler, topics=None):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with patch("app.services.roadmap_studio.httpx.AsyncClient", return_value=http):
                return await find_study_sources(topics or [topic("Brazilian ecology")], "pt")
        finally:
            await http.aclose()

    async def test_wikipedia_response_has_attributed_encyclopedia_source(self):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200, json={"query": {"pages": {"7": {
                "title": "Ecologia", "fullurl": "https://pt.wikipedia.org/wiki/Ecologia", "index": 1,
            }}}})

        sources, status = await self.fetch_with(handler)
        self.assertEqual(status, "available")
        self.assertEqual(sources[0][0].kind, "encyclopedia")
        self.assertEqual(len(requests), 1)

    async def test_403_wikipedia_falls_back_to_openalex(self):
        requests = []

        def handler(request):
            requests.append(request.url.host)
            if request.url.host == "pt.wikipedia.org":
                return httpx.Response(403)
            self.assertEqual(request.url.host, "api.openalex.org")
            return httpx.Response(200, json={"results": [{
                "title": "Brazilian biomes", "id": "https://openalex.org/W1234567",
                "doi": "https://doi.org/10.1234/example",
            }]})

        sources, status = await self.fetch_with(handler)
        self.assertEqual(requests, ["pt.wikipedia.org", "api.openalex.org"])
        self.assertEqual(status, "available")
        self.assertEqual(sources[0][0].kind, "research")
        self.assertEqual(sources[0][0].url, "https://doi.org/10.1234/example")

    async def test_openlibrary_catalog_fallback_and_untrusted_links_filtered(self):
        requests = []

        def handler(request):
            requests.append(request.url.host)
            if request.url.host == "pt.wikipedia.org":
                return httpx.Response(200, json={"query": {"pages": {"3": {
                    "title": "Spoof", "fullurl": "https://evil.example/wiki/Ecologia",
                }}}})
            if request.url.host == "api.openalex.org":
                return httpx.Response(200, json={"results": [{"title": "Malicious", "doi": "https://doi.org.evil.example/10.1/x"}]})
            return httpx.Response(200, json={"docs": [
                {"title": "Invalid", "key": "//evil.example"},
                {"title": "Ecology guide", "key": "/works/OL123W"},
            ]})

        sources, status = await self.fetch_with(handler)
        self.assertEqual(status, "available")
        self.assertEqual(requests, ["pt.wikipedia.org", "api.openalex.org", "openlibrary.org"])
        self.assertEqual(sources[0][0].kind, "book")
        self.assertEqual(sources[0][0].url, "https://openlibrary.org/works/OL123W")

    async def test_errors_redirects_and_partial_results(self):
        def handler(request):
            if "Good" in request.url.query.decode():
                if request.url.host == "pt.wikipedia.org":
                    return httpx.Response(200, json={"query": {"pages": {"1": {
                        "title": "Good", "fullurl": "https://pt.wikipedia.org/wiki/Good",
                    }}}})
            return httpx.Response(302, headers={"Location": "https://unsafe.example/"})

        sources, status = await self.fetch_with(handler, [topic("Good"), topic("Missing")])
        self.assertEqual(status, "limited")
        self.assertEqual(len(sources[0]), 1)
        self.assertEqual(sources[1], [])

    async def test_request_count_capped_at_twelve_topics(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(404)

        sources, status = await self.fetch_with(handler, [topic(f"Topic {i}") for i in range(15)])
        self.assertEqual(len(sources), 15)
        self.assertEqual(len(requests), 36)
        self.assertEqual(status, "unavailable")

    def test_rejects_untrusted_source_shapes(self):
        for url, kind in (
            ("http://pt.wikipedia.org/wiki/Ecology", "encyclopedia"),
            ("https://pt.wikipedia.org.evil.example/wiki/Ecology", "encyclopedia"),
            ("https://openlibrary.org/redirect", "book"),
            ("https://evil.example/W123", "research"),
            ("https://visitor@doi.org/10.123/x", "research"),
            ("https://doi.org:8443/10.123/x", "research"),
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                RoadmapSource(label="Reference", url=url, kind=kind)

    async def test_large_external_response_is_rejected_and_fallback_preserved(self):
        requests = []

        def handler(request):
            requests.append(request.url.host)
            if request.url.host == "pt.wikipedia.org":
                return httpx.Response(200, content=b"x" * 256_001)
            return httpx.Response(200, json={"results": [{
                "title": "Conservation", "id": "https://openalex.org/W12345",
            }]})

        sources, status = await self.fetch_with(handler)
        self.assertEqual(requests, ["pt.wikipedia.org", "api.openalex.org"])
        self.assertEqual(status, "available")
        self.assertEqual(sources[0][0].kind, "research")

    async def test_failed_catalog_task_does_not_hide_other_topics(self):
        async def handler(request):
            if "Broken" in str(request.url):
                raise RuntimeError("Unexpected catalog failure")
            return httpx.Response(200, json={"query": {"pages": {"1": {
                "title": "Valid ecology", "fullurl": "https://pt.wikipedia.org/wiki/Ecologia",
            }}}})

        sources, status = await self.fetch_with(handler, [topic("Broken"), topic("Good")])
        self.assertEqual(status, "limited")
        self.assertEqual(sources[0], [])
        self.assertEqual(len(sources[1]), 1)

    async def test_global_deadline_keeps_finished_sources(self):
        original_wait = asyncio.wait

        async def fast_deadline(tasks, timeout):
            return await original_wait(tasks, timeout=0.02)

        async def handler(request):
            if "Slow" in str(request.url):
                await asyncio.sleep(2)
            return httpx.Response(200, json={"query": {"pages": {"1": {
                "title": "Ecology", "fullurl": "https://pt.wikipedia.org/wiki/Ecologia",
            }}}})

        with patch("app.services.roadmap_studio.asyncio.wait", side_effect=fast_deadline):
            sources, status = await self.fetch_with(handler, [topic("Good"), topic("Slow")])
        self.assertEqual(status, "limited")
        self.assertEqual(len(sources[0]), 1)
        self.assertEqual(sources[1], [])


if __name__ == "__main__":
    unittest.main()
