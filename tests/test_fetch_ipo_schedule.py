import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_ipo_schedule import has_public_offering_structure, is_ipo_document, make_item, parse_dates, parse_money


class ScheduleTests(unittest.TestCase):
    def test_dates_and_money(self):
        self.assertEqual(parse_dates("2026년 9월 10일 ~ 2026년 09월 11일"), ["2026-09-10", "2026-09-11"])
        self.assertEqual(parse_money("15,800원"), 15800)

    def test_ipo_filter_rejects_ordinary_offering(self):
        self.assertTrue(is_ipo_document("코스닥시장 상장을 목적으로 신규상장".encode()))
        self.assertFalse(is_ipo_document("주주배정 후 실권주 일반공모".encode()))

    def test_structured_public_offering_requires_underwriter(self):
        detail = {"group": [
            {"title": "증권의종류", "list": [{"rcept_no": "222", "slmthn": "일반공모"}]},
            {"title": "인수인정보", "list": [{"rcept_no": "222", "actnmn": "KB증권"}]},
        ]}
        self.assertTrue(has_public_offering_structure(detail, "222"))
        detail["group"].pop()
        self.assertFalse(has_public_offering_structure(detail, "222"))

    def test_item_schema(self):
        filing = {"rcept_no": "20260910000001", "corp_name": "테스트", "corp_cls": "E"}
        detail = {"group": [
            {"title": "일반사항", "list": [{"sbd": "2026.09.10 ~ 2026.09.11"}]},
            {"title": "증권의종류", "list": [{"slprc": "10,000"}]},
            {"title": "인수인정보", "list": [{"actnmn": "NH투자증권"}]},
        ]}
        item = make_item(filing, detail)
        self.assertEqual(item["date"], "2026-09-10")
        self.assertIsNone(item["price"])
        self.assertEqual(item["priceBand"], "10,000원 (공시 표시값)")
        self.assertEqual(item["broker"], "NH투자증권")

    def test_item_uses_matching_receipt_after_correction(self):
        filing = {"rcept_no": "222", "corp_name": "테스트", "corp_cls": "E"}
        detail = {"group": [
            {"title": "일반사항", "list": [
                {"rcept_no": "111", "sbd": "2026.08.01 ~ 2026.08.02"},
                {"rcept_no": "222", "sbd": "2026.09.10 ~ 2026.09.11"},
            ]},
            {"title": "증권의종류", "list": [{"rcept_no": "222", "slprc": "12,000"}]},
            {"title": "인수인정보", "list": [{"rcept_no": "222", "actnmn": "KB증권"}]},
        ]}
        item = make_item(filing, detail)
        self.assertEqual(item["date"], "2026-09-10")
        self.assertIsNone(item["price"])


if __name__ == "__main__":
    unittest.main()
