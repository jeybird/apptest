"""
네이버 증권 실시간 랭킹(상승) 페이지를 크롤링하여 SQLite DB에 저장하는 스크립트.

대상 페이지: https://stock.naver.com/market/stock/kr/stocklist/upper

실행 방법:
    python -m crawler.naver_rank_crawler

사전 준비 (최초 1회):
    pip install -r requirements.txt
    playwright install chromium

동작 방식:
    - 네이버의 비공개 API를 직접 호출하지 않고, Playwright로 실제 화면을 그대로
      렌더링한 뒤 화면에 보이는 표(<table>)를 그대로 읽어옵니다.
    - 표의 헤더 텍스트(종목명/현재가/전일대비/거래량/거래대금/고가/저가/시가총액)를
      기준으로 컬럼 위치를 찾기 때문에, 컬럼 순서가 바뀌거나 사용자가 표 설정에서
      컬럼을 추가/제거해도 필요한 컬럼만 정상적으로 인식합니다.

알려진 제한사항 (중요):
    이 코드는 네이버 페이지의 실제 HTML 구조를 실시간으로 확인할 수 없는 개발 환경에서
    작성되었습니다. 표준적인 <table> 마크업이라고 가정하고 작성했으나, 만약 실제
    페이지가 div 기반의 커스텀 그리드라면 _extract_rows_from_table()의 선택자를
    조정해야 합니다. 최초 실행 시 데이터가 하나도 수집되지 않는다면, 자동으로 저장되는
    debug_page.html 파일의 구조를 확인해 알려주세요.
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from crawler.db import init_db, save_ranking_data
from crawler.parsers import parse_change, parse_int, parse_won_amount

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TARGET_URL = "https://stock.naver.com/market/stock/kr/stocklist/upper"
DEBUG_HTML_PATH = Path(__file__).resolve().parent.parent / "debug_page.html"

# 화면에 표시되는 헤더 텍스트 -> 내부 필드명 매핑.
# ('전일대비'는 가격/등락률 두 값을 함께 담고 있어 별도 파서(parse_change)로 처리합니다.)
HEADER_TO_FIELD = {
    "종목명": "stock_name",
    "현재가": "current_price",
    "전일대비": "change",
    "거래량": "volume",
    "거래대금": "trading_value",
    "고가": "high_price",
    "저가": "low_price",
    "시가총액": "market_cap",
}


def _find_header_indexes(header_cells: List[str]) -> Dict[str, int]:
    """헤더 텍스트 리스트에서 필요한 컬럼들의 인덱스를 찾아 반환합니다."""
    index_map: Dict[str, int] = {}
    for idx, raw_text in enumerate(header_cells):
        text = raw_text.strip()
        if text in HEADER_TO_FIELD:
            index_map[HEADER_TO_FIELD[text]] = idx
    return index_map


def _parse_row(cells: List[str], index_map: Dict[str, int], rank: int) -> Optional[Dict]:
    """표의 한 행(td 텍스트 리스트)을 DB 저장용 딕셔너리로 변환합니다."""
    try:
        stock_name = cells[index_map["stock_name"]].strip()
    except IndexError:
        return None
    if not stock_name:
        return None

    def cell(field: str) -> Optional[str]:
        idx = index_map.get(field)
        if idx is None or idx >= len(cells):
            return None
        return cells[idx]

    change_price, change_rate = parse_change(cell("change"))

    return {
        "rank": rank,
        "stock_name": stock_name,
        "current_price": parse_int(cell("current_price")),
        "change_price": change_price,
        "change_rate": change_rate,
        "volume": parse_int(cell("volume")),
        "trading_value": parse_won_amount(cell("trading_value")),
        "high_price": parse_int(cell("high_price")),
        "low_price": parse_int(cell("low_price")),
        "market_cap": parse_won_amount(cell("market_cap")),
    }


def _extract_rows_from_table(page: Page, max_rows: int) -> List[Dict]:
    """
    렌더링된 페이지의 <table> 요소들을 순회하며, '종목명'/'현재가' 헤더를 가진
    표를 찾아 랭킹 데이터를 추출합니다. 여러 표가 있을 수 있으므로 조건에
    맞는 첫 번째 표만 사용합니다.
    """
    tables = page.locator("table")
    table_count = tables.count()
    logger.info("페이지에서 발견된 <table> 개수: %d", table_count)

    for t in range(table_count):
        table = tables.nth(t)

        header_cells = table.locator("thead th").all_inner_texts()
        if not header_cells:
            # thead가 없는 표는 첫 번째 행을 헤더로 간주해봅니다.
            first_row = table.locator("tr").first
            header_cells = first_row.locator("th, td").all_inner_texts()

        index_map = _find_header_indexes(header_cells)
        if "stock_name" not in index_map or "current_price" not in index_map:
            continue  # 원하는 랭킹 표가 아님 (예: 광고성 표, 다른 통계 표 등)

        body_rows = table.locator("tbody tr")
        row_count = min(body_rows.count(), max_rows)
        results: List[Dict] = []
        for r in range(row_count):
            cells = body_rows.nth(r).locator("td").all_inner_texts()
            if not cells:
                continue
            parsed = _parse_row(cells, index_map, rank=r + 1)
            if parsed:
                results.append(parsed)

        if results:
            return results

    return []


def crawl_ranking(max_rows: int = 50, headless: bool = True, timeout_ms: int = 30000) -> List[Dict]:
    """
    네이버 증권 실시간 랭킹(상승) 페이지를 크롤링해서 파싱된 딕셔너리 리스트를 반환합니다.

    Args:
        max_rows: 수집할 최대 종목 수
        headless: True면 브라우저 창을 띄우지 않고 백그라운드에서 실행
        timeout_ms: 페이지 로딩/요소 대기 제한 시간(밀리초)

    Returns:
        파싱된 종목 데이터 리스트. 크롤링에 실패하면 빈 리스트를 반환합니다.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            logger.info("페이지 접속 중: %s", TARGET_URL)
            page.goto(TARGET_URL, wait_until="networkidle")

            # SPA 특성상 초기 응답만으로는 데이터가 없을 수 있어 표가 그려질 때까지 대기
            page.wait_for_selector("table", timeout=timeout_ms)

            rows = _extract_rows_from_table(page, max_rows=max_rows)
            if not rows:
                logger.error(
                    "랭킹 표에서 데이터를 찾지 못했습니다. 페이지 구조가 예상과 다를 수 있습니다."
                )
                _save_debug_html(page)
            return rows
        except PlaywrightTimeoutError:
            logger.error("페이지 로딩 시간이 초과되었습니다. 네트워크 상태 또는 URL을 확인하세요.")
            return []
        finally:
            browser.close()


