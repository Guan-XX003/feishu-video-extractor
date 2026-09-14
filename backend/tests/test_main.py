from fastapi.testclient import TestClient

from pathlib import Path

from app import main
from yt_dlp.utils import DownloadError

from app.main import (
    WorkerResult,
    app,
    build_download_options,
    create_download_ticket,
    download_error_detail,
    dispatch_worker_job,
    finish_worker_job,
    claim_worker_job,
    is_allowed_host,
    is_local_worker_host,
    media_type_for_filename,
    read_download_ticket,
    resolve_cookies_file,
    safe_filename,
    validate_production_settings,
)


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["max_audio_source_size_mb"] == 500
    assert response.json()["worker_enabled"] is False


def test_domain_allowlist() -> None:
    assert is_allowed_host("www.douyin.com") is True
    assert is_allowed_host("v.douyin.com") is True
    assert is_allowed_host("example.com") is False
    assert is_allowed_host("127.0.0.1") is False


def test_worker_domain_routing(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "worker_enabled", True)
    monkeypatch.setattr(main.settings, "worker_domains", "douyin.com,iesdouyin.com")
    assert is_local_worker_host("v.douyin.com") is True
    assert is_local_worker_host("www.bilibili.com") is False


def test_rejects_unlisted_domain_before_download() -> None:
    response = client.post("/api/extract", json={"url": "https://example.com/video"})
    assert response.status_code == 400
    assert "白名单" in response.json()["detail"]


def test_extract_endpoint_is_disabled_in_production(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "require_base_signature", True)
    response = client.post(
        "/api/extract",
        json={"url": "https://www.douyin.com/video/123"},
    )
    assert response.status_code == 403
    assert "字段捷径" in response.json()["detail"]


def test_safe_filename() -> None:
    assert safe_filename("测试 视频 / 01") == "测试-视频-01"
    assert media_type_for_filename("demo.m4a") == "audio/mp4"


def test_download_ticket_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "prepared_video_dir", str(tmp_path))
    prepared = tmp_path / "abcdefghijklmnopqrstuvwx.mp4"
    prepared.write_bytes(b"video")
    path, filename = read_download_ticket(
        create_download_ticket(prepared.name, "demo-video.mp4")
    )
    assert path == prepared
    assert filename == "demo-video.mp4"


