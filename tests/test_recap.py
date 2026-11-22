"""核对无剧透回顾引擎：实际呈现、已知事实、剧透安全、补看窗口与改动复核。"""

import copy
import json
from pathlib import Path
import unittest

from inspect_records import load_records
from recap_engine import (
    State,
    build_editor_preview,
    is_safe,
    presented_lines,
    resolve_presentations,
    run_batch,
    tainted_by,
)

ROOT = Path(__file__).resolve().parents[1]


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records(ROOT / "data" / "records.json")
        cls.pre = run_batch(cls.records, apply_changes=False)
        cls.post = run_batch(cls.records, apply_changes=True)

    def view(self, rid):
        return self.post["requests"][rid]

    def test_line_must_be_fully_presented(self):
        presented = presented_lines(self.post["state"], "U01")
        self.assertIn(("B01", "text", 0), presented)
        # P1 播到 5800，B01 第二句到 5900：进入过片段不算听完
        self.assertNotIn(("B01", "text", 1), presented)
        self.assertIn(("B02", "text", 0), presented)
        self.assertNotIn(("B02", "text", 1), presented)
        # A02 的“下集预告”镜头文字只播了一半，不算看到
        self.assertNotIn(("A02", "screen", 1), presented)

    def test_known_facts_after_changes(self):
        self.assertEqual(
            set(self.view("R1")["known"]),
            {"F_kite_at_door", "F_bluesign_link", "F_token_half", "F_dyehouse_name"})

    def test_deleted_playback_revokes_only_that_record(self):
        pre_known = set(self.pre["requests"]["R1"]["known"])
        self.assertIn("F_blueline_mark", pre_known)  # 删除前经 B03 等价交代计入
        self.assertNotIn("F_blueline_mark", set(self.view("R1")["known"]))
        # 其他播放记录不受影响
        self.assertIn("F_token_half", set(self.view("R1")["known"]))

    def test_mapping_revision_narrows_equivalence(self):
        # 原登记按整段对应，U01 播全 B02 首句即计入身份揭晓
        self.assertIn("F_identity", set(self.pre["requests"]["R1"]["known"]))
        # E2 修订后仅末句等价，U01 未播到末句
        self.assertNotIn("F_identity", set(self.view("R1")["known"]))
        # U02 直接看过正片 A03，不受修订影响
        self.assertIn("F_identity", set(self.view("R2")["known"]))

    def test_recap_texts(self):
        r1 = self.view("R1")["player"]["recap"]
        self.assertEqual(r1, "她的蓝线签名接得上竹牌；竹牌另一半在青井染坊。")
        self.assertLessEqual(len(r1), 52)
        r2 = self.view("R2")["player"]["recap"]
        self.assertEqual(r2, "石绘就是纸鸢客；她回染坊的缘由在前文，可补看。")
        self.assertLessEqual(len(r2), 42)

    def test_recap_uses_only_seen_terms_and_no_spoilers(self):
        for rid in ("R1", "R2"):
            text = self.view(rid)["player"]["recap"]
            self.assertNotIn("姐姐", text)  # A05 才揭晓，不得说破
        # U01 没播全过石绘的台词，回顾不用该称呼
        self.assertNotIn("石绘", self.view("R1")["player"]["recap"])
        # U02 没见过竹牌，缺关键前因时只用已见过的称呼说明
        self.assertNotIn("竹牌", self.view("R2")["player"]["recap"])

    def test_catchup_within_window_and_boundaries(self):
        r1 = self.view("R1")["player"]
        self.assertEqual(r1["catchup"], [{"clip": "A04", "start": 0, "end": 700}])
        self.assertLessEqual(700, self.view("R1")["catchup_ms"])
        r2 = self.view("R2")["player"]
        self.assertEqual(r2["catchup"], [{"clip": "A04", "start": 0, "end": 700}])
        self.assertLessEqual(700, self.view("R2")["catchup_ms"])
        # 关键前因没有可安全跳转的位置：提示不含剧情内容
        self.assertTrue(r2["notices"])
        payload = json.dumps(r2, ensure_ascii=False)
        self.assertNotIn("姐姐", payload)
        self.assertNotIn("预告", payload)

    def test_gap_filling_interval_must_not_carry_spoilers(self):
        # A02[0,3200] 虽能补“竹牌另一半在染坊”，但与“下集预告”镜头文字重叠
        unfillable = {u["fact"] for u in self.view("R2")["unfillable"]}
        self.assertIn("F_token_half", unfillable)
        state = self.post["state"]
        presentations = resolve_presentations(state)
        self.assertEqual(
            tainted_by(state, presentations, "A02", 0, 3200, "A04", 800),
            "F_sister")
        self.assertIsNone(
            tainted_by(state, presentations, "A04", 0, 700, "A04", 800))

    def test_trailer_does_not_establish_fact(self):
        state = self.post["state"]
        presentations = resolve_presentations(state)
        # 预告播得再早，也不在续播点之前确立正片事实
        self.assertFalse(is_safe(state, presentations, "F_sister", "A04", 800))
        self.assertTrue(is_safe(state, presentations, "F_token_half", "A04", 800))
        # 轻剪独有事实经场记关联换算位置，可在续播点前确立
        self.assertTrue(is_safe(state, presentations, "F_bluesign_link", "A04", 800))
        # 续播点之后的台词不可用
        self.assertFalse(is_safe(state, presentations, "F_keep_token", "A04", 800))

    def test_jump_kept_when_text_invalidated(self):
        preview = build_editor_preview(self.records)
        r1 = preview["requests"]["R1"]
        verdicts = {c["fact"]: c["verdict"] for c in r1["previous_components"]
                    if c["fact"]}
        self.assertEqual(verdicts["F_identity"], "作废")
        self.assertEqual(verdicts["F_blueline_mark"], "作废")
        self.assertEqual(verdicts["F_bluesign_link"], "保留")
        self.assertEqual(verdicts["F_token_half"], "保留")
        reasons = {c["fact"]: c["reason"] for c in r1["previous_components"]
                   if c["fact"]}
        self.assertIn("P4", reasons["F_blueline_mark"])
        self.assertIn("M2", reasons["F_identity"])
        # 还合适的跳转不能仅因同批文案作废而被一并删去
        self.assertEqual(len(r1["previous_catchup"]), 1)
        self.assertEqual(r1["previous_catchup"][0]["verdict"], "保留")

    def test_spinoff_never_counts_as_main_plot(self):
        records = copy.deepcopy(self.records)
        records["playback"].append({"id": "PX", "viewer": "U09", "clip": "B02",
                                    "played": [[4100, 6600]]})
        records["resume"].append({"id": "RX", "viewer": "U09", "clip": "A04",
                                  "offset": 800, "limit": 50, "catchup_ms": 0})
        batch = run_batch(records, apply_changes=True)
        self.assertNotIn("F_spinoff_setup", batch["requests"]["RX"]["known"])

    def test_equivalent_account_in_other_version_counts(self):
        records = copy.deepcopy(self.records)
        # 只看过轻剪 B02 末句的观众：等价独立交代可纳入已知
        records["playback"].append({"id": "PX", "viewer": "U09", "clip": "B02",
                                    "played": [[3000, 3900]]})
        records["resume"].append({"id": "RX", "viewer": "U09", "clip": "A04",
                                  "offset": 800, "limit": 50, "catchup_ms": 0})
        batch = run_batch(records, apply_changes=True)
        self.assertIn("F_identity", batch["requests"]["RX"]["known"])

    def test_trailer_seen_still_not_usable_back_in_main_plot(self):
        records = copy.deepcopy(self.records)
        # 观众完整看过 A02 的“下集预告”镜头文字
        records["playback"].append({"id": "PX", "viewer": "U09", "clip": "A02",
                                    "played": [[2500, 4200]]})
        records["resume"].append({"id": "RX", "viewer": "U09", "clip": "A04",
                                  "offset": 800, "limit": 50, "catchup_ms": 0})
        batch = run_batch(records, apply_changes=True)
        view = batch["requests"]["RX"]
        self.assertIn("F_sister", view["known"])  # 预告确实看到了
        self.assertNotIn("姐姐", view["player"]["recap"])  # 跳回正片不得说破

    def test_zero_budget_allows_zero_segments(self):
        records = copy.deepcopy(self.records)
        for request in records["resume"]:
            request["catchup_ms"] = 0
        batch = run_batch(records, apply_changes=True)
        self.assertEqual(batch["requests"]["R1"]["player"]["catchup"], [])
        self.assertIsNone(batch["requests"]["R1"]["player"]["hint"])

    def test_limit_counts_codepoints_not_hint(self):
        records = copy.deepcopy(self.records)
        for request in records["resume"]:
            if request["id"] == "R1":
                request["limit"] = 12  # 只容得下答案本身
        batch = run_batch(records, apply_changes=True)
        view = batch["requests"]["R1"]
        self.assertEqual(view["player"]["recap"], "竹牌另一半在青井染坊。")
        self.assertLessEqual(len(view["player"]["recap"]), 12)
        self.assertIsNotNone(view["player"]["hint"])  # 补看提示不占短稿额度


if __name__ == "__main__":
    unittest.main()
