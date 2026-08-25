from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import active_count, Thread
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from uuid import uuid4


class WebsiteEvidenceFetcherTests(unittest.TestCase):
    def test_fetches_homepage_and_three_relevant_same_domain_pages_as_compact_evidence(self) -> None:
        from royal_glass_validator.website_fetch import (
            FetchSourceRecord,
            WebsiteEvidenceFetcher,
        )

        with FixtureWebsite(
            {
                "/": FixtureResponse(
                    body=_html(
                        "Royal Glass Test",
                        "Glass pool fencing and balustrades in Auckland, New Zealand.",
                        links=["/services", "/pool-fencing", "/about", "/contact", "https://outside.example/contact"],
                    )
                ),
                "/services": FixtureResponse(body=_html("Services", "Residential glass balustrades.")),
                "/pool-fencing": FixtureResponse(body=_html("Pool fencing", "Frameless pool fencing installation.")),
                "/about": FixtureResponse(body=_html("About", "Serving New Zealand homeowners.")),
                "/contact": FixtureResponse(body=_html("Contact", "Call us today.")),
            }
        ) as website:
            repository = RecordingEvidenceRepository()
            record = FetchSourceRecord(
                id=uuid4(),
                validation_run_id=uuid4(),
                original_values={"Website": website.url("/")},
            )

            summary = WebsiteEvidenceFetcher(repository).fetch_record(record)

        self.assertEqual(summary.evidence_count, 4)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual([evidence.url for evidence in repository.evidence], [
            website.url("/"),
            website.url("/services"),
            website.url("/pool-fencing"),
            website.url("/about"),
        ])
        self.assertTrue(all(evidence.source_type == "official_site" for evidence in repository.evidence))
        self.assertTrue(all(evidence.page_title for evidence in repository.evidence))
        self.assertTrue(all(0 < len(evidence.evidence_snippet) <= 1200 for evidence in repository.evidence))
        self.assertTrue(all(len(evidence.content_sha256) == 64 for evidence in repository.evidence))
        self.assertEqual(repository.evidence[0].service_facts["services"], ["balustrades", "pool_fencing"])
        self.assertEqual(repository.evidence[0].region_facts["regions"], ["auckland", "new_zealand"])
        self.assertTrue(all(evidence.fetched_at.tzinfo is not None for evidence in repository.evidence))

    def test_retries_one_transient_server_failure_then_retains_the_successful_page(self) -> None:
        from royal_glass_validator.website_fetch import FetchSourceRecord, WebsiteEvidenceFetcher

        with FixtureWebsite(
            {"/": [FixtureResponse(status=503), FixtureResponse(body=_html("Recovered", "Pool fencing in New Zealand."))]}
        ) as website:
            repository = RecordingEvidenceRepository()
            summary = WebsiteEvidenceFetcher(repository).fetch_record(
                FetchSourceRecord(id=uuid4(), validation_run_id=uuid4(), original_values={"Website": website.url("/")})
            )

        self.assertEqual(summary.evidence_count, 1)
        self.assertEqual(summary.failure_count, 1)
        self.assertEqual([(failure.failure_type, failure.attempt_number) for failure in repository.failures], [("server_error", 1)])
        self.assertEqual(repository.evidence[0].page_title, "Recovered")

    def test_captures_required_review_failures_and_continues_the_batch(self) -> None:
        from royal_glass_validator.website_fetch import FetchSourceRecord, WebsiteEvidenceFetcher

        with FixtureWebsite(
            {
                "/robots.txt": FixtureResponse(body=b"User-agent: *\nDisallow: /robots\n", content_type="text/plain"),
                "/forbidden": FixtureResponse(status=403),
                "/challenge": FixtureResponse(body=_html("Checking your browser", "Access denied: bot verification required.")),
                "/robots": FixtureResponse(body=_html("Robots", "This page must not be fetched.")),
                "/javascript": FixtureResponse(
                    body=b"<html><head><title>App</title><script>window.bootValidatorApp();</script></head><body></body></html>"
                ),
                "/missing": FixtureResponse(status=404),
                "/available": FixtureResponse(body=_html("Available", "Glass balustrades in Auckland.")),
            }
        ) as website:
            repository = RecordingEvidenceRepository()
            records = tuple(
                FetchSourceRecord(id=uuid4(), validation_run_id=uuid4(), original_values={"Website": website.url(path)})
                for path in ("/forbidden", "/challenge", "/robots", "/javascript", "/missing", "/available")
            )

            summaries = WebsiteEvidenceFetcher(repository).fetch_records(records)

        self.assertEqual(len(summaries), 6)
        self.assertEqual(sum(summary.evidence_count for summary in summaries), 1)
        self.assertEqual(sum(summary.failure_count for summary in summaries), 5)
        self.assertEqual(
            [failure.failure_type for failure in repository.failures],
            ["blocked", "blocked", "robots_restricted", "javascript_only", "http_error"],
        )
        self.assertTrue(all(failure.required_outcome == "review_required" for failure in repository.failures))
        self.assertEqual(repository.evidence[0].page_title, "Available")

    def test_retries_a_timeout_once_and_retains_both_attempts_as_review_required_failures(self) -> None:
        from royal_glass_validator.website_fetch import FetchSourceRecord, WebsiteEvidenceFetcher

        with FixtureWebsite({"/slow": FixtureResponse(body=_html("Slow", "Pool fencing."), delay_seconds=0.5)}) as website:
            repository = RecordingEvidenceRepository()
            summary = WebsiteEvidenceFetcher(repository, timeout_seconds=0.1).fetch_record(
                FetchSourceRecord(id=uuid4(), validation_run_id=uuid4(), original_values={"Website": website.url("/slow")})
            )

        self.assertEqual(summary.evidence_count, 0)
        self.assertEqual(summary.failure_count, 2)
        self.assertEqual([(failure.failure_type, failure.attempt_number) for failure in repository.failures], [("timeout", 1), ("timeout", 2)])

    def test_discovers_relevant_pages_on_the_same_domain_across_scheme_and_www_variants(self) -> None:
        from royal_glass_validator.website_fetch import relevant_same_domain_urls

        urls = relevant_same_domain_urls(
            "http://www.example.test/",
            _html(
                "Example",
                "Glass services.",
                links=[
                    "https://example.test/services",
                    "https://outside.example.test/pool-fencing",
                ],
            ),
        )

        self.assertEqual(urls, ["https://example.test/services"])

    def test_records_timeouts_and_continues_when_a_request_never_returns_to_the_http_client(self) -> None:
        from royal_glass_validator.website_fetch import FetchSourceRecord, WebsiteEvidenceFetcher

        def stalled_urlopen(*args: object, **kwargs: object) -> object:
            sleep(0.5)
            raise AssertionError("The stalled request should be abandoned before it returns.")

        repository = RecordingEvidenceRepository()
        started_at = monotonic()
        with patch("royal_glass_validator.website_fetch.urlopen", side_effect=stalled_urlopen):
            summary = WebsiteEvidenceFetcher(repository, timeout_seconds=0.01).fetch_record(
                FetchSourceRecord(id=uuid4(), validation_run_id=uuid4(), original_values={"Website": "https://stalled.example/"})
            )
        elapsed = monotonic() - started_at

        self.assertLess(elapsed, 0.2)
        self.assertEqual((summary.evidence_count, summary.failure_count), (0, 2))
        self.assertEqual([(failure.failure_type, failure.attempt_number) for failure in repository.failures], [("timeout", 1), ("timeout", 2)])
        sleep(0.55)

    def test_bounds_abandoned_network_workers_when_repeated_requests_stall(self) -> None:
        from royal_glass_validator.website_fetch import (
            MAX_CONCURRENT_STALLED_HTTP_CALLS,
            FetchSourceRecord,
            WebsiteEvidenceFetcher,
        )

        def stalled_urlopen(*args: object, **kwargs: object) -> object:
            sleep(0.25)
            raise TimeoutError("late timeout")

        repository = RecordingEvidenceRepository()
        baseline_workers = active_count()
        records = tuple(
            FetchSourceRecord(id=uuid4(), validation_run_id=uuid4(), original_values={"Website": "https://stalled.example/"})
            for _ in range(8)
        )
        with patch("royal_glass_validator.website_fetch.urlopen", side_effect=stalled_urlopen):
            WebsiteEvidenceFetcher(repository, timeout_seconds=0.01).fetch_records(records)
            self.assertLessEqual(active_count() - baseline_workers, MAX_CONCURRENT_STALLED_HTTP_CALLS)

        sleep(0.3)


