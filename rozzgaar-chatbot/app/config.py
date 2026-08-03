from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Rozzgaar API
    rozzgaar_base_url: str = "https://rozzgaar.in/apis"
    rozzgaar_open_key: str = ""

    # Extra static pages to scrape (About / FAQ / etc.)
    static_page_urls: str = "https://rozzgaar.in/,https://rozzgaar.in/courses,https://rozzgaar.in/about,https://rozzgaar.in/contact,https://rozzgaar.in/verify,https://rozzgaar.in/privacy-policy,https://rozzgaar.in/terms,https://rozzgaar.in/refund-policy"


    # Groq LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_stt_model: str = "whisper-large-v3-turbo"

    # Admin
    admin_secret: str = ""

    # CORS - your FRONTEND site's origin(s) (e.g. its own ngrok tunnel while
    # testing locally). Different from public_backend_url below.
    allowed_origins: str = "*"

    # Public URL where THIS backend itself is reachable (this backend's own
    # ngrok tunnel). Injected into static/embed.js's CONFIG.BACKEND_URL when
    # it's served, so the widget always points at the right tunnel - update
    # this in .env whenever ngrok restarts and hands out a new URL, no need
    # to hand-edit embed.js.
    public_backend_url: str = "https://tropical-refocus-exact.ngrok-free.dev"

    # Storage
    data_dir: str = "./data"

    # TTS voices
    tts_voice_hi: str = "hi-IN-SwaraNeural"
    tts_voice_en: str = "en-IN-NeerjaNeural"

    @property
    def static_page_url_list(self) -> list[str]:
        return [u.strip() for u in self.static_page_urls.split(",") if u.strip()]

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
