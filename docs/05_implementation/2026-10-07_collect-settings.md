---
type: implementation
project: finbrief-analyzer
topic: data-sources
created: 2026-10-07
status: done
source_task: "[[2026-10-07_data-sources]]"
commits: []
blog_candidate: false
tags: [implementation]
---

# 🛠️ 구현: data-sources Task 3 — 설정과 의존성

## 한 일
- `Settings` 에 API 키 3개, 시세 심볼 목록, RSS 피드 목록, Marketaux 슬롯당 호출 상한, HTTP 타임아웃을 추가했다.
- 런타임 의존성 4개를 버전과 함께 고정했다: `httpx==0.28.1`, `finance-datareader==0.9.202`, `yfinance==1.7.0`, `defusedxml==0.7.1`. 개발 의존성에 `types-defusedxml`.
- `uv.lock` 을 처음으로 커밋했다.
- `.env.example`, `terraform.tfvars.example` 에 새 변수 이름을 넣었다.
- 로컬 `.env` 의 키 이름 3개를 `APP_` 접두 이름으로 바꿨다 (값은 그대로, git 제외 파일).

## 왜 이렇게 했나
| 결정 | 대안 | 고른 이유 |
|---|---|---|
| 키 이름은 `APP_DART_API_KEY`·`APP_MARKETAUX_TOKEN`·`APP_ECOS_API_KEY` | 기존 `.env` 의 `OPENDART_KEY` 등에 별칭으로 맞추기 | `Settings` 의 다른 변수가 전부 `APP_` 접두다. 별칭을 두면 운영(`secrets`)과 로컬의 이름이 갈린다. 로컬 `.env` 한 곳만 고치면 끝난다 |
| 심볼 목록은 `QuoteSymbol(symbol, name, market)` 의 튜플 | 심볼 문자열 목록 | Task 2 에서 `Quote` 가 이름·시장을 갖지 않게 했다. 그 대응표가 있을 곳은 설정이다 |
| 기본 심볼에 환율 없음, `US10YT` 있음 | 설계 메모의 "국내 2·미국 3·환율 1" | PoC 뒤 사용자 결정. 환율은 ECOS 매매기준율로 간다 |
| 빈 문자열 키는 `None` | 빈 `SecretStr` 로 두기 | `.env.example` 을 복사하면 `APP_ECOS_API_KEY=` 가 된다. 빈 키로 호출해 인증 오류를 받는 것보다 "비활성"이 맞다 |
| 타임아웃 기본 30초, 전 출처 공통 | 출처별 타임아웃 | PoC 에서 Marketaux 가 15초에 타임아웃이 났고 그 요청도 한도에서 빠졌다. 하루 2회 배치라 길어도 해가 없다. 출처별로 나눌 근거는 아직 없다 |
| 슬롯당 Marketaux 호출 기본 3회, 상한 50 | 상한 없음 | 무료 한도가 하루 100회, 슬롯이 2개다. 설정 실수로 한도를 넘지 않게 한다 |
| 테스트는 작업 디렉터리를 임시 폴더로 옮기고 `Settings()` 생성 | `Settings(_env_file=None)` | 개발자의 실제 `.env` 가 테스트에 섞이지 않게 한다. `_env_file` 인자는 mypy strict 에서 `type: ignore` 가 필요하다 |
| `core/config.py` 가 `collect.models.Market` 을 import | 시장을 문자열로 두기 | 오타 난 시장 이름이 설정 로드 시점에 걸린다. `models.py` 는 표준 라이브러리만 쓰므로 순환이 생기지 않는다 |

mypy override 는 `FinanceDataReader.*`, `yfinance.*` 두 모듈로 한정했다. 아직 import 하는 코드가 없지만(Task 4·5) mypy 가 경고 없이 통과한다.

## 막혔던 부분 / 해결 과정
없음.

## 검증 결과
```
$ uv run pytest tests/test_config.py   (구현 전)
9 failed, 1 warning in 0.20s

$ uv run pytest
src\finbrief_analyzer\core\config.py           30      0   100%
TOTAL                                         123      4    97%
23 passed, 1 warning in 0.11s
$ uv run ruff check .
All checks passed!
$ uv run mypy
Success: no issues found in 14 source files
```
로컬 `.env` 로 `Settings()` 를 만들어 키 3개가 모두 읽히고 `repr` 에 값이 나오지 않는 것을 확인했다.

## 발견한 이슈 (이번 범위 밖)
- [ ] `finance-datareader` 가 `plotly`, `lxml`, `pandas`, `numpy` 를 끌고 온다. 운영 이미지가 커진다. 크기는 재지 않았다.
- [ ] pytest 의 `StarletteDeprecationWarning` (httpx 대신 httpx2 권장)은 그대로다. httpx 를 고정했으므로 당장은 영향 없다.

## 남은 것
- [ ] 운영 배포 전 SSM Parameter Store 에 키 3개를 넣고 `terraform.tfvars` 의 `secrets` 에 ARN 을 적는다 (delivery-channels Task 8 과 함께).