def test_ticket_endpoint_returns_fetchable_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "prepared_video_dir", str(tmp_path / "cache"))

    def fake_download(_url: str, media_type: str) -> tuple[Path, Path, str]:
        assert media_type == "video"
        download_dir = tmp_path / "download"
        download_dir.mkdir()
        file_path = download_dir / "demo.mp4"
        file_path.write_bytes(b"prepared-video")
        return file_path, download_dir, "demo-video.mp4"

    monkeypatch.setattr(main, "download_media", fake_download)
    response = client.post("/api/tickets", json={"url": "https://www.douyin.com/video/123"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["download_url"].startswith("http://localhost:8000/api/download/")
    assert payload["filename"] == "demo-video.mp4"
    assert payload["content_length"] == len(b"prepared-video")

    download_response = client.get(payload["download_url"])
    assert download_response.status_code == 200
    assert download_response.content == b"prepared-video"
    assert download_response.headers["content-length"] == str(len(b"prepared-video"))
    assert download_response.headers["content-type"].startswith("video/mp4")


def test_ticket_endpoint_can_use_windows_worker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "prepared_video_dir", str(tmp_path / "cache"))
    monkeypatch.setattr(main.settings, "worker_enabled", True)
    monkeypatch.setattr(main.settings, "worker_domains", "douyin.com")
    prepared = Path(main.settings.prepared_video_dir)
    prepared.mkdir(parents=True)
    file_id = "abcdefghijklmnopqrstuvwx.mp4"
    (prepared / file_id).write_bytes(b"windows-video")

    async def fake_dispatch(_url: str, media_type: str, log_id: str) -> WorkerResult:
        assert media_type == "video"
        assert log_id == "worker-log"
        return WorkerResult(file_id, "windows-video.mp4", len(b"windows-video"))

    monkeypatch.setattr(main, "dispatch_worker_job", fake_dispatch)
    response = client.post(
        "/api/tickets",
        json={"url": "https://www.douyin.com/video/123", "log_id": "worker-log"},
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "windows-video.mp4"
    assert client.get(response.json()["download_url"]).content == b"windows-video"


def test_worker_claim_requires_auth(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "worker_token", "x" * 32)
    response = client.post("/api/worker/claim", json={"worker_id": "test-worker"})
    assert response.status_code == 401


def test_worker_job_round_trip(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "worker_job_timeout_seconds", 5)
    monkeypatch.setattr(main.settings, "worker_claim_wait_seconds", 1)
    main.worker_jobs.clear()
    while not main.worker_queue.empty():
        main.worker_queue.get_nowait()

    async def scenario() -> None:
        dispatched = __import__("asyncio").create_task(
            dispatch_worker_job("https://v.douyin.com/demo/", "video", "log-worker")
        )
        job = await claim_worker_job("windows-test")
        assert job is not None
        assert job.claimed_by == "windows-test"
        finish_worker_job(job, WorkerResult("abcdefghijklmnopqrstuvwx.mp4", "demo.mp4", 5))
        result = await dispatched
        assert result.filename == "demo.mp4"
        assert result.content_length == 5

    __import__("asyncio").run(scenario())


def test_audio_ticket_returns_audio_attachment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "prepared_video_dir", str(tmp_path / "cache"))

    def fake_download(_url: str, media_type: str) -> tuple[Path, Path, str]:
        assert media_type == "audio"
        download_dir = tmp_path / "audio-download"
        download_dir.mkdir()
        file_path = download_dir / "demo.m4a"
        file_path.write_bytes(b"prepared-audio")
        return file_path, download_dir, "demo-audio.m4a"

    monkeypatch.setattr(main, "download_media", fake_download)
    response = client.post(
        "/api/tickets",
        json={"url": "https://www.douyin.com/video/123", "media_type": "audio"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "demo-audio.m4a"

    download_response = client.get(payload["download_url"])
    assert download_response.status_code == 200
    assert download_response.content == b"prepared-audio"
    assert download_response.headers["content-type"].startswith("audio/mp4")


def test_audio_download_options_extract_m4a(tmp_path: Path) -> None:
    options = build_download_options(tmp_path, "audio")
    assert options["format"] == "bestaudio/best"
    assert options["max_filesize"] == 500 * 1024 * 1024
    assert "ffmpeg" in Path(options["ffmpeg_location"]).name
    assert options["postprocessors"] == [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "128",
        }
    ]


def test_rejects_invalid_ticket() -> None:
    response = client.get("/api/download/not-a-ticket")
    assert response.status_code == 400


def test_cookie_error_is_actionable() -> None:
    error = DownloadError("Fresh cookies (not necessarily logged in) are needed")
    assert "COOKIES_FILE" in download_error_detail(error)


def test_production_settings_require_secret(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "require_base_signature", True)
    monkeypatch.setattr(main.settings, "ticket_secret", "change-me-in-production")
    monkeypatch.setattr(main.settings, "expected_pack_id", "")

    try:
        import asyncio

        asyncio.run(validate_production_settings())
    except RuntimeError as error:
        assert "TICKET_SECRET" in str(error)
    else:
        raise AssertionError("生产环境默认密钥应被拒绝")


def test_production_settings_accept_valid_values(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "require_base_signature", True)
    monkeypatch.setattr(main.settings, "ticket_secret", "x" * 32)
    monkeypatch.setattr(main.settings, "expected_pack_id", "")

    import asyncio

    asyncio.run(validate_production_settings())


def test_resolve_cookies_content(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "cookies_content", "# Netscape HTTP Cookie File\n")
    monkeypatch.setattr(main.settings, "cookies_file", "")

    resolved = Path(resolve_cookies_file())
    try:
        assert resolved.read_text(encoding="utf-8") == "# Netscape HTTP Cookie File\n"
        assert resolved.stat().st_mode & 0o077 == 0
    finally:
        resolved.unlink(missing_ok=True)