def _save_debug_html(page: Page) -> None:
    """데이터 추출에 실패했을 때, 원인 분석을 위해 현재 페이지 HTML을 저장합니다."""
    try:
        DEBUG_HTML_PATH.write_text(page.content(), encoding="utf-8")
        logger.info("디버깅용 페이지 스냅샷을 저장했습니다: %s", DEBUG_HTML_PATH)
    except OSError as exc:
        logger.warning("디버깅용 페이지 스냅샷 저장 실패: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="네이버 증권 실시간 랭킹(상승) 크롤러")
    parser.add_argument("--max-rows", type=int, default=50, help="수집할 최대 종목 수 (기본값: 50)")
    parser.add_argument(
        "--show-browser", action="store_true", help="브라우저 창을 화면에 표시합니다 (디버깅용)"
    )
    args = parser.parse_args()

    init_db()

    now = datetime.now()
    crawl_date = now.strftime("%Y-%m-%d")
    crawl_time = now.strftime("%H:%M:%S")

    rows = crawl_ranking(max_rows=args.max_rows, headless=not args.show_browser)
    if not rows:
        logger.error("저장할 데이터가 없어 크롤링을 종료합니다.")
        sys.exit(1)

    saved_count = save_ranking_data(rows, crawl_date, crawl_time)
    logger.info("%d건 저장 완료 (날짜: %s, 시각: %s)", saved_count, crawl_date, crawl_time)


if __name__ == "__main__":
    main()
