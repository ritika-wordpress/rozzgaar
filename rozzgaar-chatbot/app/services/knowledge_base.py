import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import settings
from app.services.content_fetcher import RawDoc, build_all_docs

_CHUNK_WORDS = 180
_CHUNK_OVERLAP = 30


@dataclass
class Chunk:
    text: str
    title: str
    source: str
    slug: str
    url: str | None


def _chunk_text(text: str, size: int = _CHUNK_WORDS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text] if text.strip() else []
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        piece = words[start:start + size]
        if not piece:
            break
        chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


class KnowledgeBase:
    """A small TF-IDF backed retriever. Good enough for a course catalogue
    of a few hundred pages; swap in a vector DB (e.g. Chroma + embeddings)
    later without changing the router code, since everything goes through
    .retrieve() and .get_full_doc()."""

    def __init__(self):
        self._lock = threading.Lock()
        self.chunks: list[Chunk] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None
        # slug -> full concatenated text, for direct course/bundle summarization
        self.full_docs: dict[str, RawDoc] = {}
        # slug -> {"hash": sha256 of the English text this was translated
        # from, "hi": the Hindi translation}. Pre-built once per doc during
        # build() (see _refresh_translations) so a Hindi read/summary of an
        # indexed course/bundle/page never waits on a live Groq translate
        # call - it's already sitting here. Rebuilt automatically whenever
        # a doc's English text hash changes (edited course content); a doc
        # whose text hasn't changed since the last refresh reuses its
        # existing translation instead of paying for a re-translate.
        self.translations: dict[str, dict] = {}

    @property
    def path(self) -> str:
        return os.path.join(settings.data_dir, "kb.joblib")

    def build(self) -> dict:
        docs = build_all_docs()
        chunks: list[Chunk] = []
        full_docs: dict[str, RawDoc] = {}

        courses = bundles = pages = 0
        for doc in docs:
            full_docs[doc.slug] = doc
            if doc.source == "course":
                courses += 1
            elif doc.source == "bundle":
                bundles += 1
            else:
                pages += 1
            for piece in _chunk_text(doc.text):
                chunks.append(Chunk(text=piece, title=doc.title, source=doc.source, slug=doc.slug, url=doc.url))

        vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform([c.text for c in chunks]) if chunks else None

        translations = self._refresh_translations(full_docs)

        with self._lock:
            self.chunks = chunks
            self.vectorizer = vectorizer
            self.matrix = matrix
            self.full_docs = full_docs
            self.translations = translations

        self.save()
        return {
            "courses_indexed": courses,
            "bundles_indexed": bundles,
            "pages_indexed": pages,
            "chunks_indexed": len(chunks),
            "translations_reused": sum(1 for slug in translations if self._was_reused(slug, translations)),
            "translations_regenerated": sum(1 for slug in translations if not self._was_reused(slug, translations)),
        }

    def _was_reused(self, slug: str, translations: dict) -> bool:
        return translations.get(slug, {}).get("reused", False)

    def _refresh_translations(self, full_docs: dict[str, RawDoc]) -> dict[str, dict]:
        """Pre-translates every indexed doc's full text into Hindi, once,
        here at ingest time - not on-demand per request. A doc whose
        English text is byte-identical to what it was last time this ran
        (same sha256 hash) reuses its existing Hindi translation instead of
        calling Groq again; only genuinely new/changed docs get translated.
        This is what makes /ingest/refresh double as "keep the Hindi cache
        in sync with content changes" - no separate cron/hook needed."""
        # Local import avoids a circular import at module load time
        # (app.services.llm doesn't import knowledge_base, but importing it
        # up top here would run llm.py's Groq client construction before
        # settings are fully ready in some startup orderings).
        from app.services import llm

        previous = self.translations  # whatever was loaded from disk / the prior build

        def _translate_one(item: tuple[str, RawDoc]) -> tuple[str, dict]:
            slug, doc = item
            text_hash = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
            cached = previous.get(slug)
            if cached and cached.get("hash") == text_hash:
                return slug, {"hash": text_hash, "hi": cached.get("hi", ""), "reused": True}
            hi_text = llm.translate(doc.text, "hi") if doc.text.strip() else ""
            return slug, {"hash": text_hash, "hi": hi_text, "reused": False}

        items = list(full_docs.items())
        if not items:
            return {}
        # Docs are independent Groq calls (when they need one at all), so
        # they're dispatched in parallel rather than one at a time - this
        # is what keeps a full-catalogue refresh from taking N times as
        # long as translating a single course. Capped at 2 concurrent
        # workers (was 6) - each worker can itself fire multiple requests
        # per doc (llm.translate() chunks long text internally), and
        # Google Translate's unofficial free-tier limit is ~5 requests/sec,
        # so anything higher here was reliably tripping "You made too many
        # requests to the server" and silently falling back to
        # untranslated text for those chunks.
        with ThreadPoolExecutor(max_workers=min(2, len(items))) as pool:
            results = list(pool.map(_translate_one, items))
        return dict(results)

    def save(self):
        os.makedirs(settings.data_dir, exist_ok=True)
        joblib.dump({
            "chunks": self.chunks,
            "vectorizer": self.vectorizer,
            "matrix": self.matrix,
            "full_docs": self.full_docs,
            "translations": self.translations,
        }, self.path)

    def load(self) -> bool:
        if not os.path.exists(self.path):
            return False
        state = joblib.load(self.path)
        with self._lock:
            self.chunks = state["chunks"]
            self.vectorizer = state["vectorizer"]
            self.matrix = state["matrix"]
            self.full_docs = state["full_docs"]
            # Older kb.joblib files saved before this cache existed won't
            # have this key - fall back to empty so load() doesn't crash on
            # them (build() will simply translate everything fresh on the
            # next /ingest/refresh instead of reusing anything).
            self.translations = state.get("translations", {})
        return True

    def retrieve(self, query: str, top_k: int = 5, restrict_to_slug: str | None = None) -> list[Chunk]:
        if not self.chunks or self.vectorizer is None or self.matrix is None:
            return []
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.matrix)[0]

        if restrict_to_slug:
            # Only rank chunks belonging to one course/bundle/page - used to
            # keep a plain Q&A scoped to "this course" instead of searching
            # every course on the site when the user is clearly on one
            # course's page already.
            candidate_idx = [i for i, c in enumerate(self.chunks) if c.slug == restrict_to_slug]
            if not candidate_idx:
                return []
            ranked = sorted(candidate_idx, key=lambda i: sims[i], reverse=True)[:top_k]
        else:
            ranked = sims.argsort()[::-1][:top_k]

        return [self.chunks[i] for i in ranked if sims[i] > 0]

    def get_full_doc(self, slug: str) -> RawDoc | None:
        return self.full_docs.get(slug)

    def get_full_text(self, slug: str, language: str) -> str | None:
        """Full text of an indexed doc in the requested language - English
        straight from full_docs, Hindi from the pre-built translations
        cache (falling back to a live translate only if that doc somehow
        wasn't covered by the last /ingest/refresh, e.g. it was added and
        this got called before a refresh ran). Callers that have a slug
        (an indexed course/bundle/page) should always go through this
        instead of calling llm.translate() directly, so they get the
        instant cached path."""
        doc = self.full_docs.get(slug)
        if not doc:
            return None
        if language != "hi":
            return doc.text
        cached = self.translations.get(slug)
        if cached and cached.get("hi"):
            return cached["hi"]
        from app.services import llm  # local import, see _refresh_translations
        return llm.translate(doc.text, "hi")


# single shared instance used across the app
kb = KnowledgeBase()