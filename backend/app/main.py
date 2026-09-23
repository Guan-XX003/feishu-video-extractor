from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Union
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.background import BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from imageio_ffmpeg import get_ffmpeg_exe
from pydantic import BaseModel, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from websockets.sync.client import connect as websocket_connect


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    allowed_origins: str = "http://localhost:5173,http://localhost:4173"
    max_video_size_mb: int = 30
    max_audio_source_size_mb: int = 500
    download_concurrency: int = 2
    public_base_url: str = "http://localhost:8000"
    ticket_secret: str = "change-me-in-production"
    ticket_ttl_seconds: int = 600
    prepared_video_dir: str = "/tmp/feishu-video-extractor-cache"
    cookies_file: str = ""
    cookies_content: str = ""
    cookies_from_browser: str = ""
    cookies_browser_profile: str = ""
    browser_user_agent: str = ""
    browser_debug_url: str = ""
    browser_warmup_seconds: float = 3.0
    require_base_signature: bool = False
    expected_pack_id: str = ""
    worker_enabled: bool = False
    worker_token: str = ""
    worker_job_timeout_seconds: int = 90
    worker_claim_wait_seconds: int = 20
    worker_heartbeat_ttl_seconds: int = 60
    worker_domains: str = "douyin.com,iesdouyin.com"
    allowed_video_domains: str = (
        "douyin.com,iesdouyin.com,tiktok.com,xiaohongshu.com,xhslink.com,"
        "bilibili.com,b23.tv,kuaishou.com"
    )

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def domains(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_video_domains.split(",") if item.strip()}

    @property
    def local_worker_domains(self) -> set[str]:
        return {item.strip().lower() for item in self.worker_domains.split(",") if item.strip()}

    @property
    def expected_pack_ids(self) -> set[str]:
        """允许一个后端服务服务多个已发布的字段捷径。"""
        return {item.strip() for item in self.expected_pack_id.split(",") if item.strip()}


settings = Settings()
download_semaphore = asyncio.Semaphore(max(1, settings.download_concurrency))
browser_warm_lock = threading.Lock()
logger = logging.getLogger("feishu_video_extractor")
AUDIO_BITRATE_KBPS = 32


@dataclass
class WorkerResult:
    file_id: str
    filename: str
    content_length: int


@dataclass
class WorkerJob:
    job_id: str
    completion_token: str
    url: str
    media_type: str
    log_id: str
    created_at: float
    result: asyncio.Future[WorkerResult]
    claimed_by: str = ""


class WorkerUnavailableError(RuntimeError):
    pass


class WorkerJobError(RuntimeError):
    pass


worker_queue: asyncio.Queue[str] = asyncio.Queue()
worker_jobs: dict[str, WorkerJob] = {}
worker_last_seen_at = 0.0

app = FastAPI(title="Feishu Video Extractor", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "X-Video-Source"],
)


@app.on_event("startup")
async def validate_production_settings() -> None:
    if settings.require_base_signature:
        if settings.ticket_secret == "change-me-in-production" or len(settings.ticket_secret) < 32:
            raise RuntimeError("生产环境必须配置至少 32 个字符的 TICKET_SECRET")
    if settings.worker_enabled and len(settings.worker_token) < 32:
        raise RuntimeError("启用本地下载助手时必须配置至少 32 个字符的 WORKER_TOKEN")
    if settings.cookies_from_browser:
        supported_browsers = {"brave", "chrome", "chromium", "edge", "firefox", "safari", "vivaldi"}
        if settings.cookies_from_browser.lower() not in supported_browsers:
            raise RuntimeError("COOKIES_FROM_BROWSER 不是受支持的浏览器")
    if settings.browser_debug_url:
        debug_url = urlparse(settings.browser_debug_url)
        if debug_url.scheme != "http" or debug_url.hostname not in {"127.0.0.1", "localhost"}:
            raise RuntimeError("BROWSER_DEBUG_URL 必须是本机 HTTP 地址")


def resolve_cookies_file() -> str:
    if settings.cookies_content.strip():
        cookie_path = Path("/tmp/feishu-video-extractor-cookies.txt")
        cookie_path.write_text(settings.cookies_content, encoding="utf-8")
        cookie_path.chmod(0o600)
        return str(cookie_path)
    return settings.cookies_file


