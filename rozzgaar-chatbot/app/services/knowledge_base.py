import os
import threading
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

        with self._lock:
            self.chunks = chunks
            self.vectorizer = vectorizer
            self.matrix = matrix
            self.full_docs = full_docs

        self.save()
        return {
            "courses_indexed": courses,
            "bundles_indexed": bundles,
            "pages_indexed": pages,
            "chunks_indexed": len(chunks),
        }

    def save(self):
        os.makedirs(settings.data_dir, exist_ok=True)
        joblib.dump({
            "chunks": self.chunks,
            "vectorizer": self.vectorizer,
            "matrix": self.matrix,
            "full_docs": self.full_docs,
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


# single shared instance used across the app
kb = KnowledgeBase()
