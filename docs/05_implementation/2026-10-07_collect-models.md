---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [7f2b39a]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 2 — 도메인 모델과 제공자 인터페이스

## 한 일
- `collect/models.py`: `Slot`, `Market`, `Quote`, `NewsItem`, `MarketSnapshot`, `CollectError`.
- `collect/ports.py`: `QuoteProvider`, `RateProvider`, `NewsProvider` (`Protocol`).
- `tests/collect/test_models.py`: 12개.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| `Quote` 는 심볼·종가·전일 종가·기준일만 | 표시 이름·시장(`Market`)도 `Quote` 에 | 어댑터는 심볼만 안다. 이름·시장은 설정의 심볼 표가 아는 정보라, 어댑터가 채우게 하면 출처마다 같은 표를 들고 있어야 한다. 조립(Task 10)에서 붙인다 |
| 값은 `float` | `Decimal` | PoC 에서 원천이 소수 둘째 자리이고 합산·정산 계산이 없음을 확인했다. 표시할 때 반올림하면 된다 |
| 금리·환율도 `Quote` | `Rate` 타입을 따로 | 필요한 필드가 같다(값, 직전 값, 기준일). 미 국채 10년은 실제로 시세 어댑터에서 나온다 |
| `Quote` 가 NaN·무한대 종가를 생성 시 거부 | 어댑터마다 걸러내기 | PoC 에서 Yahoo 환율 표에 NaN 종가 행이 있었다. 한 곳에서 막아야 어댑터 하나가 빠뜨려도 브리핑에 `nan` 이 실리지 않는다 |
| 전일 종가가 NaN 이면 등락률 `None` | 생성 시 거부 | 종가는 멀쩡한데 전일 값만 깨진 경우다. 종가는 살리고 등락률만 비운다 |
| `NewsItem` 의 동일성은 링크만 | 모든 필드 비교 | 같은 기사가 피드마다 제목·요약이 조금씩 다르게 실린다. 집합에 넣으면 중복이 사라진다 |
| naive `published_at` 을 생성 시 거부 | 어댑터가 알아서 | 매일경제 피드가 실제로 시간대를 잃는다(PoC). 조용히 9시간 어긋난 채 "기준 시각 이후" 필터를 통과하는 것보다 실패가 낫다 |
| 프로토콜에 `name` 속성 | 조립 쪽에서 이름을 따로 관리 | 누락 목록에 적을 출처 이름이 필요하다. 제공자와 이름이 떨어져 있으면 어긋난다 |
| `NewsProvider.get_news(since)` | 슬롯을 넘기기 | 어댑터가 슬롯의 의미(밤사이/당일)를 알 필요가 없다. 기준 시각 계산은 조립의 일이다 |

`Market.FX`·`Market.RATE` 는 휴장 판정 대상은 아니지만 Task 10 이 심볼을 묶어 보여 줄 때 쓴다.

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect/test_models.py   (구현 전)
ERROR tests/collect/test_models.py
1 warning, 1 error in 0.14s

$ uv run pytest
src\finbrief_analyzer\collect\models.py        49      0   100%
src\finbrief_analyzer\collect\ports.py         12      0   100%
TOTAL                                         104      6    94%
12 passed, 1 warning in 0.08s      (collect 만 실행한 수치. 전체는 14 passed)
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 13 source files
```

## 발견한 이슈 (이번 범위 밖)
- [ ] pytest 경고: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` Task 3 에서 httpx 를 런타임 의존성으로 올릴 때 함께 본다.

## 남은 것
- [ ] 없음. 다음은 Task 3(설정과 의존성).
