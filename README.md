# 네이버 증권 실시간 랭킹(상승) 대시보드

[stock.naver.com 실시간 랭킹(상승)](https://stock.naver.com/market/stock/kr/stocklist/upper) 데이터를
주기적으로 크롤링해서 로컬 SQLite DB에 쌓고, 날짜별로 조회할 수 있는 대시보드입니다.

이 저장소의 코드는 **사용자의 PC(로컬 환경)에서 실행하는 것을 전제로** 작성되었습니다.
(현재 이 코드를 작성한 개발 환경은 네이버 도메인에 대한 네트워크 접근이 차단되어 있어,
실제 페이지 렌더링 결과를 직접 확인하지 못한 채 작성되었습니다. "알려진 제한사항" 항목을
꼭 읽어주세요.)

## 폴더 구조

```
apptest/
├── crawler/
│   ├── naver_rank_crawler.py   # Playwright로 랭킹 페이지를 크롤링하는 메인 스크립트
│   ├── db.py                   # SQLite DB 초기화 및 저장 로직
│   └── parsers.py              # 화면 텍스트 -> 숫자 변환 유틸리티
├── dashboard/
│   └── app.py                  # Streamlit 대시보드 (날짜별 조회)
├── data/                       # 실행 시 자동 생성됨 (stock_rank.db 저장 위치, git에는 포함 안 됨)
├── requirements.txt
└── README.md
```

## 1. 설치 (최초 1회)

```bash
# (선택) 가상환경 생성
python -m venv .venv
source .venv/bin/activate   # Windows는 .venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# Playwright가 사용할 브라우저(Chromium) 설치
playwright install chromium
```

## 2. 크롤러 실행

```bash
python -m crawler.naver_rank_crawler
```

- 실행할 때마다 현재 날짜/시각을 기준으로 랭킹 데이터를 `data/stock_rank.db` 에 저장합니다.
- 옵션
  - `--max-rows 50` : 수집할 최대 종목 수 (기본값 50)
  - `--show-browser` : 브라우저 창을 직접 보면서 디버깅하고 싶을 때 사용

### 매일 자동으로 수집하고 싶다면 (스케줄링)

이 저장소 자체에는 스케줄러가 포함되어 있지 않습니다. 사용자의 PC에서 OS의
스케줄링 기능을 이용해 위 명령을 주기적으로 실행하도록 등록해야 합니다.

**Linux / macOS (cron)**

```bash
crontab -e
```

아래 줄을 추가하면 평일 오후 3시 40분(장 마감 이후)에 한 번 수집합니다.
(가상환경 경로와 프로젝트 경로는 실제 환경에 맞게 수정하세요.)

```
40 15 * * 1-5 cd /path/to/apptest && /path/to/apptest/.venv/bin/python -m crawler.naver_rank_crawler >> crawler.log 2>&1
```

**Windows (작업 스케줄러)**

1. "작업 스케줄러" 실행 → "기본 작업 만들기"
2. 트리거: 매일 / 원하는 시각 (예: 15:40)
3. 동작: 프로그램 시작
   - 프로그램: `C:\path\to\apptest\.venv\Scripts\python.exe`
   - 인수 추가: `-m crawler.naver_rank_crawler`
   - 시작 위치: `C:\path\to\apptest`

## 3. 대시보드 실행

```bash
streamlit run dashboard/app.py
```

브라우저가 자동으로 열리며, 사이드바에서 **날짜**(및 해당 날짜의 크롤링 시각)를 선택하면
그 시점의 실시간 랭킹(상승) 데이터를 표와 등락률 차트로 확인할 수 있습니다.

## 저장되는 데이터 항목

스크린샷 기준 실시간 랭킹 표에 표시되는 아래 항목을 그대로 저장합니다.

| 항목 | 설명 |
|---|---|
| 순위 | 상승률 기준 순위 |
| 종목명 | 종목 이름 |
| 현재가 | 현재 주가 (원) |
| 전일대비 | 전일 대비 변동가 + 등락률(%) |
| 거래량 | 거래된 주식 수 |
| 거래대금 | 거래 대금 (원 단위로 환산해서 저장) |
| 고가 / 저가 | 당일 고가 / 저가 |
| 시가총액 | 시가총액 (원 단위로 환산해서 저장) |

## 알려진 제한사항

- 크롤러는 네이버의 비공개 API가 아니라, Playwright로 렌더링한 화면의 `<table>` 요소를
  헤더 텍스트(종목명/현재가/전일대비/거래량/거래대금/고가/저가/시가총액) 기준으로 읽어옵니다.
  이는 API 스펙을 몰라도 동작하도록 하기 위한 선택이지만, 만약 실제 페이지가 `<table>`이
  아닌 `div` 기반 커스텀 그리드로 되어 있다면 데이터를 찾지 못할 수 있습니다.
- 이 경우 크롤러가 자동으로 `debug_page.html` (프로젝트 루트)에 페이지 스냅샷을 저장합니다.
  데이터가 수집되지 않으면 이 파일의 구조를 확인해서 `crawler/naver_rank_crawler.py`의
  `_extract_rows_from_table()` 로직을 보완해야 합니다. 필요하면 이 파일 내용을 공유해
  주시면 선택자를 정확히 맞춰 드리겠습니다.
- "조 + 억"이 섞인 표기(예: "1조 2,345억")는 현재 파서가 지원하지 않습니다. 실제로 그런
  표기가 나타난다면 `crawler/parsers.py`의 `parse_won_amount()`를 보완해야 합니다.
