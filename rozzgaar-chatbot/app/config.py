from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Rozzgaar API
    rozzgaar_base_url: str = ""
    rozzgaar_open_key: str = ""

    # Extra static pages to scrape (About / FAQ / etc.)
    static_page_urls: str = ""

    # Hosts the video-summarize endpoint is allowed to download from
    # (comma separated). /summarize/video fetches whatever URL it's given
    # server-side, so without this allowlist it would be an open SSRF   
    # proxy - any request for a URL whose host isn't in this list (or a
    # subdomain of one) is rejected with 400 before any network call.
    allowed_video_domains: str = ""


    # Groq LLM
    groq_api_key: str = ""
    groq_model: str = ""
    groq_stt_model: str = ""


    # Admin
    admin_secret: str = ""

    # CORS - your FRONTEND site's origin(s) (e.g. its own ngrok tunnel while
    # testing locally). Different from public_backend_url below.
    allowed_origins: str = ""

    # Public URL where THIS backend itself is reachable (this backend's own
    # ngrok tunnel). Injected into static/embed.js's CONFIG.BACKEND_URL when
    # it's served, so the widget always points at the right tunnel - update
    # this in .env whenever ngrok restarts and hands out a new URL, no need
    # to hand-edit embed.js.
    public_backend_url: str = ""


    # Storage
    data_dir: str = ""

    # TTS voices
    tts_voice_hi: str = ""
    tts_voice_en: str = ""

    @property
    def static_page_url_list(self) -> list[str]:
        return [u.strip() for u in self.static_page_urls.split(",") if u.strip()]

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_video_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_video_domains.split(",") if d.strip()]


settings = Settings()