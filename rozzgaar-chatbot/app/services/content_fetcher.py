import logging
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

_HEADERS = {"Authorization": f"Bearer {settings.rozzgaar_open_key}"}
_TIMEOUT = 15


@dataclass
class RawDoc:
    """One piece of source content before chunking."""
    source: str          # "course" | "bundle" | "page"
    slug: str             # course_slug / bundle_slug / page url
    title: str
    text: str
    url: str | None = None
    extra: dict = field(default_factory=dict)


def _get(path: str, params: dict | None = None) -> dict | None:
    url = f"{settings.rozzgaar_base_url}{path}"
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Rozzgaar API call failed (%s): %s", url, exc)
        return None


def fetch_all_courses() -> list[dict]:
    """Paginates through /courses and returns the raw list of course summaries."""
    courses: list[dict] = []
    page = 1
    while True:
        data = _get("/courses", {"page": page, "limit": 50})
        if not data or data.get("status") != "success":
            break
        items = (data.get("data") or {}).get("items") or data.get("data") or []
        if not items:
            break
        courses.extend(items)
        pagination = (data.get("data") or {}).get("pagination") if isinstance(data.get("data"), dict) else None
        if not pagination or page >= pagination.get("total_pages", page):
            break
        page += 1
    return courses


def fetch_course_detail(slug: str) -> dict | None:
    data = _get(f"/courses/{slug}")
    if data and data.get("status") == "success":
        return data.get("data")
    return None


def fetch_course_contents(slug: str) -> dict | None:
    data = _get(f"/courses/{slug}/contents")
    if data and data.get("status") == "success":
        return data.get("data")
    return None


def fetch_all_bundles() -> list[dict]:
    data = _get("/courses/bundles")
    if data and data.get("status") == "success":
        result = data.get("data")
        return result if isinstance(result, list) else result.get("items", [])
    return []


def fetch_bundle_detail(slug: str) -> dict | None:
    data = _get(f"/courses/bundles/{slug}")
    if data and data.get("status") == "success":
        return data.get("data")
    return None


def _course_to_text(detail: dict, contents: dict | None) -> str:
    parts = [
        detail.get("title", ""),
        detail.get("short_description", ""),
        detail.get("description", ""),
        f"Price: {detail.get('price', 'N/A')}",
        f"Duration: {detail.get('duration', 'N/A')}",
    ]
    if contents:
        modules = contents.get("modules") or contents.get("chapters") or []
        if modules:
            parts.append(f"This course has {len(modules)} modules in total.")
        for i, m in enumerate(modules, start=1):
            parts.append(f"Module {i}: {m.get('title', '')}")
            for ch in m.get("chapters", m.get("lessons", [])):
                parts.append(f"- {ch.get('title', '')}")
    return "\n".join(p for p in parts if p)


def build_course_docs() -> list[RawDoc]:
    docs: list[RawDoc] = []
    for summary in fetch_all_courses():
        slug = summary.get("slug")
        if not slug:
            continue
        detail = fetch_course_detail(slug) or summary
        contents = fetch_course_contents(slug)
        text = _course_to_text(detail, contents)
        docs.append(RawDoc(
            source="course",
            slug=slug,
            title=detail.get("title", slug),
            text=text,
            url=f"https://rozzgaar.in/courses/{slug}",
            extra={"price": detail.get("price"), "duration": detail.get("duration")},
        ))
    return docs


def build_bundle_docs() -> list[RawDoc]:
    docs: list[RawDoc] = []
    for summary in fetch_all_bundles():
        slug = summary.get("slug")
        if not slug:
            continue
        detail = fetch_bundle_detail(slug) or summary
        courses = detail.get("courses", [])
        course_titles = "\n".join(f"- {c.get('title', '')}" for c in courses)
        text = "\n".join(filter(None, [
            detail.get("title", ""),
            detail.get("description", ""),
            f"Price: {detail.get('price', 'N/A')}",
            "Included courses:",
            course_titles,
        ]))
        docs.append(RawDoc(
            source="bundle",
            slug=slug,
            title=detail.get("title", slug),
            text=text,
            url=f"https://rozzgaar.in/bundles/{slug}",
        ))
    return docs


def scrape_static_pages(urls: list[str] | None = None) -> list[RawDoc]:
    """Scrapes plain visible text from configured static marketing pages
    (About, FAQ, Contact, etc.) so the chatbot can answer general
    questions beyond course data."""
    urls = urls if urls is not None else settings.static_page_url_list
    docs: list[RawDoc] = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to scrape %s: %s", url, exc)
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url
        text = " ".join(soup.get_text(separator=" ").split())
        if text:
            docs.append(RawDoc(source="page", slug=url, title=title, text=text, url=url))
    return docs


def build_all_docs() -> list[RawDoc]:
    """Pulls everything: live courses + bundles from the Rozzgaar API,
    plus scraped static pages. Call this from the ingest job."""
    docs = build_course_docs()
    docs.extend(build_bundle_docs())
    docs.extend(scrape_static_pages())
    return docs
