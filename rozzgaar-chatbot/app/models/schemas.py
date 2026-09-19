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
    # Plain follow-up prompts the visitor can tap to ASK (each one gets
    # sent back through /chat/ as their next message).
    suggested_questions: list[str] = Field(default_factory=list)
    # Multiple-choice practice questions for the visitor to ANSWER, used
    # by the "quiz me" / "give me questions" intent. Kept separate from
    # suggested_questions because the two are tapped for opposite
    # reasons and the widget renders them differently.
    mcq_questions: list["QAItem"] = Field(default_factory=list)


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


class VideoSummarizeRequest(BaseModel):
    # The lecture video's direct URL (the <source src="..."> the widget
    # already reads off the page - see static/embed.js getActiveVideoUrl()).
    # Only URLs on an allow-listed host are accepted server-side (see
    # settings.allowed_video_domain_list) - this is fetched server-side,
    # so an arbitrary URL here would otherwise be an SSRF vector.
    video_url: str
    length: Literal["short", "long"] = "short"
    language: Language = "auto"
    message: Optional[str] = None
    # Optional chapter/module title from the page (e.g. .viewer-title's
    # text) purely for a nicer source_title in the response - never used
    # to locate the video itself.
    module_title: Optional[str] = None
    word_count: Optional[int] = None


class VideoSummarizeResponse(BaseModel):
    summary: str
    length: Literal["short", "long"]
    language: Literal["en", "hi"]
    source_title: Optional[str] = None
    # Whether this transcript came from the on-disk cache (near-instant)
    # or was just freshly downloaded+transcribed (can take a while) - lets
    # the widget show/skip a "this may take a minute" hint appropriately
    # on repeat requests for the same video.
    transcript_cached: bool = False


class QAItem(BaseModel):
    question: str
    # `answer` is the explanation of why the correct option is right.
    answer: str
    # Multiple-choice payload. Both fields stay optional so an item the
    # model returned without usable options still round-trips as a plain
    # question/answer pair (the widget renders either shape), and so any
    # existing client reading only question/answer keeps working.
    options: list[str] = []
    correct_index: Optional[int] = None


class SuggestQuestionsRequest(BaseModel):
    topic: Optional[str] = None
    course_slug: Optional[str] = None
    text: Optional[str] = None   # raw page/module text, same convention as SummarizeRequest.text
    count: int = 5
    language: Language = "auto"


class SuggestQuestionsResponse(BaseModel):
    questions: list[QAItem]
    language: Literal["en", "hi"]


class TranslateBatchRequest(BaseModel):
    # Each string is one DOM text node's content, in DOM order. The response
    # returns translations in the exact same order/length so the widget can
    # zip them straight back onto the nodes that produced them - this is
    # what makes it a real "translate in place", not a rebuild of the page.
    texts: list[str]
    language: Language = "auto"
    # The user's own language pick, if any (e.g. from the langGate button) -
    # used the same way SummarizeRequest.message is, to resolve "auto".
    message: Optional[str] = None


class TranslateBatchResponse(BaseModel):
    texts: list[str]
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
    # How many docs' Hindi translation was reused unchanged (content hash
    # matched the last refresh) vs. actually regenerated via Groq this run.
    translations_reused: int = 0
    translations_regenerated: int = 0


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


# QAItem is defined below ChatResponse, so its forward reference has to
# be resolved once the whole module is loaded.
ChatResponse.model_rebuild()