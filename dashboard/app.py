"""
네이버 증권 실시간 랭킹(상승) 데이터를 날짜별로 조회하는 Streamlit 대시보드.

실행 방법:
    streamlit run dashboard/app.py

사전 준비:
    - crawler/naver_rank_crawler.py 를 먼저 1회 이상 실행해서 data/stock_rank.db 에
      데이터가 쌓여 있어야 합니다.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_rank.db"

# 국내 증권 관례에 맞춘 상태 색상: 상승=빨강, 하락=파랑, 보합=회색
COLOR_UP = "#d64545"
COLOR_DOWN = "#2f6fed"
COLOR_FLAT = "#6b7280"

st.set_page_config(page_title="네이버 증권 실시간 랭킹 대시보드", page_icon="📈", layout="wide")


@st.cache_data(ttl=60)
def load_available_dates() -> list:
    """DB에 저장된 조회 가능한 날짜 목록을 최신순으로 반환합니다."""
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(str(DB_PATH)) as conn:
        df = pd.read_sql_query(
            "SELECT DISTINCT crawl_date FROM stock_ranking ORDER BY crawl_date DESC", conn
        )
    return df["crawl_date"].tolist()


@st.cache_data(ttl=60)
def load_available_times(crawl_date: str) -> list:
    """선택한 날짜에 저장된 크롤링 시각 목록을 최신순으로 반환합니다."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        df = pd.read_sql_query(
            "SELECT DISTINCT crawl_time FROM stock_ranking WHERE crawl_date = ? ORDER BY crawl_time DESC",
            conn,
            params=(crawl_date,),
        )
    return df["crawl_time"].tolist()


@st.cache_data(ttl=60)
def load_ranking(crawl_date: str, crawl_time: str) -> pd.DataFrame:
    """선택한 날짜/시각의 랭킹 데이터를 화면 표시용 DataFrame으로 반환합니다."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        df = pd.read_sql_query(
            """
            SELECT rank AS 순위, stock_name AS 종목명, current_price AS 현재가,
                   change_price AS 전일대비, change_rate AS "등락률(%)",
                   volume AS 거래량, trading_value AS 거래대금,
                   high_price AS 고가, low_price AS 저가, market_cap AS 시가총액
            FROM stock_ranking
            WHERE crawl_date = ? AND crawl_time = ?
            ORDER BY 순위 ASC
            """,
            conn,
            params=(crawl_date, crawl_time),
        )
    return df


def style_change_value(value: float) -> str:
    """등락 관련 셀에 값 부호에 따라 빨강/파랑/회색 글자색을 적용합니다."""
    if pd.isna(value):
        return ""
    if value > 0:
        return f"color: {COLOR_UP}; font-weight: 600;"
    if value < 0:
        return f"color: {COLOR_DOWN}; font-weight: 600;"
    return f"color: {COLOR_FLAT};"


def main() -> None:
    st.title("📈 네이버 증권 실시간 랭킹(상승) 대시보드")
    st.caption("stock.naver.com 의 실시간 랭킹(상승) 데이터를 날짜별로 조회합니다.")

    dates = load_available_dates()
    if not dates:
        st.warning(
            "저장된 데이터가 없습니다. 먼저 아래 명령으로 크롤러를 실행해 데이터를 수집해 주세요.\n\n"
            "```\npython -m crawler.naver_rank_crawler\n```"
        )
        return

    with st.sidebar:
        st.header("조회 조건")
        selected_date = st.selectbox("날짜 선택", options=dates, index=0)
        times = load_available_times(selected_date)
        selected_time = st.selectbox("크롤링 시각 선택", options=times, index=0)

    df = load_ranking(selected_date, selected_time)
    if df.empty:
        st.info("선택한 날짜/시각에 해당하는 데이터가 없습니다.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("수집 종목 수", f"{len(df)}개")
    avg_rate = df["등락률(%)"].mean()
    col2.metric("평균 등락률", f"{avg_rate:+.2f}%" if pd.notna(avg_rate) else "N/A")
    col3.metric("조회 기준", f"{selected_date} {selected_time}")

    styled_df = df.style.map(style_change_value, subset=["전일대비", "등락률(%)"]).format(
        {
            "현재가": "{:,.0f}",
            "전일대비": "{:+,.0f}",
            "등락률(%)": "{:+.2f}",
            "거래량": "{:,.0f}",
            "거래대금": "{:,.0f}",
            "고가": "{:,.0f}",
            "저가": "{:,.0f}",
            "시가총액": "{:,.0f}",
        },
        na_rep="-",
    )
    st.dataframe(styled_df, use_container_width=True, height=600)

    st.subheader("상위 종목 등락률")
    top_n = df.head(15).sort_values("등락률(%)", ascending=True)
    st.bar_chart(top_n.set_index("종목명")["등락률(%)"])


if __name__ == "__main__":
    main()