def resolve_cookie_options() -> dict[str, Any]:
    """返回 yt-dlp Cookie 配置。

    本机浏览器模式优先于静态 cookies.txt，避免旧的
    COOKIES_CONTENT 残留值遮蔽 Mac 上已刷新的登录状态。
    """
    browser = settings.cookies_from_browser.strip().lower()
    if browser:
        profile: str | None = None
        if settings.cookies_browser_profile.strip():
            profile_path = Path(settings.cookies_browser_profile).expanduser().resolve()
            if not profile_path.is_dir():
                raise RuntimeError("配置的浏览器 Cookie Profile 目录不存在")
            profile = str(profile_path)
        return {"cookiesfrombrowser": (browser, profile, None, None)}

    cookies_file = resolve_cookies_file()
    if not cookies_file:
        return {}
    cookies_path = Path(cookies_file).expanduser()
    if not cookies_path.is_file():
        raise RuntimeError("配置的抖音 Cookie 文件不存在")
    return {"cookiefile": str(cookies_path)}


def cookie_source_name() -> str:
    if settings.cookies_from_browser.strip():
        return "browser"
    if settings.cookies_content.strip() or settings.cookies_file.strip():
        return "file"
    return "none"


def browser_http_headers(url: str = "") -> dict[str, str]:
    browser = settings.cookies_from_browser.strip().lower()
    if not browser:
        return {}

    user_agent = settings.browser_user_agent.strip()
    if not user_agent and sys.platform == "darwin":
        browser_binaries = {
            "edge": Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            "chrome": Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        }
        binary = browser_binaries.get(browser)
        if binary and binary.is_file():
            try:
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
                match = re.search(r"(\d+(?:\.\d+){3})", result.stdout)
                if match:
                    version = match.group(1)
                    product = f" Edg/{version}" if browser == "edge" else ""
                    user_agent = (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} "
                        f"Safari/537.36{product}"
                    )
            except (OSError, subprocess.SubprocessError):
                logger.warning("browser_version_detection_failed browser=%s", browser)

    headers: dict[str, str] = {}
    hostname = (urlparse(url).hostname or "").lower()
    if hostname == "douyin.com" or hostname.endswith(".douyin.com"):
        headers.update(
            {
                "Referer": "https://www.douyin.com/",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def browser_binary_path(browser: str) -> Path | None:
    if sys.platform != "darwin":
        return None
    return {
        "edge": Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        "chrome": Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    }.get(browser)


def browser_debug_request(path: str, method: str = "GET") -> Any:
    base_url = settings.browser_debug_url.strip().rstrip("/")
    if not base_url:
        raise RuntimeError("未配置浏览器调试地址")
    request = UrlRequest(f"{base_url}{path}", method=method)
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def browser_debug_evaluate(websocket_url: str, expression: str) -> Any:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            with websocket_connect(
                websocket_url, origin=None, open_timeout=5, close_timeout=2
            ) as websocket:
                websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "Runtime.evaluate",
                            "params": {"expression": expression, "returnByValue": True},
                        }
                    )
                )
                response = json.loads(websocket.recv(timeout=5))
            return response.get("result", {}).get("result", {}).get("value")
        except Exception as error:
            last_error = error
            time.sleep(0.25)
    raise RuntimeError("无法读取专用浏览器页面") from last_error


