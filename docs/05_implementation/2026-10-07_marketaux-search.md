---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: [b84884a]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 12 — Marketaux 시황 검색어 필터

Task 8 을 실제로 돌려 보니 결과 6건 중 시황 기사가 1건이었다. 사용자 결정(2026-10-07)에 따라 필터를 보강했다.

## 한 일
- `MarketauxNewsProvider` 가 요청에 `search` 를 싣는다. 기본값은 `"Wall Street" | "S&P 500" | Nasdaq | "Federal Reserve" | Treasury`.
- 생성자 인자 `search` 로 바꿀 수 있다.
- 테스트 2개 추가.

## 왜 이렇게 했나
네 가지 필터를 한 번씩 실제로 호출해 비교했다 (각 3건, 같은 기간).

| 필터 | 결과 | 판단 |
|---|---|---|
| `domains=cnbc.com,reuters.com,...` | CNBC 3건. 재규어 전기차, IMF 발언 등 | 매체는 좋지만 시황과 무관한 기사가 섞인다. 10개 도메인 중 CNBC 만 나왔다 |
| `exclude_domains=seekingalpha.com,...` | 핀테크 행사, 인도 중앙은행 | 빼도 다른 잡음이 들어온다 |
| `entity_types=index` | 인도·일본 지수 기사 | `countries` 와 함께 쓰지 못해 미국에 한정되지 않는다 |
| **`search=` 시황 용어 + `countries=us`** | 3건 모두 미국 시황 | 채택 |

채택한 검색어로 3회 호출(9건)했을 때 8건이 시황·마감 기사였다(S&P 500·나스닥 사상 최고 마감, 국채 금리 급등 등). 1건은 개별 종목(Marvell)이다.

검색어를 `Settings` 로 올리지 않은 이유: 바꿀 일이 생기면 코드와 테스트를 함께 고치는 편이 안전하다. 값 하나를 위해 환경변수를 늘리지 않았다.

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/collect/test_news_marketaux.py   (구현 전)
2 failed
$ uv run pytest
src\finbrief_analyzer\collect\news_marketaux.py       74      0   100%
168 passed, 1 warning in 1.49s
$ uv run ruff check . → All checks passed!
$ uv run mypy         → Success: no issues found in 36 source files
```

## 발견한 이슈 (이번 범위 밖)
- [ ] 매체가 thestockmarketwatch.com, economictimes(인도) 위주다. 내용은 미국 시황이지만 1차 매체(로이터·블룸버그)는 무료 요금제에 거의 없다.
- [ ] 검색 결과는 최신순이 아니라 관련도순으로 온다. 어댑터가 최신순으로 다시 정렬한다.
- [ ] 오늘 Marketaux 한도를 PoC·확인에 16회가량 썼다(잔여 84회 안팎).

## 남은 것
- [ ] 없음.
