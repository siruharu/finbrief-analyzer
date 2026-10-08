---
type: implementation
project: finbrief-analyzer
topic: stock-screening
created: 2026-10-08
status: done
source_task: "[[2026-10-08_stock-screening]]"
commits: [e0c4f44]
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: stock-screening Task 8 — 수집·작성에 연결하고 메일에 싣기

끝에서 끝까지 이었다. `APP_SCREEN_ENABLED=true` 면 브리핑 메일에 "조건 충족 종목" 섹션 네 개와 고지 문구가 실린다. 기본값은 꺼짐이다.

## 한 일
- `screen/service.py`: `ScreenService.run(now)`, `screen_group`(순수 함수), `ScreenDeps`, `build_screen_deps`, `build_screen_service`.
- `collect`: `MarketSnapshot.screens`, `Providers.screens`, 실패 시 `missing` 에 `"screen"`.
- `deliver`: `Briefing.footnotes` 와 본문 맨 아래 렌더링 (text·HTML).
- `compose/simple.py`: 조건 충족 종목 섹션, 종목 한 줄, 고지 문구.
- `Settings`: `screen_enabled`(False), `screen_top`(5), 최소 거래대금(10억 원 / 2천만 달러), `screen_update_seconds`(240).
- `store/price_bars.py`: `histories` (여러 종목의 이력을 한 번에).
- `jobs`: 발송 작업이 스크리닝을 수집의 한 출처로 붙인다. 처음 받기 명령은 같은 배선(`build_screen_deps`)을 쓴다.
- 테스트 29개 추가 (스크리닝 서비스 12, 작성기 10, 렌더러 3, 수집 3, 저장소 1).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 스크리닝은 **수집의 한 출처** (`Providers.screens`) | 발송 작업이 따로 부른다 | 실패 처리가 기존 규칙 그대로다: 예외를 삼키고 `missing` 에 올린 뒤 브리핑은 나간다. 본문 상단의 "일부 출처를 가져오지 못했습니다" 안내에 `screen` 이 같이 뜬다 |
| 규칙 적용(`screen_group`)은 **순수 함수**, DB·시계는 `ScreenService` 에만 | 한 클래스 | 같은 함수를 백테스트가 날짜만 바꿔 부를 수 있다. 테스트가 DB 없이 경우를 만든다 |
| **최신 거래일에 거래가 없던 종목은 제외** | 각자의 마지막 날로 계산 | 일주일 전에 거래가 멈춘 종목의 그날 거래량 급증이 "오늘의 급증"으로 실린다. 테스트로 고정했다 |
| 국내는 KOSPI + KOSDAQ 을 **한 묶음**으로 순위 | 거래소별로 따로 | 메일에서는 "국내"가 한 단위다. 섹션이 6개가 되면 길다 |
| `ScreenResult` 는 `exchanges` 를 든다 | `Market.KR`/`US` | `collect.models` 가 `ScreenResult` 를 참조한다. 반대 방향으로도 참조하면 순환 import 가 된다 |
| 고지 문구는 **각주**(`Briefing.footnotes`) | 안내(`notices`)에 넣는다 | 안내는 본문 맨 위에 굵게 나온다. 누락·휴장처럼 "오늘 이 메일이 평소와 다르다"를 알리는 자리다. 매번 같은 고지가 그 자리를 차지하면 진짜 안내가 묻힌다 |
| 조건 충족 섹션이 없으면 고지 문구도 없다 | 항상 싣는다 | 가리키는 목록이 없는 고지는 소음이다 |
| 섹션은 `required=False`, 필수 판정에 끼지 않는다 | 시세 묶음처럼 취급 | "시세가 하나도 없으면 보내지 않는다"는 그대로다. 종목 목록만 있는 브리핑은 브리핑이 아니다 |
| 제목·문구에 "추천"·"매수"·"유망"을 쓰지 않는다 (테스트로 고정) | 주석으로만 | 분석의 가장 큰 리스크가 "목록을 매수 추천으로 읽는다"였다. 나중에 문구를 고치다 들어가는 것을 막는다 |
| 기준일을 섹션마다 적는다 | 한 번만 | 국내와 미국의 기준일이 다를 수 있다. "어제"라고 쓰지 않는다 — 월요일 아침의 기준일은 금요일이다 |
| `screen_enabled` 기본값 False | True | 처음 받기를 하지 않은 DB 에서 켜지면 발송 작업이 850종목을 받으려 든다(시간 상한 240초 안에서). 켜는 것은 처음 받기를 한 사람이 한다 |
| 발송 작업 안의 갱신에 **시간 상한** | 상한 없음 | 순위 조회가 죽어 종목별 조회로 넘어가면 2분이 걸린다. 상한을 넘으면 남은 종목은 다음 실행으로 넘기고 있는 이력으로 스크리닝한다 |

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
uv run pytest tests/compose tests/collect tests/jobs tests/deliver  → 통과
uv run ruff check .                                                 → All checks passed!
uv run mypy                                                         → Success: no issues found in 88 source files
uv run pytest                                                       → exit 0, 커버리지 98%
```
실제 실행 (2026-10-08 12:30 KST, 이번 실행에만 `APP_SCREEN_ENABLED=true`, 발송하지 않음):
```
price history: added=0 loaded=0 reloaded=0 failed=0 skipped=0
■ 조건 충족 종목 — 국내 52주 신고가 근접
종가가 최근 52주 최고 종가에 가까운 순 (2026-10-07 종가 기준)
한미사이언스 66,200 (+14.73%) · 고가 대비 100.0%
케이씨텍 120,100 (+12.98%) · 고가 대비 100.0%
…
■ 조건 충족 종목 — 국내 거래량 급증
삼표시멘트 7,830 (+15.32%) · 평소의 68.9배
펩트론 96,900 (-25.12%) · 평소의 8.2배
…
■ 조건 충족 종목 — 미국 52주 신고가 근접 / 미국 거래량 급증 (각 5개)
※ 조건 충족 종목은 정해진 규칙에 따라 자동으로 뽑은 목록입니다. …
screens=4 missing=() collect=32.6s
```
- 수집 전체가 32.6초다 (스크리닝이 꺼졌을 때 23.5초). 853종목의 이력을 읽고 규칙을 적용하는 데 약 9초.
- 52주 고가 근접은 5개 모두 "고가 대비 100.0%"다. 동점이 많아 당일 등락률이 순위를 정했다 (PoC 에서 예상한 대로).

## 발견한 이슈 (이번 범위 밖)
- [ ] **52주 신고가 근접의 상위 5개가 전부 100.0% 라 숫자가 정보를 주지 않는다.** 사실상 "어제 52주 신고가를 새로 쓴 종목 중 많이 오른 순"이다. 표시를 "52주 신고가"로 바꾸거나 신고가 종목 수를 같이 적는 편이 정직하다.
- [ ] **거래량 급증은 방향을 가리지 않는다.** 펩트론은 -25% 다. 등락률을 같이 보여 주지만, 급락 종목이 "조건 충족"에 실리는 것이 기대와 다를 수 있다.
- [ ] 미국 종목 이름이 영문이다 (목록의 이름 그대로).
- [ ] 스크리닝이 켜지면 수집이 9초쯤 늘어난다.
- [ ] 스크리닝의 `missing` 표시가 `screen` 이라는 영문 그대로 안내에 실린다.

## 남은 것
- [ ] `.env` 에 `APP_SCREEN_ENABLED=true` — 사용자가 켠다.
- [ ] 실제 메일로 받아 보는 것.
- [ ] 장 마감 뒤 실행에서 국내 하루치가 순위 조회로 덧붙는지 (Task 6 의 남은 확인).
