"""X-Medusa signed playback lookup, ported from the working client's protocol modules.

The unidbg web signer still works for catalog endpoints, but the player-model
endpoint now only answers X-Medusa signed requests. This module builds such a
request (device + saved session, no account token) and returns the raw
video_model payload so the caller can reuse the existing track parser.
"""
from __future__ import annotations

import gzip
import json
import time

import requests

HOST = "api5-normal-sinfonlineb.fqnovel.com"
MAX_BODY = 2 * 1024 * 1024


class PlaybackV5Error(RuntimeError):
    def __init__(self, reason, **numbers):
        self.reason = reason
        self.diagnostic = {key: value for key, value in numbers.items() if isinstance(value, int)}
        messages = {
            "upstream-empty": "上游没有返回播放地址，请稍后重试",
            "upstream-http": "上游拒绝了播放请求，请稍后重试",
            "invalid-model": "上游返回的播放地址不可用，请稍后重试",
            "setup": "本地播放签名组件不可用",
        }
        super().__init__(messages.get(reason, "播放地址暂不可用，请稍后重试"))


def build_context(device, base_query, cookies, user_agent):
    """Assemble the protocol context from our own saved device and account cookies."""
    params = {}
    for key, value in (base_query or {}).items():
        params[str(key)] = str(value)
    for key, value in (device or {}).items():
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            params[str(key)] = str(value)
    return {
        "params": params,
        "cookies": {str(key): str(value) for key, value in (cookies or {}).items()},
        "user_agent": user_agent,
        "device_token": "",
    }


def lookup(context, video, timeout=(8, 20)):
    """Return the raw video_model payload for one video id."""
    try:
        import desktop_playback_request as playback_request
    except Exception as error:  # noqa: BLE001
        raise PlaybackV5Error("setup") from error
    now = int(time.time() * 1000)
    try:
        url, headers, body = playback_request.prepare_account(context, str(video), now)
    except ValueError as error:
        raise PlaybackV5Error("setup", code=0) from error
    cookies = context.get("cookies") or {}
    if cookies:
        # 账号态请求：带上登录 cookie 与区域头（匿名分支里被构造器移除了）。
        headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
        headers["X-TT-Store-Region"] = cookies.get("store-region") or "cn"
        headers["X-TT-Store-Region-Src"] = "did"
    try:
        response = requests.post(url, data=body, headers=headers, timeout=timeout, allow_redirects=False)
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
