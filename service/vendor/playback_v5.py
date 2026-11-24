"""X-Medusa playback lookup through the SDK v5 session (ported protocol stack).

The unidbg web signer still serves catalog endpoints, but the player-model
endpoint only answers requests signed by the SDK's own session: a device
registration, an SDK exchange (token + ladon) and the medusa proof built from
the SDK image/config. Everything here is pure Python and local.
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path

import requests

# 本地依赖：SDK 摘要核心用 unicorn 模拟 ARM 指令，随客户端一起分发。
_LIBS = Path(__file__).resolve().parent / "libs"
if _LIBS.is_dir() and str(_LIBS) not in sys.path:
    sys.path.insert(0, str(_LIBS))
# 协议模块（设备注册、签名、模型解析）放在同级 phone 目录。
_PHONE = Path(__file__).resolve().parent / "phone"
if _PHONE.is_dir() and str(_PHONE) not in sys.path:
    sys.path.insert(0, str(_PHONE))

HOST = "api5-normal-sinfonlineb.fqnovel.com"
MAX_BODY = 2 * 1024 * 1024
SDK_VERSION_DIR = "74332"


class PlaybackV5Error(RuntimeError):
    def __init__(self, reason, message=None, **numbers):
        self.reason = reason
        self.diagnostic = {key: value for key, value in numbers.items() if isinstance(value, int)}
        messages = {
            "assets": "本地缺少播放签名素材，请重新安装客户端",
            "session": "播放签名会话建立失败，请稍后重试",
            "upstream-empty": "上游没有返回播放地址，请稍后重试",
            "upstream-http": "上游拒绝了播放请求，请稍后重试",
            "invalid-model": "上游返回的播放地址不可用，请稍后重试",
            "setup": "本地播放签名组件不可用",
        }
        super().__init__(message or messages.get(reason, "播放地址暂不可用，请稍后重试"))


def assets_dir(data_dir) -> Path:
    return Path(data_dir) / "playback-sdk" / SDK_VERSION_DIR


def ensure_assets(data_dir, *, allow_download=False, donor=None):
    """Make the SDK image/config available locally (bundled copy first, no network)."""
    from phone_sdk_assets_v5 import load_assets, SdkAssetsError

    root = assets_dir(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    names = ("libmetasec_ml.so", "sdk-app-config.encoded")
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        bundled = Path(__file__).resolve().parent / "sdk-assets" / SDK_VERSION_DIR
        sources = [bundled]
        if donor:
            sources.append(Path(donor) / "playback-sdk" / SDK_VERSION_DIR)
        for name in missing:
            for source in sources:
                candidate = source / name
                if candidate.is_file() and candidate.stat().st_size:
                    (root / name).write_bytes(candidate.read_bytes())
                    break
    try:
        return load_assets(root, allow_download=allow_download)
    except SdkAssetsError as error:
        raise PlaybackV5Error("assets", str(error)) from error


def _core_factory(image):
    from phone_sdk_core_v5 import SdkDigestCore

    engine = SdkDigestCore(image)

    def core(payload, mode, seconds):
        return engine.digest(payload, mode, seconds)[0][:16]

    return core


def _archive_review_marker(data_dir):
    """A previous exchange that never finished must not block us forever."""
    root = Path(data_dir)
    for name in ("playback-sdk-v5-attempt.json", "playback-sdk-v5-continue.json"):
        marker = root / name
        try:
            if marker.is_file():
                marker.replace(root / (name + ".stale"))
        except OSError:
            pass


def lookup(data_dir, context, video, *, allow_download=False, donor=None, timeout=(8, 20)):
    """Return the raw video_model payload for one video id."""
    try:
        return _lookup_once(data_dir, context, video, allow_download=allow_download, donor=donor, timeout=timeout)
    except PlaybackV5Error as error:
        if "needs-review" not in str(error):
            raise
        _archive_review_marker(data_dir)
        return _lookup_once(data_dir, context, video, allow_download=allow_download, donor=donor, timeout=timeout)


def _lookup_once(data_dir, context, video, *, allow_download=False, donor=None, timeout=(8, 20)):
    from phone_sdk_materials_v5 import decode_app_config, read_sdk_image
    from phone_sdk_session_v5 import SessionStore, SdkSessionError, send_prepared
    from phone_playback_request_v5 import prepare_playback_v5

    assets = ensure_assets(data_dir, allow_download=allow_download, donor=donor)
    image_bytes = assets.image
    materials = decode_app_config(assets.configuration)
    image = read_sdk_image(image_bytes)
    core = _core_factory(image_bytes)
    store = SessionStore(Path(data_dir), sender=send_prepared)
    try:
        session = store.ensure(context, assets, core=core, allow_exchange=True)
    except SdkSessionError as error:
        raise PlaybackV5Error("session", str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise PlaybackV5Error("session", str(error)[:120]) from error
    request = prepare_playback_v5(
        context,
        str(video),
        int(time.time() * 1000),
        token=session["token"],
        previous_ladon=session.get("ladon", 0),
        materials=materials,
        image=image,
        core=core,
    )
    try:
        response = requests.post(request.url, data=request.body, headers=request.headers,
                                 timeout=timeout, allow_redirects=False)
    except requests.RequestException as error:
        raise PlaybackV5Error("upstream-http") from error
    with response:
        if response.status_code != 200:
            raise PlaybackV5Error("upstream-http", http_status=response.status_code)
        payload = response.content
    if not payload:
        raise PlaybackV5Error("upstream-empty", http_status=200, body_bytes=0)
    if len(payload) > MAX_BODY:
        raise PlaybackV5Error("upstream-http", body_bytes=len(payload))
    if payload[:2] == b"\x1f\x8b":
        try:
            payload = gzip.decompress(payload)
        except OSError as error:
            raise PlaybackV5Error("invalid-model") from error
    try:
        root = json.loads(payload)
    except ValueError as error:
        raise PlaybackV5Error("invalid-model", body_bytes=len(payload)) from error
    if not isinstance(root, dict) or root.get("code") != 0:
        raise PlaybackV5Error("upstream-http", code=root.get("code") if isinstance(root, dict) else -1)
    data = root.get("data") if isinstance(root.get("data"), dict) else {}
    item = data.get(str(video)) if isinstance(data, dict) else None
    if not isinstance(item, dict) or not item.get("video_model"):
        raise PlaybackV5Error("invalid-model")
    return item["video_model"]
