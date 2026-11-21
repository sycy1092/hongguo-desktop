"""Reservation contract: public upcoming calendar, the account's own reservations
and a single-item 预约 / 取消预约 change.

Every field and path here comes from the mobile client's own traffic, and the
read paths were re-checked against live responses on 2026-11-20:

  * 即将上线 (no login)
      GET /reading/user/subscribe/list/v1/?tab_type=5&target_date=YYYYMMDD
          &user_is_login=0&need_calendar_schema=true
      rows: is_online=false, item_id=<预约对象>, sub_info='预计11月23日上线',
            expected_rec_text='86.5万人预约', subscribe_data={title, cover, ...}
      `subscribe_data.series_id` is empty before the series launches, so an
      upcoming card is identified by its reservation id instead.
  * 已预约 (login)
      GET /reading/user/subscribe/list/v1/?tab_type=13&is_online=false|true
      the account's reservations split by whether the series has launched.
  * 预约 / 取消预约 (login, one item per call)
      POST /reading/bookapi/search/uncover_subscribe/v
      body {item_id, item_type:1, op_type:1|2, wish_list_all_del:0, shark_param}
      op_type 1 reserves, 2 cancels.

This module owns validation and normalisation only: no HTTP client, no account
storage and no background work. The provider owns the request budget and the
read-back confirmation.
"""
from __future__ import annotations

import re

CALENDAR_PATH = "/reading/user/subscribe/list/v1/"
CHANGE_PATH = "/reading/bookapi/search/uncover_subscribe/v"

_DATE = re.compile(r"[0-9]{8}")
_IDENTITY = re.compile(r"[1-9][0-9]{7,23}")
# The mobile client only publishes 上线 times inside this window; anything else
# is an unset field rather than a real date.
_MIN_STAMP, _MAX_STAMP = 946684800, 4102444800
_MAX_ROWS = 200
MAX_PAGES = 3


class ReservationError(ValueError):
    """Rejected or unrecognised reservation input; never contains account data."""


def valid_date(value) -> str:
    """Return a YYYYMMDD calendar key or raise."""
    text = value if isinstance(value, str) else ""
    if not _DATE.fullmatch(text):
        raise ReservationError("date-invalid")
    year, month, day = int(text[:4]), int(text[4:6]), int(text[6:])
    if not 2000 <= year <= 2100 or not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ReservationError("date-invalid")
    return text


def identity(value) -> str:
    """Return a reservation/series identifier, or '' when the field is unset."""
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    return text if _IDENTITY.fullmatch(text) else ""


