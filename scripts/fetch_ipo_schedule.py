#!/usr/bin/env python3
"""Build ipo-schedule.json from OpenDART without exposing the API key."""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = "https://opendart.fss.or.kr/api"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ipo-schedule.json"
SEOUL = timezone(timedelta(hours=9))
LIST_LOOKBACK_DAYS = 89  # OpenDART limits company-less disclosure searches to 3 months.


def clean(value: object) -> str:
    return re.sub(r"[<>\x00-\x1f]", " ", str(value or "")).strip()


def urlopen_with_retry(request: urllib.request.Request, timeout: int = 20) -> bytes:
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as error:
            last_error = error
            if attempt < 1:
                time.sleep(2 ** attempt)
    raise RuntimeError("OpenDART request failed after retries") from last_error


def api_json(path: str, params: dict[str, object]) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "ipo-record/1.0"})
    data = json.loads(urlopen_with_retry(request).decode("utf-8"))
    if data.get("status") not in (None, "000", "013"):
        raise RuntimeError(f"OpenDART {path}: {data.get('status')} {data.get('message')}")
    return data


def parse_dates(value: object) -> list[str]:
    text = str(value or "")
    found: list[date] = []
    for y, m, d in re.findall(r"(20\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})", text):
        try:
            item = date(int(y), int(m), int(d))
            if item not in found:
                found.append(item)
        except ValueError:
            pass
    return [item.isoformat() for item in found]


def parse_money(value: object) -> int | None:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return int(digits) if digits else None


def groups(payload: dict) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for group in payload.get("group", []) or []:
        result[clean(group.get("title"))] = group.get("list", []) or []
    return result


def rows_for_receipt(grouped: dict[str, list[dict]], title: str, receipt: str) -> list[dict]:
    rows = grouped.get(title) or []
    exact = [row for row in rows if clean(row.get("rcept_no")) == receipt]
    return exact or rows


def has_public_offering_structure(detail: dict, receipt: str) -> bool:
    grouped = groups(detail)
    securities = rows_for_receipt(grouped, "증권의종류", receipt)
    underwriters = rows_for_receipt(grouped, "인수인정보", receipt)
    methods = " ".join(clean(row.get("slmthn")) for row in securities)
    return bool(underwriters) and ("공모" in methods or "모집" in methods)


IPO_MARKERS = (
    "신규상장", "기업공개", "코스닥시장 상장", "유가증권시장 상장",
    "코넥스시장 상장", "상장을 목적으로", "상장예정",
)


