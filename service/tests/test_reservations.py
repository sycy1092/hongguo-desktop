"""Reservation contract and provider behaviour; every payload here is synthetic."""
from pathlib import Path
import json
import sys
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reservations as contract
from provider import Provider, ProviderError


UPCOMING_ID = "7704223871410392089"
ONLINE_ID = "7708340921548426265"
DATE = "20261123"
TODAY = "20261120"


def upcoming_row(item_id=UPCOMING_ID, title="病弱千金，百鬼让路第二季"):
    return {"is_online": False, "item_id": item_id, "sub_info": "预计11月23日上线",
            "expected_rec_text": "86.5万人预约", "schedule_publish_time": 1795363560,
            "expected_publish_time": 1795363560, "subscribe_data": {
                "title": title, "cover": "https://example.invalid/upcoming.image",
                "video_desc": "简介", "series_id": None, "episode_cnt": 55}}


def online_row():
    return {"is_online": True, "item_id": "0", "schedule_publish_time": 1795104248,
            "subscribe_data": {"title": "惹不起的沈南汐", "cover": "https://example.invalid/online.image",
                               "video_desc": "简介", "series_id": ONLINE_ID, "episode_cnt": 80}}


def calendar_page(rows, more=False, next_offset=None, date=DATE):
    data = {"subscribe_items": rows, "has_more": more, "session_id": "synthetic",
            "calendar_schema": {"current_date": TODAY, "default_date": date,
                                "date_list": ["20261119", TODAY, DATE]}}
    if next_offset is not None:
        data["next_offset"] = next_offset
    return {"code": 0, "data": data}


def mine_row(item, subscribed=True):
    row = {**item, "has_subscribed": subscribed}
    return row


def mine_page(rows, online, more=False, next_offset=None):
    data = {"subscribe_items": rows, "has_more": more, "session_id": "synthetic",
            "online_total_count": 1 if online else 0, "offline_total_count": 0 if online else 1}
    if next_offset is not None:
        data["next_offset"] = next_offset
    return {"code": 0, "data": data}


class ReservationContractTests(unittest.TestCase):
    def test_calendar_maps_an_upcoming_series_without_a_series_id(self):
        page = contract.parse_calendar(calendar_page([upcoming_row()]), DATE, 0)
        self.assertEqual(page["today"], TODAY)
        self.assertEqual(page["date"], DATE)
        self.assertEqual(page["dates"], ["20261119", TODAY, DATE])
        item = page["items"][0]
        self.assertEqual(item["id"], UPCOMING_ID)
        self.assertEqual(item["seriesId"], "")
        self.assertEqual(item["reservationId"], UPCOMING_ID)
        self.assertEqual(item["publishAt"], 1795363560)
        self.assertEqual(item["note"], "预计11月23日上线")
        self.assertEqual(item["reserveText"], "86.5万人预约")
        self.assertFalse(item["online"])

    def test_calendar_keeps_launched_rows_readonly(self):
        item = contract.parse_calendar(calendar_page([online_row()]), TODAY, 0)["items"][0]
        self.assertEqual(item["seriesId"], ONLINE_ID)
        self.assertEqual(item["reservationId"], "")
        self.assertTrue(item["online"])

    def test_calendar_defaults_to_the_server_day(self):
        page = contract.parse_calendar(calendar_page([upcoming_row()], date=DATE), "", 0)
        self.assertEqual(page["date"], DATE)

    def test_calendar_drops_rows_without_display_data(self):
        rows = [{"is_online": False, "item_id": ""}, upcoming_row()]
        self.assertEqual(len(contract.parse_calendar(calendar_page(rows), DATE)["items"]), 1)
        with self.assertRaises(contract.ReservationError):
            contract.parse_calendar(calendar_page([{"is_online": False, "item_id": ""}]), DATE)

    def test_calendar_requires_forward_pagination(self):
        with self.assertRaises(contract.ReservationError):
            contract.parse_calendar(calendar_page([upcoming_row()], more=True, next_offset=0), DATE)
        page = contract.parse_calendar(calendar_page([upcoming_row()], more=True, next_offset=24), DATE, 0)
        self.assertEqual(page["nextOffset"], 24)

    def test_calendar_rejects_a_date_outside_the_schema(self):
        page = contract.parse_calendar(calendar_page([upcoming_row()]), "20261201", 0)
        self.assertIn("20261201", page["dates"])

    def test_rejected_upstream_is_not_reported_as_an_empty_calendar(self):
        with self.assertRaises(contract.ReservationError):
            contract.parse_calendar({"code": 100, "data": {}}, DATE)
        with self.assertRaises(contract.ReservationError):
            contract.parse_calendar({"code": 0, "data": {"subscribe_items": [], "has_more": False}}, DATE)

    def test_mine_partitions_keep_subscribed_rows_only(self):
        page = contract.parse_list(mine_page([mine_row(upcoming_row())], False), False, 0)
        self.assertEqual(page["items"][0]["reservationId"], UPCOMING_ID)
        skipped = contract.parse_list(mine_page([mine_row(upcoming_row(), subscribed=False)], False), False, 0)
        self.assertEqual(skipped["items"], [])
        self.assertEqual(skipped["offlineTotal"], 1)

    def test_mine_rejects_unconfirmed_or_mismatched_rows(self):
        row = {**upcoming_row(), "has_subscribed": True}
        with self.assertRaises(contract.ReservationError):
            contract.parse_list(mine_page([row], False), True)
        row = {k: v for k, v in mine_row(upcoming_row()).items() if k != "has_subscribed"}
        with self.assertRaises(contract.ReservationError):
            contract.parse_list(mine_page([row], False), False)

    def test_change_body_matches_the_mobile_request(self):
        self.assertEqual(contract.change_body(UPCOMING_ID, True), {
            "item_id": UPCOMING_ID, "item_type": 1, "op_type": 1, "wish_list_all_del": 0,
            "shark_param": {"enter_from": "BulletActivity", "previous_page": "MainFragmentActivity",
                            "page_list": "MainFragmentActivity,BulletActivity"}})
        self.assertEqual(contract.change_body(UPCOMING_ID, False)["op_type"], 2)
        for bad in ("", "0", "short", "1" * 25, None, 1234):
            with self.assertRaises(contract.ReservationError):
                contract.change_body(bad, True)
        with self.assertRaises(contract.ReservationError):
            contract.change_body(UPCOMING_ID, "yes")

    def test_calendar_fields_carry_the_public_query(self):
        fields = contract.calendar_fields(DATE, 24)
        self.assertEqual(fields["target_date"], DATE)
        self.assertEqual(fields["offset"], "24")
        self.assertEqual(fields["tab_type"], "5")
        self.assertEqual(fields["user_is_login"], "0")
        self.assertNotIn("target_date", contract.calendar_fields("", 0))


class ProviderReservationTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(__file__).resolve().parent / ".work" / self._testMethodName
        self.work.mkdir(parents=True, exist_ok=True)
        (self.work / "reservations.json").unlink(missing_ok=True)
        self.mine = {False: [mine_row(upcoming_row())], True: []}
        self.calendar = [upcoming_row()]
        self.posts, self.calls = [], []
        self.write_code = 0
        self.identity = "synthetic-identity"

        def respond(method, path, body=None, extra=None, session=None):
            self.calls.append((method, path, body, extra))
            if path == contract.CHANGE_PATH:
                self.posts.append(body)
                return {"code": self.write_code, "data": {}}
            online = (extra or {}).get("is_online") == "true"
            rows = self.mine[online]
            return mine_page(rows, online)

        self.sdk = types.SimpleNamespace(api=Mock(side_effect=lambda *args, **kwargs: {
            "code": 0, "data": {"subscribe_items": self.calendar, "has_more": False,
                                "calendar_schema": {"current_date": TODAY, "default_date": DATE,
                                                    "date_list": [TODAY, DATE]}}}))
        self.account = types.SimpleNamespace(
            public_session=Mock(return_value={"loggedIn": True, "uid": "synthetic-user", "userName": "测试"}),
            load_session=Mock(return_value={"uid": "synthetic-user", "token": "synthetic-only"}),
            _account_changed=Mock(return_value=False), _call=Mock(side_effect=respond),
            _json=lambda response: response)
        self.provider = Provider(self.work, self.sdk, self.account)
        self.addCleanup(self.provider.close)

    def expire(self):
        self.provider.cache.clear()

    def test_calendar_reads_the_public_page_without_an_account_call(self):
        page = self.provider.reservation_calendar(DATE)
        self.assertEqual(page["items"][0]["reservationId"], UPCOMING_ID)
        self.assertEqual(page["cursor"], "")
        self.account._call.assert_not_called()
        self.sdk.api.assert_called_once()
        self.assertEqual(self.sdk.api.call_args.kwargs["extra_query"]["target_date"], DATE)

    def test_calendar_rejects_an_unknown_date_or_cursor(self):
        for date, cursor in (("2026-11-23", ""), (DATE, "x"), (DATE, "10000")):
            with self.assertRaises(ProviderError) as error:
                self.provider.reservation_calendar(date, cursor)
            self.assertEqual(error.exception.code, "INPUT_INVALID")

    def test_reservations_merge_both_partitions_and_cache_offline(self):
        self.mine[True] = [mine_row(online_row())]
        value = self.provider.reservations()
        self.assertEqual([item["reservationId"] for item in value["upcoming"]], [UPCOMING_ID])
        self.assertEqual([item["seriesId"] for item in value["online"]], [ONLINE_ID])
        self.assertFalse(value["stale"])
        self.assertEqual(len(self.posts), 0)

        self.expire()
        self.account._call = Mock(side_effect=OSError("offline"))
        stale = self.provider.reservations()
        self.assertTrue(stale["stale"])
        self.assertEqual(stale["warning"], "显示上次读取的预约列表")
        self.assertEqual(stale["upcoming"][0]["title"], "病弱千金，百鬼让路第二季")

    def test_reservations_without_a_cache_still_report_the_failure(self):
        self.expire()
        self.account._call = Mock(side_effect=OSError("offline"))
        with self.assertRaises(ProviderError):
            self.provider.reservations()

    def test_reserve_confirms_by_reading_both_partitions(self):
        self.mine[False] = [mine_row(upcoming_row())]
        result = self.provider.reserve(UPCOMING_ID, True, "synthetic-user")
        self.assertEqual(result, {"synced": True, "reserved": True, "pending": False})
        self.assertEqual(self.posts[0]["op_type"], 1)
        self.assertEqual(self.posts[0]["item_id"], UPCOMING_ID)
        offline = [call for call in self.calls if call[1] == contract.CALENDAR_PATH]
        self.assertEqual({call[3]["is_online"] for call in offline}, {"false"})

    def test_reserve_reports_pending_when_the_list_does_not_confirm(self):
        self.mine[False] = []
        with patch("time.sleep"):
            result = self.provider.reserve(UPCOMING_ID, True, "synthetic-user")
        self.assertFalse(result["synced"])
        self.assertTrue(result["pending"])
        self.assertIn("红果尚未确认", result["message"])
        self.assertEqual(len(self.posts), 1)

    def test_cancel_posts_op_type_two_and_verifies_absence(self):
        self.mine[False] = []
        result = self.provider.reserve(UPCOMING_ID, False, "synthetic-user")
        self.assertTrue(result["synced"])
        self.assertEqual(self.posts[0]["op_type"], 2)
        # An absence only holds once both launch partitions were read.
        offline = [call for call in self.calls if call[1] == contract.CALENDAR_PATH]
        self.assertEqual([call[3]["is_online"] for call in offline], ["false", "true"])

    def test_rejected_write_never_claims_success(self):
        self.write_code = 101144
        with self.assertRaises(ProviderError) as error:
            self.provider.reserve(UPCOMING_ID, True, "synthetic-user")
        self.assertEqual(error.exception.code, "RESERVATION_REJECTED")
        self.assertEqual(len(self.posts), 1)
        self.assertFalse([call for call in self.calls if call[1] == contract.CALENDAR_PATH])

    def test_reserve_requires_the_current_account(self):
        with self.assertRaises(ProviderError) as error:
            self.provider.reserve(UPCOMING_ID, True, "another-user")
        self.assertEqual(error.exception.code, "ACCOUNT_CHANGED")
        self.assertEqual(self.posts, [])

    def test_reserve_rejects_an_invalid_target_before_writing(self):
        with self.assertRaises(ProviderError) as error:
            self.provider.reserve("0", True, "synthetic-user")
        self.assertEqual(error.exception.code, "INPUT_INVALID")
        self.assertEqual(self.posts, [])

    def test_logged_out_account_cannot_read_reservations(self):
        self.account.public_session = Mock(return_value={"loggedIn": False, "uid": ""})
        with self.assertRaises(ProviderError) as error:
            self.provider.reservations()
        self.assertEqual(error.exception.code, "LOGIN_REQUIRED")

    def seed(self, history):
        self.mine[False] = []
        self.mine[True] = []
        (self.work / "reservations.json").write_text(json.dumps({"schema": 1, "accounts": {
            "synthetic-user": {"at": int(time.time()), "upcoming": [], "online": [], "history": history}}},
            ensure_ascii=False), encoding="utf-8")
        self.expire()

    @staticmethod
    def entry(patch=None):
        value = {"id": UPCOMING_ID, "itemId": UPCOMING_ID, "seriesId": "", "title": "病弱千金，百鬼让路第二季",
                 "cover": "https://example.invalid/upcoming.image", "episodeCount": 55,
                 "publishAt": 1700000000, "reservedAt": 1699990000, "cancelledAt": 0}
        value.update(patch or {})
        return value

    @staticmethod
    def launched_row(title, episodes):
        row = online_row()
        row["subscribe_data"] = {**row["subscribe_data"], "title": title, "episode_cnt": episodes}
        return mine_row(row)

    def test_a_launched_local_record_survives_an_upstream_list_that_dropped_it(self):
        self.seed([self.entry()])
        value = self.provider.reservations()
        self.assertEqual([row["title"] for row in value["online"]], ["病弱千金，百鬼让路第二季"])
        self.assertEqual(value["online"][0]["source"], "local")
        self.assertTrue(value["online"][0]["online"])
        self.assertEqual(value["history"][0]["id"], UPCOMING_ID)

    def test_a_reservation_made_before_this_client_keeps_an_unknown_time(self):
        self.mine[False] = [mine_row(upcoming_row())]
        history = self.provider.reservations()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["reservedAt"], 0)
        self.assertEqual(history[0]["publishAt"], 1795363560)

    def test_a_future_reservation_is_not_reported_as_launched(self):
        self.seed([self.entry({"publishAt": 4102440000})])
        self.assertEqual(self.provider.reservations()["online"], [])

    def test_a_cancelled_reservation_is_never_reported_as_launched(self):
        self.seed([self.entry({"cancelledAt": 1699999999})])
        self.assertEqual(self.provider.reservations()["online"], [])

    def test_a_delayed_release_upstream_still_lists_as_upcoming_stays_upcoming(self):
        self.seed([self.entry({"publishAt": 1700000000, "seenAt": int(time.time()), "online": False})])
        self.assertEqual(self.provider.reservations()["online"], [])

    def test_an_entry_upstream_reported_online_is_launched_without_a_schedule(self):
        self.seed([self.entry({"publishAt": 0, "online": True, "seenAt": int(time.time())})])
        self.assertEqual(len(self.provider.reservations()["online"]), 1)

    def test_the_same_series_is_not_listed_twice(self):
        self.seed([self.entry()])
        self.mine[True] = [self.launched_row("病弱千金，百鬼让路第二季", 55)]
        value = self.provider.reservations()
        self.assertEqual(len(value["online"]), 1)
        self.assertEqual(len(value["history"]), 1)
        self.assertEqual(value["history"][0]["seriesId"], ONLINE_ID)

    def test_a_similar_title_stays_a_separate_record(self):
        self.seed([self.entry()])
        self.mine[True] = [self.launched_row("病弱千金，百鬼让路第二季（下）", 55)]
        self.assertEqual(len(self.provider.reservations()["online"]), 2)

    def test_a_different_episode_count_is_not_merged(self):
        self.seed([self.entry()])
        self.mine[True] = [self.launched_row("病弱千金，百鬼让路第二季", 80)]
        self.assertEqual(len(self.provider.reservations()["online"]), 2)

    def test_reserving_records_the_schedule_and_cancelling_keeps_the_history(self):
        self.mine[False] = [mine_row(upcoming_row())]
        self.assertTrue(self.provider.reserve(UPCOMING_ID, True, "synthetic-user")["synced"])
        self.expire()
        self.mine[False] = []
        self.assertTrue(self.provider.reserve(UPCOMING_ID, False, "synthetic-user")["synced"])
        history = self.provider._reservation_ledger("synthetic-user")
        self.assertEqual(len(history), 1)
        self.assertGreater(history[0]["cancelledAt"], 0)
        self.assertEqual(history[0]["title"], "病弱千金，百鬼让路第二季")
        self.assertEqual(history[0]["publishAt"], 1795363560)
        self.assertEqual(self.provider.reservations()["online"], [])

    def test_history_is_newest_action_first(self):
        self.seed([self.entry({"id": "7704223871410392001", "itemId": "7704223871410392001",
                               "title": "先预约的", "reservedAt": 1699000000}),
                   self.entry({"id": "7704223871410392002", "itemId": "7704223871410392002",
                               "title": "后预约的", "reservedAt": 1699900000})])
        self.assertEqual([row["title"] for row in self.provider.reservations()["history"]],
                         ["后预约的", "先预约的"])


if __name__ == "__main__":
    unittest.main()
