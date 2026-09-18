"""
SQLite DB 초기화 및 랭킹 데이터 저장을 담당하는 모듈.

- DB 파일은 프로젝트 루트의 data/stock_rank.db 에 생성됩니다.
- 크롤러(naver_rank_crawler.py)와 대시보드(dashboard/app.py)가 이 파일을 공유합니다.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List

# 프로젝트 루트 기준 data 폴더 경로 (crawler/db.py -> crawler -> 프로젝트 루트)
DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "stock_rank.db"

# 실시간 랭킹 스냅샷을 저장하는 테이블
# 같은 (crawl_date, crawl_time, rank) 조합은 유일해야 하며, 중복 저장 시 덮어씁니다.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_ranking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_date TEXT NOT NULL,        -- 조회 기준 날짜 (YYYY-MM-DD)
    crawl_time TEXT NOT NULL,        -- 크롤링 실행 시각 (HH:MM:SS)
    rank INTEGER NOT NULL,           -- 실시간 랭킹 순위
    stock_name TEXT NOT NULL,        -- 종목명
    current_price INTEGER,           -- 현재가 (원)
    change_price INTEGER,            -- 전일대비 변동가 (원, 부호 포함, 상승 +/하락 -)
    change_rate REAL,                -- 전일대비 등락률 (%, 부호 포함)
    volume INTEGER,                  -- 거래량 (주)
    trading_value INTEGER,           -- 거래대금 (원 단위로 환산해서 저장)
    high_price INTEGER,              -- 고가 (원)
    low_price INTEGER,               -- 저가 (원)
    market_cap INTEGER,              -- 시가총액 (원 단위로 환산해서 저장)
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(crawl_date, crawl_time, rank)
);
"""

CREATE_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_stock_ranking_date ON stock_ranking (crawl_date);"


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """
    DB 커넥션을 컨텍스트 매니저로 제공합니다.
    정상 종료 시 자동 commit, 예외 발생 시 자동 rollback 후 예외를 다시 던집니다.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)  # data 폴더가 없으면 생성
    conn = sqlite3.connect(str(DB_PATH))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """DB 파일과 테이블/인덱스가 없으면 새로 생성합니다. 여러 번 호출해도 안전합니다."""
    with get_connection() as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)


def save_ranking_data(rows: List[Dict], crawl_date: str, crawl_time: str) -> int:
    """
    크롤링한 랭킹 데이터를 DB에 저장합니다.
    동일한 (crawl_date, crawl_time, rank) 조합이 이미 있으면 덮어씁니다.

    Args:
        rows: naver_rank_crawler.crawl_ranking() 이 반환한 딕셔너리 리스트
        crawl_date: 조회 기준 날짜, 'YYYY-MM-DD' 형식
        crawl_time: 크롤링 실행 시각, 'HH:MM:SS' 형식

    Returns:
        저장을 시도한 row 개수 (0이면 저장할 데이터가 없었다는 의미)
    """
    if not rows:
        return 0

    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO stock_ranking (
                crawl_date, crawl_time, rank, stock_name,
                current_price, change_price, change_rate,
                volume, trading_value, high_price, low_price, market_cap
            ) VALUES (
                :crawl_date, :crawl_time, :rank, :stock_name,
                :current_price, :change_price, :change_rate,
                :volume, :trading_value, :high_price, :low_price, :market_cap
            )
            """,
            [{**row, "crawl_date": crawl_date, "crawl_time": crawl_time} for row in rows],
        )
    return len(rows)
