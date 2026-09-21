import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_ipo_schedule import add_kind_listing_dates, company_key, has_public_offering_structure, is_ipo_document, make_item, parse_dates, parse_kind_offerings, parse_money, spac_key


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

    def test_kind_table_and_verified_match(self):
        html = '''<table><tr onclick="fnDetailView('1')">
        <td title="테스트">test</td><td>2026-09-01</td><td>2026-09-02 ~ 2026-09-03</td>
        <td>2026-09-10<br/> ~ 2026-09-11</td><td>2026-09-15</td><td>10,000</td><td>20,000</td>
        <td>2026-09-21</td><td>KB증권(주)</td></tr></table>'''.encode()
        offers = parse_kind_offerings(html)
        self.assertEqual(offers[0]["listing"], "2026-09-21")
        items = [{"name": "테스트", "date": "2026-09-10", "endDate": "2026-09-11", "listing": None}]
        self.assertEqual(add_kind_listing_dates(items, offers), 1)
        self.assertEqual(items[0]["listing"], "2026-09-21")

    def test_kind_match_requires_same_subscription_period(self):
        items = [{"name": "테스트", "date": "2026-09-12", "endDate": "2026-09-13", "listing": None}]
        offers = [{"name": "테스트", "date": "2026-09-10", "endDate": "2026-09-11", "listing": "2026-09-21"}]
        self.assertEqual(add_kind_listing_dates(items, offers), 0)
        self.assertIsNone(items[0]["listing"])

    def test_company_and_spac_normalization(self):
        self.assertEqual(company_key("(주) 테스트"), company_key("테스트 주식회사"))
        self.assertEqual(spac_key("KB제34호스팩"), spac_key("KB스팩34호"))
        self.assertEqual(spac_key("케이비제34호기업인수목적"), spac_key("KB제34호스팩"))


if __name__ == "__main__":
    unittest.main()