def valid_offset(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2000:
        raise ReservationError("offset-invalid")
    return value


def calendar_fields(date: str = "", offset: int = 0) -> dict:
    """Public calendar query; `date` empty asks the server for its current day."""
    fields = {
        "active_panel": "5", "gender_type": "2", "tab_type": "5", "tab_style": "2",
        "need_calendar_schema": "true", "order_experiment": "descend", "offset": str(valid_offset(offset)),
        "session_id": "", "version": "0", "filter_type": "gender", "subscribe_list_opt": "0",
        "user_is_login": "0",
    }
    if date:
        fields["target_date"] = valid_date(date)
    return fields


def list_fields(online: bool, offset: int = 0) -> dict:
    """The account's reservations, one partition per launch state."""
    if type(online) is not bool:
        raise ReservationError("partition-invalid")
    return {
        "limit": "20", "offset": str(valid_offset(offset)), "subscribe_offset": str(valid_offset(offset)),
        "tab_type": "13", "subscribe_order_type": "0", "swipe_type": "0",
        "need_calendar_schema": "false", "is_online": "true" if online else "false",
    }


def change_body(item_id, reserved) -> dict:
    """The exact body the mobile client sends for one reservation change."""
    target = identity(item_id)
    if not target or type(reserved) is not bool:
        raise ReservationError("change-invalid")
    return {
        "item_id": target, "item_type": 1, "op_type": 1 if reserved else 2, "wish_list_all_del": 0,
        "shark_param": {"enter_from": "BulletActivity", "previous_page": "MainFragmentActivity",
                        "page_list": "MainFragmentActivity,BulletActivity"},
    }


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _count(value) -> int:
    return value if type(value) is int and 0 <= value <= 100000 else 0


def _stamp(value) -> int:
    return value if type(value) is int and _MIN_STAMP <= value <= _MAX_STAMP else 0


def _detail(row) -> dict:
    detail = row.get("subscribe_data")
    return detail if isinstance(detail, dict) else {}


def _publish_at(row) -> int:
    return _stamp(row.get("schedule_publish_time")) or _stamp(row.get("expected_publish_time"))


def _item(row, online: bool) -> dict | None:
    """Normalise one calendar row; None means the row carries nothing displayable."""
    detail = _detail(row)
    video = detail.get("video_detail") if isinstance(detail.get("video_detail"), dict) else {}
    series = identity(detail.get("series_id")) or identity(row.get("series_id"))
    # A launched row keeps item_id='0' in the public calendar; the account's own
    # list may still carry the reservation id, and the ledger matches on it.
    reservation = identity(row.get("item_id"))
    title = _text(video.get("series_title") or detail.get("title") or row.get("name") or row.get("item_desc"), 200)
    if not title or not (series or reservation):
        return None
    return {
        "id": series or reservation,
        "seriesId": series,
        "reservationId": reservation,
        "title": title,
        "cover": _text(video.get("series_cover") or detail.get("cover") or row.get("cover"), 8192),
        "intro": _text(video.get("series_intro") or detail.get("video_desc") or row.get("item_desc"), 4000),
        "episodeCount": _count(video.get("episode_cnt") or detail.get("episode_cnt")),
        "publishAt": _publish_at(row),
        "note": _text(row.get("sub_info"), 200),
        "reserveText": _text(row.get("expected_rec_text"), 200),
        "online": online,
    }


def _page(root) -> dict:
    if not isinstance(root, dict) or str(root.get("code")) != "0":
        raise ReservationError("upstream-rejected")
    data = root.get("data")
    if not isinstance(data, dict):
        raise ReservationError("payload-invalid")
    rows, more = data.get("subscribe_items"), data.get("has_more")
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS or type(more) is not bool:
        raise ReservationError("payload-invalid")
    return {"data": data, "rows": rows, "more": more}


def _continuation(data, offset: int, more: bool) -> int:
    if not more:
        return offset
    next_offset = data.get("next_offset")
    if type(next_offset) is not int or not offset < next_offset <= 2000:
        raise ReservationError("continuation-invalid")
    return next_offset


def parse_calendar(root, date: str = "", offset: int = 0) -> dict:
    """Normalise one page of the public 上线日历."""
    valid_offset(offset)
    page = _page(root)
    data, rows = page["data"], page["rows"]
    schema = data.get("calendar_schema")
    if not isinstance(schema, dict):
        raise ReservationError("calendar-schema-missing")
    today = valid_date(schema.get("current_date") or schema.get("default_date"))
    current = valid_date(date) if date else valid_date(schema.get("default_date") or today)
    dates = []
    raw_dates = schema.get("date_list")
    if not isinstance(raw_dates, list) or not 1 <= len(raw_dates) <= 62:
        raise ReservationError("calendar-dates-invalid")
    for value in raw_dates:
        try:
            key = valid_date(value)
        except ReservationError:
            continue
        if key not in dates:
            dates.append(key)
    dates.sort()
    if not dates:
        raise ReservationError("calendar-dates-invalid")
    if current not in dates:
        dates = sorted({*dates, current})
    items = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("is_online")) is not bool:
            continue
        item = _item(row, row["is_online"])
        if item:
            items.append(item)
    if rows and not items:
        raise ReservationError("calendar-items-unrecognised")
    return {"today": today, "date": current, "dates": dates, "items": items,
            "hasMore": page["more"], "nextOffset": _continuation(data, offset, page["more"])}


def parse_list(root, online: bool, offset: int = 0) -> dict:
    """Normalise one page of the account's own reservations."""
    list_fields(online, offset)
    page = _page(root)
    data, rows = page["data"], page["rows"]
    items = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReservationError("row-invalid")
        subscribed, launched = row.get("has_subscribed"), row.get("is_online")
        if type(subscribed) is not bool or type(launched) is not bool:
            raise ReservationError("state-unconfirmed")
        if not subscribed:
            continue
        if launched != online:
            raise ReservationError("partition-mismatch")
        item = _item(row, online)
        if item:
            items.append(item)
    return {"items": items, "hasMore": page["more"],
            "nextOffset": _continuation(data, offset, page["more"]),
            "onlineTotal": _count(data.get("online_total_count")),
            "offlineTotal": _count(data.get("offline_total_count"))}
