from typing import Literal, Optional
from pydantic import BaseModel, Field

Language = Literal["auto", "en", "hi"]


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Language = "auto"
    page_url: Optional[str] = None       # current page the widget is embedded on, if any
    page_content: Optional[str] = None   # live text scraped from the DOM of that page by the widget


class SourceRef(BaseModel):
    title: str
    url: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    language: Literal["en", "hi"]
    sources: list[SourceRef] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)


class SummarizeRequest(BaseModel):
    course_slug: Optional[str] = None
    bundle_slug: Optional[str] = None
    text: Optional[str] = None
    length: Literal["short", "long"] = "short"
    language: Language = "auto"
    # The user's own request text (e.g. "summarize this in Hindi"). Used to
    # resolve language="auto" - falls back to `text` if omitted, but that
    # means "auto" ends up detecting the *content's* language rather than
    # what the user asked for, which is almost always English here.
    message: Optional[str] = None
    # Explicit word target (e.g. "summarize in 100 words"). When omitted,
    # it's auto-detected from `message` if present; otherwise `length` is
    # used as before.
    word_count: Optional[int] = None


class SummarizeResponse(BaseModel):
    summary: str
    length: Literal["short", "long"]
    language: Literal["en", "hi"]
    source_title: Optional[str] = None


class QAItem(BaseModel):
    question: str
    answer: str


class SuggestQuestionsRequest(BaseModel):
    topic: Optional[str] = None
    course_slug: Optional[str] = None
    text: Optional[str] = None   # raw page/module text, same convention as SummarizeRequest.text
    count: int = 5
    language: Language = "auto"


class SuggestQuestionsResponse(BaseModel):
    questions: list[QAItem]
    language: Literal["en", "hi"]


class TTSRequest(BaseModel):
    text: str
    language: Language = "auto"
    voice: Optional[str] = None


class IngestResponse(BaseModel):
    courses_indexed: int
    bundles_indexed: int
    pages_indexed: int
    chunks_indexed: int


class STTResponse(BaseModel):
    transcript: str
    language: Literal["en", "hi"]


class VoiceChatResponse(BaseModel):
    transcript: str
    reply: str
    language: Literal["en", "hi"]
    sources: list[SourceRef] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    audio_base64: str | None = None
    audio_mime: str = "audio/mpeg"