def resolve_browser_target_url(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if hostname != "v.douyin.com":
        return url
    request = UrlRequest(url, headers=browser_http_headers("https://www.douyin.com/"))
    try:
        with urlopen(request, timeout=10) as response:
            resolved = response.geturl()
        if (urlparse(resolved).hostname or "").lower().endswith("douyin.com"):
            return resolved
    except (OSError, URLError, ValueError):
        pass
    return url


def ensure_browser_debug_endpoint() -> bool:
    if not settings.browser_debug_url.strip():
        return False
    try:
        browser_debug_request("/json/version")
        return True
    except (OSError, RuntimeError, URLError, ValueError, json.JSONDecodeError):
        pass

    browser = settings.cookies_from_browser.strip().lower()
    binary = browser_binary_path(browser)
    profile = settings.cookies_browser_profile.strip()
    if not binary or not binary.is_file() or not profile:
        return False

    debug_url = urlparse(settings.browser_debug_url)
    if not debug_url.port:
        return False
    profile_path = Path(profile).expanduser().resolve()
    profile_root = profile_path.parent if profile_path.name == "Default" else profile_path
    try:
        subprocess.Popen(
            [
                str(binary),
                f"--user-data-dir={profile_root}",
                f"--profile-directory={profile_path.name}",
                "--no-first-run",
                "--headless=new",
                "--disable-gpu",
                f"--remote-debugging-address={debug_url.hostname}",
                f"--remote-debugging-port={debug_url.port}",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        logger.warning("browser_debug_launch_failed browser=%s", browser)
        return False

    for _ in range(20):
        time.sleep(0.25)
        try:
            browser_debug_request("/json/version")
            return True
        except (OSError, RuntimeError, URLError, ValueError, json.JSONDecodeError):
            continue
    return False


def warm_browser_session(url: str) -> bool:
    """让专用浏览器访问目标页，刷新抖音的动态风控 Cookie。"""
    if not settings.browser_debug_url.strip():
        return False
    with browser_warm_lock:
        if not ensure_browser_debug_endpoint():
            logger.warning("browser_warmup_unavailable")
            return False
        target_id = ""
        try:
            target = browser_debug_request(f"/json/new?{quote(url, safe=':/?=&')}", method="PUT")
            target_id = str(target.get("id") or "") if isinstance(target, dict) else ""
            time.sleep(max(0.5, settings.browser_warmup_seconds))
            logger.info("browser_warmup_complete host=%s", urlparse(url).hostname or "")
            return True
        except (OSError, RuntimeError, URLError, ValueError, json.JSONDecodeError):
            logger.warning("browser_warmup_failed host=%s", urlparse(url).hostname or "")
            return False
        finally:
            if target_id:
                try:
                    browser_debug_request(f"/json/close/{target_id}")
                except (OSError, RuntimeError, URLError, ValueError, json.JSONDecodeError):
                    pass


def browser_media_sources(url: str) -> dict[str, Any]:
    """从专用浏览器已通过风控的页面读取实际媒体地址。"""
    if not settings.browser_debug_url.strip():
        raise RuntimeError("未配置浏览器回退通道")
    with browser_warm_lock:
        if not ensure_browser_debug_endpoint():
            raise RuntimeError("专用浏览器不可用")
        target_id = ""
        try:
            target_url = resolve_browser_target_url(url)
            target = browser_debug_request(
                f"/json/new?{quote(target_url, safe=':/?=&')}", method="PUT"
            )
            if not isinstance(target, dict) or not target.get("webSocketDebuggerUrl"):
                raise RuntimeError("无法连接专用浏览器页面")
            target_id = str(target.get("id") or "")
            expression = """JSON.stringify({
                title: document.title.replace(/\\s+-\\s+抖音$/, ''),
                currentSrc: document.querySelector('video')?.currentSrc || '',
                resources: performance.getEntriesByType('resource')
                    .map(entry => entry.name)
                    .filter(name => name.includes('douyinvod.com'))
            })"""
            deadline = time.monotonic() + max(5.0, settings.browser_warmup_seconds + 7.0)
            while time.monotonic() < deadline:
                value = browser_debug_evaluate(str(target["webSocketDebuggerUrl"]), expression)
                payload = json.loads(value) if isinstance(value, str) else {}
                if isinstance(payload, dict):
                    resources = unique_urls(payload.get("resources"))
                    has_dash = any("media-video-" in item for item in resources) and any(
                        "media-audio-" in item for item in resources
                    )
                    if has_dash or str(payload.get("currentSrc") or "").startswith("https://"):
                        return payload
                time.sleep(0.5)
            raise RuntimeError("专用浏览器页面未加载出媒体资源")
        finally:
            if target_id:
                try:
                    browser_debug_request(f"/json/close/{target_id}")
                except (OSError, RuntimeError, URLError, ValueError, json.JSONDecodeError):
                    pass


def unique_urls(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.startswith("https://") and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def download_browser_resource(url: str, destination: Path, max_bytes: int) -> None:
    headers = browser_http_headers("https://www.douyin.com/")
    headers["Referer"] = "https://www.douyin.com/"
    request = UrlRequest(url, headers=headers)
    total = 0
    with urlopen(request, timeout=30) as response, destination.open("wb") as output:
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length and content_length > max_bytes:
            raise RuntimeError("浏览器媒体源超过大小限制")
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError("浏览器媒体源超过大小限制")
            output.write(chunk)


def download_douyin_from_browser(
    url: str, media_type: str, temp_dir: Path
) -> tuple[Path, str]:
    payload = browser_media_sources(url)
    resources = unique_urls(payload.get("resources"))
    video_urls = [item for item in resources if "media-video-" in item]
    audio_urls = [item for item in resources if "media-audio-" in item]
    current_src = str(payload.get("currentSrc") or "")
    title = safe_filename(payload.get("title"), fallback="douyin-video")
    final_limit = settings.max_video_size_mb * 1024 * 1024

    if media_type == "audio":
        if not audio_urls:
            raise RuntimeError("浏览器页面未找到音频流")
        source = temp_dir / "browser-audio-source.mp4"
        output = temp_dir / "browser-audio.m4a"
        download_browser_resource(
            audio_urls[-1], source, settings.max_audio_source_size_mb * 1024 * 1024
        )
        subprocess.run(
            [
                get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(source),
                "-vn", "-ac", "1", "-c:a", "aac", "-b:a", f"{AUDIO_BITRATE_KBPS}k", str(output),
            ],
            capture_output=True,
            check=True,
        )
        if output.stat().st_size > final_limit:
            raise RuntimeError(f"音频超过 {settings.max_video_size_mb} MB 限制")
        return output, f"{title}.m4a"

    if video_urls and audio_urls:
        video_source = temp_dir / "browser-video-source.mp4"
        audio_source = temp_dir / "browser-audio-source.m4a"
        output = temp_dir / "browser-video.mp4"
        download_browser_resource(video_urls[-1], video_source, final_limit)
        download_browser_resource(audio_urls[-1], audio_source, final_limit)
        subprocess.run(
            [
                get_ffmpeg_exe(), "-y", "-loglevel", "error",
                "-i", str(video_source), "-i", str(audio_source),
                "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(output),
            ],
            capture_output=True,
            check=True,
        )
    elif current_src.startswith("https://"):
        output = temp_dir / "browser-video.mp4"
        download_browser_resource(current_src, output, final_limit)
    else:
        raise RuntimeError("浏览器页面未找到视频流")

    if output.stat().st_size > final_limit:
        raise RuntimeError(f"视频超过 {settings.max_video_size_mb} MB 限制")
    return output, f"{title}.mp4"


class ExtractRequest(BaseModel):
    url: HttpUrl
    media_type: Literal["video", "audio"] = "video"


class TicketRequest(BaseModel):
    url: HttpUrl
    media_type: Literal["video", "audio"] = "video"
    base_signature: Optional[str] = None
    pack_id: Optional[str] = None
    log_id: Optional[str] = None


class WorkerClaimRequest(BaseModel):
    worker_id: str


class WorkerFailureRequest(BaseModel):
    message: str


BASE_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxKNV23rheRvtUKDMJPOW
GhUt+W25k63X4Q1QYhztPlobF2VNIDR6eHVFUDP22aytzVguisJ/GaOKZ7FJDKis
9YvMUiCIFnfu1LWB4b4pa4ajmPk/Rr9DMSLz6frKRP0QqirWFe7t+u0K0nzzPe3/
a5ScSmJwYACmayQfLZFTFjyL0Z1SQFZM6pZ1J1w9ETxWI0NrpkMU7eqzVGvhf+OO
dmxsXrHARWa1Ldm3WqPCF3k5jKuPG7s0zB+iuBHamSitZ7ktBf0mzBBjsAjKQll1
kmdjryGbKX5sLXhEgOb5ndakYeA0Oy7vve2Hm78kH5MtaSv6MfNVjm5ForMjPAPQ
BQIDAQAB
-----END PUBLIC KEY-----"""


def is_allowed_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(normalized)
        return False
    except ValueError:
        pass
    return any(normalized == domain or normalized.endswith(f".{domain}") for domain in settings.domains)


def validate_source_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="仅支持 http/https 分享链接")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="链接不能包含用户名或密码")
    if not is_allowed_host(parsed.hostname):
        raise HTTPException(status_code=400, detail="当前链接域名不在允许的视频平台白名单中")


def is_local_worker_host(hostname: str | None) -> bool:
    if not settings.worker_enabled or not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    return any(
        normalized == domain or normalized.endswith(f".{domain}")
        for domain in settings.local_worker_domains
    )


def verify_worker_authorization(authorization: str | None) -> None:
    expected = f"Bearer {settings.worker_token}"
    if not settings.worker_token or not authorization or not secrets.compare_digest(
        authorization, expected
    ):
        raise HTTPException(status_code=401, detail="本地下载助手鉴权失败")


def require_worker_job(job_id: str, completion_token: str | None) -> WorkerJob:
    job = worker_jobs.get(job_id)
    if not job or not completion_token or not secrets.compare_digest(
        completion_token, job.completion_token
    ):
        raise HTTPException(status_code=404, detail="下载任务不存在或已经失效")
    return job


async def dispatch_worker_job(
    url: str,
    media_type: str,
    log_id: str,
) -> WorkerResult:
    loop = asyncio.get_running_loop()
    job_id = secrets.token_urlsafe(18)
    job = WorkerJob(
        job_id=job_id,
        completion_token=secrets.token_urlsafe(32),
        url=url,
        media_type=media_type,
        log_id=log_id,
        created_at=time.time(),
        result=loop.create_future(),
    )
    worker_jobs[job_id] = job
    await worker_queue.put(job_id)
    logger.info("worker_job_queued log_id=%s job_id=%s media_type=%s", log_id, job_id, media_type)
    try:
        return await asyncio.wait_for(
            asyncio.shield(job.result),
            timeout=max(5, settings.worker_job_timeout_seconds),
        )
    except asyncio.TimeoutError as error:
        if not job.result.done():
            job.result.cancel()
        logger.warning("worker_job_timeout log_id=%s job_id=%s", log_id, job_id)
        raise WorkerUnavailableError("本地下载助手离线或处理超时，请确认 Windows 下载节点在线") from error
    finally:
        worker_jobs.pop(job_id, None)


async def claim_worker_job(worker_id: str) -> WorkerJob | None:
    global worker_last_seen_at
    worker_last_seen_at = time.time()
    deadline = time.monotonic() + max(0, settings.worker_claim_wait_seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            job_id = await asyncio.wait_for(worker_queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        job = worker_jobs.get(job_id)
        if not job or job.result.done() or job.claimed_by:
            continue
        job.claimed_by = worker_id
        logger.info(
            "worker_job_claimed log_id=%s job_id=%s worker_id=%s",
            job.log_id,
            job.job_id,
            safe_filename(worker_id, fallback="worker"),
        )
        return job


def finish_worker_job(job: WorkerJob, result: WorkerResult) -> None:
    if not job.result.done():
        job.result.set_result(result)


def fail_worker_job(job: WorkerJob, message: str) -> None:
    if not job.result.done():
        job.result.set_exception(WorkerJobError(message[:500]))


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_base_signature(signature: str | None, request_pack_id: str | None) -> None:
    if not settings.require_base_signature and not settings.expected_pack_id:
        return
    if not signature:
        raise HTTPException(status_code=401, detail="缺少字段捷径流量签名")
    try:
        payload_part, signature_part = signature.split(".", 1)
        payload_bytes = base64url_decode(payload_part)
        signature_bytes = base64url_decode(signature_part)
        public_key = serialization.load_pem_public_key(BASE_PUBLIC_KEY.encode("ascii"))
        public_key.verify(signature_bytes, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        payload = json.loads(payload_bytes)
        if payload.get("source") != "base" or payload.get("version") != "v1":
            raise HTTPException(status_code=401, detail="字段捷径流量签名来源无效")
        signed_pack_id = str(payload.get("packID") or "")
        expires_at = int(payload.get("exp") or 0)
        expires_at_seconds = expires_at / 1000 if expires_at > 10_000_000_000 else expires_at
        if expires_at_seconds < time.time():
            raise HTTPException(status_code=401, detail="字段捷径流量签名已过期")
        if request_pack_id and signed_pack_id != request_pack_id:
            raise HTTPException(status_code=401, detail="字段捷径 ID 与签名不匹配")
        if settings.expected_pack_ids and signed_pack_id not in settings.expected_pack_ids:
            raise HTTPException(status_code=401, detail="字段捷径 ID 不在允许范围内")
    except HTTPException:
        raise
    except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as error:
        raise HTTPException(status_code=401, detail="字段捷径流量签名无效") from error


def prepared_video_directory() -> Path:
    directory = Path(settings.prepared_video_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cleanup_prepared_videos() -> None:
    directory = prepared_video_directory()
    cutoff = time.time() - settings.ticket_ttl_seconds
    for path in directory.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            continue


def create_download_ticket(file_id: str, filename: str) -> str:
    payload = json.dumps(
        {
            "file": file_id,
            "name": filename,
            "exp": int(time.time()) + settings.ticket_ttl_seconds,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = base64url_encode(payload)
    signature = hmac.new(
        settings.ticket_secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded_payload}.{base64url_encode(signature)}"


def read_download_ticket(ticket: str) -> tuple[Path, str]:
    try:
        encoded_payload, encoded_signature = ticket.split(".", 1)
        expected = hmac.new(
            settings.ticket_secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, base64url_decode(encoded_signature)):
            raise ValueError("signature mismatch")
        payload = json.loads(base64url_decode(encoded_payload))
        if int(payload["exp"]) < int(time.time()):
            raise HTTPException(status_code=410, detail="下载地址已过期，请重新生成字段")
        file_id = str(payload["file"])
        filename = safe_filename(str(payload["name"]), fallback="video.mp4")
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}\.[A-Za-z0-9]{1,8}", file_id):
            raise ValueError("invalid file id")
        directory = prepared_video_directory().resolve()
        file_path = (directory / file_id).resolve()
        if file_path.parent != directory:
            raise ValueError("invalid file path")
        if not file_path.is_file():
            raise HTTPException(status_code=410, detail="视频缓存已失效，请重新生成字段")
        return file_path, filename
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="下载凭证无效") from error


def safe_filename(value: str | None, fallback: str = "video") -> str:
    cleaned = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "-", value or "", flags=re.UNICODE)
    cleaned = cleaned.strip("-._")[:80]
    return cleaned or fallback


def media_type_for_filename(filename: str) -> str:
    if Path(filename).suffix.lower() == ".m4a":
        return "audio/mp4"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def locate_download(info: dict[str, Any], directory: Path, media_type: str) -> Path:
    requested = info.get("requested_downloads") or []
    for item in requested:
        candidate = item.get("filepath")
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    files = [path for path in directory.iterdir() if path.is_file() and not path.name.endswith(".part")]
    if not files:
        if media_type == "audio":
            raise RuntimeError(
                f"没有生成音频文件。源媒体可能超过 {settings.max_audio_source_size_mb} MB，"
                "或平台没有提供可提取的音轨"
            )
        raise RuntimeError(
            f"没有生成视频文件。视频可能超过 {settings.max_video_size_mb} MB，"
            "请改用仅音频模式"
        )
    return max(files, key=lambda path: path.stat().st_size)


def build_download_options(temp_dir: Path, media_type: str) -> dict[str, Any]:
    final_max_bytes = settings.max_video_size_mb * 1024 * 1024
    source_max_bytes = (
        settings.max_audio_source_size_mb * 1024 * 1024
        if media_type == "audio"
        else final_max_bytes
    )
    options: dict[str, Any] = {
        "outtmpl": str(temp_dir / "%(title).80s-%(id)s.%(ext)s"),
        "format": "bestaudio/best" if media_type == "audio" else "best[ext=mp4]/best",
        "noplaylist": True,
        "max_filesize": source_max_bytes,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
    }
    if media_type == "audio":
        options["ffmpeg_location"] = get_ffmpeg_exe()
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": str(AUDIO_BITRATE_KBPS),
            }
        ]
    return options


def download_media(url: str, media_type: str = "video") -> tuple[Path, Path, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="feishu-video-"))
    max_bytes = settings.max_video_size_mb * 1024 * 1024
    hostname = (urlparse(url).hostname or "").lower()
    is_douyin = hostname == "douyin.com" or hostname.endswith(".douyin.com")
    if is_douyin and settings.browser_debug_url.strip():
        try:
            file_path, filename = download_douyin_from_browser(url, media_type, temp_dir)
            return file_path, temp_dir, filename
        except Exception as error:
            logger.warning(
                "douyin_browser_primary_failed media_type=%s detail=%s",
                media_type,
                str(error),
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
    max_attempts = 3 if is_douyin and settings.cookies_from_browser.strip() else 1

    try:
        info: Any = None
        for attempt in range(1, max_attempts + 1):
            options = build_download_options(temp_dir, media_type)
            headers = browser_http_headers(url)
            if headers:
                options["http_headers"] = headers
            options.update(resolve_cookie_options())
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                break
            except DownloadError as error:
                message = str(error).lower()
                retryable = "fresh cookies" in message or "403" in message
                if not retryable or attempt >= max_attempts:
                    raise
                logger.warning("douyin_download_retry attempt=%s/%s", attempt, max_attempts)
                shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir.mkdir(parents=True, exist_ok=True)
                if not warm_browser_session(url):
                    time.sleep(attempt)

        if not isinstance(info, dict):
            raise RuntimeError("媒体解析结果无效")
        file_path = locate_download(info, temp_dir, media_type)
        if file_path.stat().st_size > max_bytes:
            kind = "音频" if media_type == "audio" else "视频"
            raise RuntimeError(f"{kind}超过 {settings.max_video_size_mb} MB 限制")
        title = safe_filename(info.get("title"), fallback=safe_filename(info.get("id")))
        extension = file_path.suffix.lower() or (".m4a" if media_type == "audio" else ".mp4")
        return file_path, temp_dir, f"{title}{extension}"
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def download_error_detail(error: DownloadError) -> str:
    message = str(error)
    if "Fresh cookies" in message or "cookies" in message.lower():
        return "抖音要求有效 Cookie。请在本机专用浏览器中重新登录抖音。"
    return "视频解析失败。请确认链接公开可访问，且不需要登录或 DRM 解密。"


def prepare_media(url: str, media_type: str = "video") -> tuple[str, str, int]:
    file_path, temp_dir, filename = download_media(url, media_type)
    try:
        extension = file_path.suffix.lower() or ".mp4"
        file_id = f"{secrets.token_urlsafe(24)}{extension}"
        prepared_path = prepared_video_directory() / file_id
        shutil.move(str(file_path), prepared_path)
        return file_id, filename, prepared_path.stat().st_size
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def ticket_response(file_id: str, filename: str, content_length: int) -> dict[str, Union[str, int]]:
    ticket = create_download_ticket(file_id, filename)
    base_url = settings.public_base_url.rstrip("/")
    return {
        "download_url": f"{base_url}/api/download/{ticket}",
        "filename": filename,
        "content_length": content_length,
        "expires_in": settings.ticket_ttl_seconds,
    }


@app.post("/api/worker/claim")
async def worker_claim(
    payload: WorkerClaimRequest,
    authorization: Optional[str] = Header(default=None),
) -> Any:
    verify_worker_authorization(authorization)
    worker_id = safe_filename(payload.worker_id, fallback="windows-worker")[:80]
    job = await claim_worker_job(worker_id)
    if not job:
        return Response(status_code=204)
    return {
        "job_id": job.job_id,
        "completion_token": job.completion_token,
        "url": job.url,
        "media_type": job.media_type,
        "max_output_bytes": settings.max_video_size_mb * 1024 * 1024,
    }


@app.put("/api/worker/jobs/{job_id}/result")
async def worker_result(
    job_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_job_token: Optional[str] = Header(default=None),
    x_worker_filename: Optional[str] = Header(default=None),
) -> dict[str, bool]:
    verify_worker_authorization(authorization)
    job = require_worker_job(job_id, x_job_token)
    try:
        filename = safe_filename(
            base64url_decode(x_worker_filename or "").decode("utf-8"),
            fallback="audio.m4a" if job.media_type == "audio" else "video.mp4",
        )
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="下载助手返回的文件名无效") from error

    extension = Path(filename).suffix.lower()
    expected_extension = ".m4a" if job.media_type == "audio" else ".mp4"
    if extension not in {".mp4", ".m4a"}:
        filename = f"{safe_filename(Path(filename).stem, fallback='media')}{expected_extension}"
        extension = expected_extension

    cleanup_prepared_videos()
    file_id = f"{secrets.token_urlsafe(24)}{extension}"
    destination = prepared_video_directory() / file_id
    max_bytes = settings.max_video_size_mb * 1024 * 1024
    content_length = 0
    try:
        with destination.open("wb") as output:
            async for chunk in request.stream():
                content_length += len(chunk)
                if content_length > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"下载结果超过 {settings.max_video_size_mb} MB 限制",
                    )
                output.write(chunk)
        if content_length == 0:
            raise HTTPException(status_code=400, detail="下载助手返回了空文件")
    except Exception as error:
        destination.unlink(missing_ok=True)
        message = error.detail if isinstance(error, HTTPException) else "下载助手上传结果失败"
        fail_worker_job(job, str(message))
        raise

    finish_worker_job(
        job,
        WorkerResult(file_id=file_id, filename=filename, content_length=content_length),
    )
    logger.info(
        "worker_job_completed log_id=%s job_id=%s filename=%s bytes=%s",
        job.log_id,
        job.job_id,
        filename,
        content_length,
    )
    return {"ok": True}


@app.post("/api/worker/jobs/{job_id}/failure")
async def worker_failure(
    job_id: str,
    payload: WorkerFailureRequest,
    authorization: Optional[str] = Header(default=None),
    x_job_token: Optional[str] = Header(default=None),
) -> dict[str, bool]:
    verify_worker_authorization(authorization)
    job = require_worker_job(job_id, x_job_token)
    message = payload.message.strip()[:500] or "Windows 下载节点处理失败"
    fail_worker_job(job, message)
    logger.warning(
        "worker_job_failed log_id=%s job_id=%s detail=%s",
        job.log_id,
        job.job_id,
        message,
    )
    return {"ok": True}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "max_video_size_mb": settings.max_video_size_mb,
        "max_audio_source_size_mb": settings.max_audio_source_size_mb,
        "allowed_domains": sorted(settings.domains),
        "cookie_source": cookie_source_name(),
        "worker_enabled": settings.worker_enabled,
        "worker_online": bool(
            settings.worker_enabled
            and worker_last_seen_at
            and time.time() - worker_last_seen_at <= settings.worker_heartbeat_ttl_seconds
        ),
    }


@app.post("/api/tickets")
async def create_ticket(payload: TicketRequest) -> dict[str, Union[str, int]]:
    url = str(payload.url)
    hostname = urlparse(url).hostname or ""
    logger.info(
        "ticket_start log_id=%s pack_id=%s media_type=%s host=%s",
        payload.log_id or "",
        payload.pack_id or "",
        payload.media_type,
        hostname,
    )
    try:
        validate_source_url(url)
        verify_base_signature(payload.base_signature, payload.pack_id)
    except HTTPException as error:
        logger.warning(
            "ticket_rejected log_id=%s pack_id=%s status=%s detail=%s host=%s",
            payload.log_id or "",
            payload.pack_id or "",
            error.status_code,
            error.detail,
            hostname,
        )
        raise
    cleanup_prepared_videos()
    try:
        if is_local_worker_host(hostname):
            worker_result_value = await dispatch_worker_job(
                url,
                payload.media_type,
                payload.log_id or "",
            )
            file_id = worker_result_value.file_id
            filename = worker_result_value.filename
            content_length = worker_result_value.content_length
        else:
            async with download_semaphore:
                file_id, filename, content_length = await asyncio.to_thread(
                    prepare_media, url, payload.media_type
                )
    except DownloadError as error:
        logger.warning(
            "ticket_download_error log_id=%s pack_id=%s detail=%s",
            payload.log_id or "",
            payload.pack_id or "",
            download_error_detail(error),
        )
        raise HTTPException(
            status_code=422,
            detail=download_error_detail(error),
        ) from error
    except WorkerUnavailableError as error:
        logger.warning(
            "worker_unavailable log_id=%s pack_id=%s detail=%s",
            payload.log_id or "",
            payload.pack_id or "",
            str(error),
        )
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WorkerJobError as error:
        logger.warning(
            "worker_download_error log_id=%s pack_id=%s detail=%s",
            payload.log_id or "",
            payload.pack_id or "",
            str(error),
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        logger.warning(
            "ticket_runtime_error log_id=%s pack_id=%s detail=%s",
            payload.log_id or "",
            payload.pack_id or "",
            str(error),
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception(
            "ticket_internal_error log_id=%s pack_id=%s",
            payload.log_id or "",
            payload.pack_id or "",
        )
        raise HTTPException(status_code=500, detail="视频下载服务暂时不可用") from error

    logger.info(
        "ticket_success log_id=%s pack_id=%s filename=%s bytes=%s",
        payload.log_id or "",
        payload.pack_id or "",
        filename,
        content_length,
    )
    return ticket_response(file_id, filename, content_length)


@app.get("/api/download/{ticket}", response_class=FileResponse)
async def download_by_ticket(ticket: str, background_tasks: BackgroundTasks) -> FileResponse:
    cleanup_prepared_videos()
    file_path, filename = read_download_ticket(ticket)
    media_type = media_type_for_filename(filename)
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


@app.post("/api/extract", response_class=FileResponse)
async def extract_video(payload: ExtractRequest, background_tasks: BackgroundTasks) -> FileResponse:
    if settings.require_base_signature:
        raise HTTPException(status_code=403, detail="生产环境仅允许字段捷径签名请求")

    url = str(payload.url)
    validate_source_url(url)

    try:
        async with download_semaphore:
            file_path, temp_dir, filename = await asyncio.to_thread(
                download_media, url, payload.media_type
            )
    except DownloadError as error:
        raise HTTPException(
            status_code=422,
            detail=download_error_detail(error),
        ) from error
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="视频下载服务暂时不可用") from error

    background_tasks.add_task(shutil.rmtree, temp_dir, True)
    media_type = media_type_for_filename(filename)
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={"X-Video-Source": url},
        background=background_tasks,
    )
