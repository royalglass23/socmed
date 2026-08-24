"""Bounded ordinary-HTTP website evidence capture for imported source records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from socket import timeout as SocketTimeout
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from uuid import UUID, uuid4


REQUEST_TIMEOUT_SECONDS = 15
MAX_RELEVANT_PAGES = 3
WEBSITE_VALUE_KEYS = ("website", "website url", "url", "web address")
RELEVANT_PATH_TERMS = ("service", "pool", "fenc", "balustrade", "about", "contact")


@dataclass(frozen=True)
class FetchSourceRecord:
    """The immutable source-record fields needed to capture official-site evidence."""

    id: UUID
    validation_run_id: UUID
    original_values: Mapping[str, object]


@dataclass(frozen=True)
class PageEvidence:
    id: UUID
    source_record_id: UUID
    validation_run_id: UUID
    url: str
    page_title: str | None
    evidence_snippet: str
    snapshot_body: str
    fetched_at: datetime
    content_sha256: str
    service_facts: Mapping[str, object]
    region_facts: Mapping[str, object]
    source_type: str = "official_site"


@dataclass(frozen=True)
class FetchSummary:
    source_record_id: UUID
    evidence_count: int
    failure_count: int


@dataclass(frozen=True)
class FetchFailure:
    id: UUID
    source_record_id: UUID
    validation_run_id: UUID
    attempted_url: str
    failure_type: str
    attempt_number: int
    response_status: int | None
    detail: str | None
    occurred_at: datetime
    required_outcome: str = "review_required"


class EvidenceRepository(Protocol):
    """Persistence boundary for compact official-site evidence and fetch failures."""

    def record_evidence(self, evidence: PageEvidence) -> None: ...

    def record_failure(self, failure: FetchFailure) -> None: ...


class WebsiteEvidenceFetcher:
    """Fetch a homepage and at most three relevant same-domain pages using ordinary HTTP."""

    def __init__(self, repository: EvidenceRepository, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> None:
        if timeout_seconds <= 0:
            raise ValueError("HTTP timeout must be greater than zero.")
        self._repository = repository
        self._timeout_seconds = timeout_seconds

    def fetch_records(self, records: tuple[FetchSourceRecord, ...]) -> tuple[FetchSummary, ...]:
        """Fetch every supplied Source Record, retaining an outcome for each failed record."""
        return tuple(self.fetch_record(record) for record in records)

    def fetch_record(self, record: FetchSourceRecord) -> FetchSummary:
        """Capture compact evidence for one imported Source Record."""
        try:
            homepage_url = _website_url(record.original_values)
        except ValueError as error:
            self._record_failure(record, "", "missing_site", 1, None, str(error))
            return FetchSummary(source_record_id=record.id, evidence_count=0, failure_count=1)

        if not _robots_allows(homepage_url, self._timeout_seconds):
            self._record_failure(record, homepage_url, "robots_restricted", 1, None, "robots.txt disallows the validator user-agent.")
            return FetchSummary(source_record_id=record.id, evidence_count=0, failure_count=1)

        evidence_count = 0
        failure_count = 0
        homepage = self._fetch_page(record, homepage_url)
        failure_count += homepage.failure_count
        if homepage.evidence is None:
            return FetchSummary(source_record_id=record.id, evidence_count=0, failure_count=failure_count)
        self._repository.record_evidence(homepage.evidence)
        evidence_count += 1

        for page_url in relevant_same_domain_urls(homepage_url, homepage.body)[:MAX_RELEVANT_PAGES]:
            result = self._fetch_page(record, page_url)
            failure_count += result.failure_count
            if result.evidence is not None:
                self._repository.record_evidence(result.evidence)
                evidence_count += 1
        return FetchSummary(source_record_id=record.id, evidence_count=evidence_count, failure_count=failure_count)

    def _fetch_page(self, record: FetchSourceRecord, url: str) -> "_FetchPageResult":
        failure_count = 0
        for attempt_number in (1, 2):
            try:
                body, content_type = _http_get(url, self._timeout_seconds)
            except _HttpFetchError as error:
                self._record_failure(record, url, error.failure_type, attempt_number, error.response_status, error.detail)
                failure_count += 1
                if attempt_number == 1 and error.failure_type in {"timeout", "rate_limited", "server_error"}:
                    continue
                return _FetchPageResult(evidence=None, body=b"", failure_count=failure_count)
            document = _parse_html(body)
            failure_type = _content_failure_type(document)
            if failure_type:
                self._record_failure(record, url, failure_type, attempt_number, None, "Page content is not usable as compact website evidence.")
                return _FetchPageResult(evidence=None, body=b"", failure_count=failure_count + 1)
            return _FetchPageResult(
                evidence=_build_evidence(record, url, body, content_type, document), body=body, failure_count=failure_count
            )
        raise AssertionError("A page fetch must return after its second attempt.")

    def _record_failure(
        self,
        record: FetchSourceRecord,
        attempted_url: str,
        failure_type: str,
        attempt_number: int,
        response_status: int | None,
        detail: str | None,
    ) -> None:
        self._repository.record_failure(
            FetchFailure(
                id=uuid4(),
                source_record_id=record.id,
                validation_run_id=record.validation_run_id,
                attempted_url=attempted_url,
                failure_type=failure_type,
                attempt_number=attempt_number,
                response_status=response_status,
                detail=detail,
                occurred_at=datetime.now(timezone.utc),
            )
        )


@dataclass(frozen=True)
class _FetchPageResult:
    evidence: PageEvidence | None
    body: bytes
    failure_count: int


@dataclass(frozen=True)
class _HttpFetchError(Exception):
    failure_type: str
    response_status: int | None
    detail: str


def _website_url(values: Mapping[str, object]) -> str:
    normalized_values = {str(key).strip().casefold(): value for key, value in values.items()}
    for key in WEBSITE_VALUE_KEYS:
        value = normalized_values.get(key)
        if isinstance(value, str) and value.strip():
            parsed = urlsplit(value.strip())
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    raise ValueError("Source Record has no valid http(s) website URL.")


def _http_get(url: str, timeout_seconds: float) -> tuple[bytes, str | None]:
    request = Request(url, headers={"User-Agent": "RoyalGlassValidator/0.1 (+ordinary HTTP evidence capture)"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URLs are imported review candidates.
            return response.read(), response.headers.get_content_type()
    except HTTPError as error:
        if error.code == 403:
            failure_type = "blocked"
        elif error.code == 429:
            failure_type = "rate_limited"
        elif 500 <= error.code <= 599:
            failure_type = "server_error"
        else:
            failure_type = "http_error"
        raise _HttpFetchError(failure_type, error.code, f"HTTP {error.code}.") from error
    except (TimeoutError, SocketTimeout) as error:
        raise _HttpFetchError("timeout", None, "Request timed out.") from error
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, SocketTimeout)):
            raise _HttpFetchError("timeout", None, "Request timed out.") from error
        raise _HttpFetchError("network_error", None, "Network request failed.") from error


def _build_evidence(
    record: FetchSourceRecord, url: str, body: bytes, content_type: str | None, document: "_HtmlDocument"
) -> PageEvidence:
    text = body.decode("utf-8", errors="replace")
    snippet = " ".join(document.text_parts).strip()
    return PageEvidence(
        id=uuid4(),
        source_record_id=record.id,
        validation_run_id=record.validation_run_id,
        url=url,
        page_title=document.title,
        evidence_snippet=snippet[:1200],
        snapshot_body=text,
        fetched_at=datetime.now(timezone.utc),
        content_sha256=sha256(body).hexdigest(),
        service_facts=_service_facts(snippet),
        region_facts=_region_facts(snippet),
    )


def relevant_same_domain_urls(homepage_url: str, body: bytes) -> list[str]:
    """Return relevant homepage links on the same normalized website domain."""
    document = _parse_html(body)
    homepage_domain = _normalized_domain(homepage_url)
    urls: list[str] = []
    for href in document.hrefs:
        candidate = urljoin(homepage_url, href)
        parsed = urlsplit(candidate)
        normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
        if _normalized_domain(normalized) != homepage_domain or normalized == homepage_url:
            continue
        if not any(term in f"{parsed.path} {parsed.query}".casefold() for term in RELEVANT_PATH_TERMS):
            continue
        if normalized not in urls:
            urls.append(normalized)
    return urls


def _normalized_domain(url: str) -> str:
    hostname = urlsplit(url).hostname
    if not hostname:
        return ""
    return hostname.casefold().removeprefix("www.")


def _service_facts(text: str) -> Mapping[str, object]:
    lowered = text.casefold()
    services = [
        service
        for service, terms in {
            "balustrades": ("balustrade",),
            "pool_fencing": ("pool fencing", "pool fence"),
        }.items()
        if any(term in lowered for term in terms)
    ]
    return {"services": services}


def _region_facts(text: str) -> Mapping[str, object]:
    lowered = text.casefold()
    regions = [
        region
        for region, terms in {
            "auckland": ("auckland",),
            "new_zealand": ("new zealand", "new-zealand", "aotearoa"),
        }.items()
        if any(term in lowered for term in terms)
    ]
    return {"regions": regions}


def _robots_allows(homepage_url: str, timeout_seconds: float) -> bool:
    robots_url = urljoin(homepage_url, "/robots.txt")
    try:
        body, _ = _http_get(robots_url, timeout_seconds)
    except _HttpFetchError:
        return True
    parser = RobotFileParser()
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch("RoyalGlassValidator", homepage_url)


def _parse_html(body: bytes) -> "_HtmlDocument":
    document = _HtmlDocument()
    document.feed(body.decode("utf-8", errors="replace"))
    return document


def _content_failure_type(document: "_HtmlDocument") -> str | None:
    text = " ".join(document.text_parts).casefold()
    if any(marker in text for marker in ("access denied", "bot verification", "checking your browser", "captcha")):
        return "blocked"
    if not text and document.has_script:
        return "javascript_only"
    if not text:
        return "javascript_only"
    return None


class _HtmlDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self.has_script = False
        self._suppressed_text_depth = 0

    @property
    def title(self) -> str | None:
        title = " ".join(self._title_parts).strip()
        return title or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "title":
            self._in_title = True
        if tag.casefold() == "script":
            self.has_script = True
        if tag.casefold() in {"script", "style", "template"}:
            self._suppressed_text_depth += 1
        if tag.casefold() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
        if tag.casefold() in {"script", "style", "template"}:
            self._suppressed_text_depth = max(0, self._suppressed_text_depth - 1)

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned or self._suppressed_text_depth:
            return
        if self._in_title:
            self._title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)
