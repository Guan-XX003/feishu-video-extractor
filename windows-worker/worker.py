from __future__ import annotations

import base64
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from imageio_ffmpeg import get_ffmpeg_exe


WORKER_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = WORKER_ROOT / "config.json"


def load_local_config() -> None:
    if not CONFIG_PATH.is_file():
        return
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    mappings = {
        "FEISHU_WORKER_BACKEND_URL": "backend_url",
        "FEISHU_WORKER_TOKEN": "worker_token",
        "FEISHU_WORKER_ID": "worker_id",
        "FEISHU_WORKER_BROWSER": "browser",
        "FEISHU_WORKER_BROWSER_PROFILE": "browser_profile",
    }
    for environment_name, config_name in mappings.items():
        value = config.get(config_name)
        if value is not None:
            os.environ.setdefault(environment_name, str(value))


load_local_config()

BACKEND_URL = os.environ.get("FEISHU_WORKER_BACKEND_URL", "").rstrip("/")
WORKER_TOKEN = os.environ.get("FEISHU_WORKER_TOKEN", "")
WORKER_ID = os.environ.get("FEISHU_WORKER_ID", socket.gethostname())
BROWSER = os.environ.get("FEISHU_WORKER_BROWSER", "chrome")
BROWSER_PROFILE = os.environ.get("FEISHU_WORKER_BROWSER_PROFILE", "")
POLL_RETRY_SECONDS = float(os.environ.get("FEISHU_WORKER_POLL_RETRY_SECONDS", "3"))
DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("FEISHU_WORKER_DOWNLOAD_TIMEOUT_SECONDS", "300"))
MAX_VIDEO_SOURCE_MB = int(os.environ.get("FEISHU_WORKER_MAX_VIDEO_SOURCE_MB", "30"))
MAX_AUDIO_SOURCE_MB = int(os.environ.get("FEISHU_WORKER_MAX_AUDIO_SOURCE_MB", "500"))


log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
file_handler = RotatingFileHandler(
    WORKER_ROOT / "worker.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger("feishu_windows_worker")


def validate_settings() -> None:
    if not BACKEND_URL.startswith("https://"):
        raise RuntimeError("FEISHU_WORKER_BACKEND_URL 必须是 HTTPS 地址")
    if len(WORKER_TOKEN) < 32:
        raise RuntimeError("FEISHU_WORKER_TOKEN 未配置或长度不足")


def encoded_filename(filename: str) -> str:
    return base64.urlsafe_b64encode(filename.encode("utf-8")).decode("ascii").rstrip("=")


def download_job(job: dict[str, Any]) -> tuple[Path, Path]:
    media_type = str(job["media_type"])
    temp_dir = Path(tempfile.mkdtemp(prefix="feishu-video-worker-"))
    output_template = str(temp_dir / "%(title).80s-%(id)s.%(ext)s")
    source_limit = MAX_AUDIO_SOURCE_MB if media_type == "audio" else MAX_VIDEO_SOURCE_MB
    browser_source = f"{BROWSER}:{BROWSER_PROFILE}" if BROWSER_PROFILE else BROWSER
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--cookies-from-browser",
        browser_source,
        "--ffmpeg-location",
        get_ffmpeg_exe(),
        "--no-playlist",
        "--restrict-filenames",
        "--no-warnings",
        "--max-filesize",
        f"{source_limit}M",
        "--socket-timeout",
        "30",
        "--retries",
        "2",
        "--fragment-retries",
        "2",
        "--print",
        "after_move:filepath",
        "-o",
        output_template,
    ]
    if media_type == "audio":
        command.extend(["-f", "bestaudio/best", "-x", "--audio-format", "m4a", "--audio-quality", "128K"])
    else:
        command.extend(["-f", "best[ext=mp4]/best"])
    command.append(str(job["url"]))

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            output = f"{result.stdout}\n{result.stderr}".strip()
            if "Fresh cookies" in output or "cookies" in output.lower():
                raise RuntimeError("Windows 浏览器登录状态已失效，请在该机重新登录抖音")
            raise RuntimeError("视频下载失败，请确认链接公开可访问")

        candidates = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        file_path = next((path for path in reversed(candidates) if path.is_file()), None)
        if file_path is None:
            files = [path for path in temp_dir.iterdir() if path.is_file() and not path.name.endswith(".part")]
            file_path = max(files, key=lambda path: path.stat().st_size) if files else None
        if file_path is None:
            raise RuntimeError("下载完成但没有找到输出文件")

        max_output_bytes = int(job["max_output_bytes"])
        if file_path.stat().st_size > max_output_bytes:
            raise RuntimeError(f"下载结果超过 {max_output_bytes // 1024 // 1024} MB 附件限制")
        return file_path, temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def report_failure(client: httpx.Client, job: dict[str, Any], message: str) -> None:
    response = client.post(
        f"/api/worker/jobs/{job['job_id']}/failure",
        headers={"X-Job-Token": str(job["completion_token"])},
        json={"message": message[:500]},
    )
    response.raise_for_status()


def upload_result(client: httpx.Client, job: dict[str, Any], file_path: Path) -> None:
    headers = {
        "X-Job-Token": str(job["completion_token"]),
        "X-Worker-Filename": encoded_filename(file_path.name),
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_path.stat().st_size),
    }
    with file_path.open("rb") as media:
        response = client.put(
            f"/api/worker/jobs/{job['job_id']}/result",
            headers=headers,
            content=media,
            timeout=120,
        )
    response.raise_for_status()


def run() -> None:
    validate_settings()
    headers = {"Authorization": f"Bearer {WORKER_TOKEN}"}
    logger.info("Windows 下载节点已启动 worker_id=%s browser=%s", WORKER_ID, BROWSER)
    with httpx.Client(base_url=BACKEND_URL, headers=headers, timeout=35) as client:
        while True:
            try:
                response = client.post("/api/worker/claim", json={"worker_id": WORKER_ID})
                if response.status_code == 204:
                    continue
                response.raise_for_status()
                job = response.json()
                logger.info("领取下载任务 job_id=%s media_type=%s", job["job_id"], job["media_type"])
                temp_dir: Path | None = None
                try:
                    file_path, temp_dir = download_job(job)
                    upload_result(client, job, file_path)
                    logger.info("下载任务完成 job_id=%s bytes=%s", job["job_id"], file_path.stat().st_size)
                except Exception as error:
                    logger.error("下载任务失败 job_id=%s error=%s", job["job_id"], error)
                    try:
                        report_failure(client, job, str(error))
                    except Exception as report_error:
                        logger.error("上报任务失败 job_id=%s error=%s", job["job_id"], report_error)
                finally:
                    if temp_dir is not None:
                        shutil.rmtree(temp_dir, ignore_errors=True)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                logger.warning("连接 Railway 失败，稍后重试 error=%s", error)
                time.sleep(POLL_RETRY_SECONDS)


if __name__ == "__main__":
    run()
