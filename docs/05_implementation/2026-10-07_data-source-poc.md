---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: []
blog_candidate: true
tags: [implementation, poc]
---

# 🛠️ 구현: data-sources Task 1 — 출처 PoC

## 한 일
- 시세(FinanceDataReader·yfinance), 금리(ECOS·FRED), 뉴스(RSS 6개·Marketaux·DART)를 실제로 호출해 응답 모양과 오류 모양을 확인했다.
- 결과를 `docs/01_research/2026-10-07_data-source-poc.md` 에 적었다. 확정 심볼 표와 금리 채택 결정이 들어 있다.
- 코드 변경은 없다. 일회성 스크립트는 저장소 밖 scratch 에 두고 커밋하지 않았다.

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 국내 지수 심볼을 `^KS11`·`^KQ11` 로 | 분석이 가정한 `KS11`·`KQ11` | `KS11` 은 2026-09-17 에서 멈춰 있다. 예외 없이 오래된 값을 준다 |
| 금리를 v1 에 포함 | 금리 제외 (Task 6 block) | ECOS 로 국고채 3년·10년의 당일 값이, `US10YT` 로 미 국채 10년이 나온다 |
| XML 파서는 `defusedxml` | 표준 `xml.etree`, `feedparser` | 외부 XML 이라 표준 파서를 직접 쓰지 않는다. 쓰는 필드가 4개뿐이라 `feedparser` 는 과하다 |
| 스크립트를 `uv run --no-project --with` 로 실행 | 프로젝트 venv 에 설치 | Task 3 에서 의존성을 고정하기 전에 `pyproject.toml` 을 건드리지 않으려고 |
| 플랜·태스크 문서는 고치지 않음 | PoC 결과를 바로 반영 | 예비 출처·환율 정의는 사용자가 정할 일이다. PoC 문서의 "열린 질문"에 남겼다 |

## 막혔던 부분 / 해결 과정
> 💡 블로그 소재. "예외 없이 틀린 값을 주는 출처"

**증상**
`fdr.DataReader("KS11", "2026-09-25")` 가 0행을 돌려줬다. 예외도 경고도 없다. 같은 호출에서 미국 지수는 정상이었다.

**가설과 검증**
1. 심볼이 틀렸다 → `KOSPI`, `KS200` 도 0행. `KRX:KS11` 은 `not supported`. 심볼 문제가 아니다.
2. 조회 기간 문제다 → 시작일을 `2026-01-01` 로 넓히니 175행이 나왔다. 그런데 **마지막 행이 09-17** 이다. 전체 조회도 같다.
3. 출처가 바뀌었다 → `KRX-INDEX:1001` 은 `ValueError: LOGOUT`. `^KS11`(Yahoo 경로)은 10-07 까지 정상.

**원인**
`KS11` 계열은 실시간 조회가 아니라 어딘가에 쌓인 표를 읽는 것으로 보이고(응답 0.1초), 그 표가 09-17 에서 갱신이 멈췄다. KRX 직접 경로는 로그인을 요구한다. 멈춘 이유까지는 확인하지 않았다.

**해결**
심볼을 `^KS11`·`^KQ11` 로 바꿨다. 그리고 Task 4 에 "마지막 행의 날짜가 기대한 거래일인가"를 보는 검사가 필요하다는 것을 적었다 — 시작일을 넓게 잡았다면 3주 묵은 종가가 조용히 실렸을 것이다.

**덤으로 드러난 것**
`^KS11` 로 바꾸고 보니 FDR 의 여섯 심볼이 전부 Yahoo 를 읽는다. yfinance 예비와 종가가 소수 여섯째 자리까지 같은 이유다. 예비 출처가 원천 장애를 막아 주지 못한다.

## 검증 결과
```
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 8 source files
$ uv run pytest
TOTAL                                       43      4    91%
2 passed, 1 warning in 0.10s
```
Task 의 완료 판정(문서에 6개 출처 이름이 있는지)은 `task done 1` 이 다시 돌린다.

## 발견한 이슈 (이번 범위 밖)
- [ ] `uv sync` 가 `uv.lock` 을 새로 만들었다. 저장소에 잠금 파일이 없었다. 커밋 여부를 정해야 한다 (Task 3 에서 의존성을 고정할 때 함께 다루는 것이 자연스럽다).
- [ ] 하네스가 Windows 콘솔(cp949)에서 `—` 를 출력하다 죽는다. `PYTHONUTF8=1` 을 주면 돈다.
- [ ] 이 PC 에 git 사용자 정보가 설정돼 있지 않다. 이번 커밋은 기존 커밋의 작성자 정보를 `-c` 로 넘겨 만들었다.
- [ ] 매일경제 RSS 의 `+09:00` 을 `parsedate_to_datetime` 이 시간대 없이 읽는다 (Task 7 에서 처리).

## 남은 것
- [ ] PoC 문서의 "열린 질문" 3개에 대한 사용자 결정 (예비 출처, 미 국채 10년의 위치, 환율 정의)
- [ ] PoC 문서의 "확인 못 한 것" 6개 — 각각 해당 Task 를 시작할 때 다시 본다