def is_ipo_document(raw: bytes) -> bool:
    """Require explicit IPO/listing language from the filed document."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            text = " ".join(
                archive.read(name).decode("utf-8", "ignore")
                for name in archive.namelist()
                if name.lower().endswith((".xml", ".html", ".txt"))
            )
    except zipfile.BadZipFile:
        text = raw.decode("utf-8", "ignore")
    compact = re.sub(r"\s+", " ", text)
    return any(marker in compact for marker in IPO_MARKERS)


def fetch_document(key: str, receipt: str) -> bytes:
    query = urllib.parse.urlencode({"crtfc_key": key, "rcept_no": receipt})
    request = urllib.request.Request(f"{API}/document.xml?{query}", headers={"User-Agent": "ipo-record/1.0"})
    return urlopen_with_retry(request)


def normalize_broker(name: str) -> str:
    name = clean(name).replace("㈜", "").replace("주식회사", "").strip()
    aliases = {
        "한국투자": "한국투자증권", "NH투자": "NH투자증권", "엔에이치투자증권": "NH투자증권",
        "KB": "KB증권", "케이비증권": "KB증권", "아이비케이투자증권": "IBK투자증권",
        "유진증권": "유진투자증권",
    }
    return aliases.get(name, name)


def make_item(filing: dict, detail: dict) -> dict | None:
    grouped = groups(detail)
    receipt = clean(filing.get("rcept_no"))
    general = (rows_for_receipt(grouped, "일반사항", receipt) or [{}])[0]
    securities = rows_for_receipt(grouped, "증권의종류", receipt)
    underwriters = rows_for_receipt(grouped, "인수인정보", receipt)
    dates = parse_dates(general.get("sbd"))
    if not dates:
        return None
    start, end = dates[0], dates[-1]
    prices = [parse_money(row.get("slprc")) for row in securities]
    prices = [price for price in prices if price]
    brokers = []
    for row in underwriters:
        broker = normalize_broker(row.get("actnmn", ""))
        if broker and broker not in brokers:
            brokers.append(broker)
    return {
        "id": f"dart-{receipt}",
        "name": clean(filing.get("corp_name") or general.get("corp_name")),
        "date": start,
        "endDate": end,
        "broker": ", ".join(brokers) or "주관사 확인 필요",
        # OpenDART's slprc can be a proposed/assumed amount, not a confirmed IPO price.
        "price": None,
        "priceBand": " · ".join(f"{price:,}원" for price in sorted(set(prices))) + " (공시 표시값)" if prices else "공시 확인 필요",
        "listing": None,
        "industry": None,
        "description": "OpenDART 증권신고서에서 확인된 신규상장 일정",
        "source": "OpenDART",
        "sourceUrl": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
        "receiptNo": receipt,
    }


def fetch_filings(key: str, begin: date, end: date) -> list[dict]:
    page, filings = 1, []
    while True:
        data = api_json("list.json", {
            "crtfc_key": key, "bgn_de": begin.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"), "pblntf_ty": "C",
            "pblntf_detail_ty": "C001", "last_reprt_at": "Y",
            "page_no": page, "page_count": 100,
        })
        filings.extend(data.get("list", []) or [])
        if page >= int(data.get("total_page", 1) or 1):
            return filings
        page += 1


def build(key: str, today: date | None = None) -> dict:
    today = today or datetime.now(SEOUL).date()
    filings = fetch_filings(key, today - timedelta(days=LIST_LOOKBACK_DAYS), today)
    candidates, seen, seen_corps = [], set(), set()
    for filing in filings:
        receipt = clean(filing.get("rcept_no"))
        corp_class = clean(filing.get("corp_cls"))
        corp_code = clean(filing.get("corp_code"))
        # Listed KOSPI/KOSDAQ issuers' ordinary equity offerings are not IPOs.
        if not receipt or receipt in seen or not corp_code or corp_code in seen_corps or corp_class in {"Y", "K"}:
            continue
        seen.add(receipt)
        seen_corps.add(corp_code)
        candidates.append(filing)

    def inspect(filing: dict) -> dict | None:
        receipt = clean(filing.get("rcept_no"))
        corp_code = clean(filing.get("corp_code"))
        detail = api_json("estkRs.json", {
            "crtfc_key": key, "corp_code": corp_code,
            "bgn_de": (today - timedelta(days=180)).strftime("%Y%m%d"),
            "end_de": today.strftime("%Y%m%d"),
        })
        if detail.get("status") == "013":
            return None
        if not has_public_offering_structure(detail, receipt):
            try:
                if not is_ipo_document(fetch_document(key, receipt)):
                    return None
            except Exception as error:
                print(f"warning: skipped {receipt}; document check failed: {error}", file=sys.stderr)
                return None
        item = make_item(filing, detail)
        if item and date.fromisoformat(item["endDate"]) >= today - timedelta(days=14):
            return item
        return None

    items = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(inspect, filing): filing for filing in candidates}
        for future in as_completed(futures):
            try:
                item = future.result()
                if item:
                    items.append(item)
            except Exception as error:
                receipt = clean(futures[future].get("rcept_no"))
                print(f"warning: skipped {receipt}; OpenDART request failed: {error}", file=sys.stderr)
    items.sort(key=lambda item: (item["date"], item["name"]))
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "source": "OpenDART",
        "notice": "공시 기준 자동 일정입니다. 상장일·업종은 OpenDART 제공 범위 밖이므로 공시 원문과 증권사에서 다시 확인하세요.",
        "items": items,
    }


def main() -> int:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        print("DART_API_KEY is required", file=sys.stderr)
        return 2
    payload = build(key)
    if not payload["items"] and OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if previous.get("items"):
            raise RuntimeError("OpenDART returned no IPOs; keeping the existing non-empty schedule")
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['items'])} IPO schedules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