def _html(title: str, text: str, *, links: list[str] | None = None) -> bytes:
    anchors = "".join(f'<a href="{link}">Link</a>' for link in links or [])
    return f"<html><head><title>{title}</title></head><body><p>{text}</p>{anchors}</body></html>".encode()


class FixtureResponse:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        delay_seconds: float = 0,
    ) -> None:
        self.body = body
        self.status = status
        self.content_type = content_type
        self.delay_seconds = delay_seconds


class FixtureWebsite:
    def __init__(self, responses: dict[str, FixtureResponse | list[FixtureResponse]]) -> None:
        self._responses = responses
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_type(responses))
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FixtureWebsite":
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self._server.server_port}{path}"

    @staticmethod
    def _handler_type(responses: dict[str, FixtureResponse | list[FixtureResponse]]) -> type[BaseHTTPRequestHandler]:
        requests_by_path: dict[str, int] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                configured_response = responses.get(self.path)
                if configured_response is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if isinstance(configured_response, list):
                    request_number = requests_by_path.get(self.path, 0)
                    response = configured_response[min(request_number, len(configured_response) - 1)]
                    requests_by_path[self.path] = request_number + 1
                else:
                    response = configured_response
                if response.delay_seconds:
                    from time import sleep

                    sleep(response.delay_seconds)
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                try:
                    self.wfile.write(response.body)
                except (BrokenPipeError, ConnectionAbortedError):
                    return

            def log_message(self, format: str, *args: object) -> None:
                return None

        return Handler


class RecordingEvidenceRepository:
    def __init__(self) -> None:
        self.evidence: list[object] = []
        self.failures: list[object] = []

    def record_evidence(self, evidence: object) -> None:
        self.evidence.append(evidence)

    def record_failure(self, failure: object) -> None:
        self.failures.append(failure)
