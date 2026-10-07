# finbrief-analyzer

시세·뉴스를 수집·분석해 일일 금융 브리핑을 만드는 엔진

- **PROJECT_NAME**: `finbrief-analyzer`
- **스택**: Python 3.12 · FastAPI · uv · pytest · ruff · mypy(strict)

## 작업 흐름

`docs/WORKFLOW.md` 를 따른다. 리서치 → 분석 → 플랜 → 태스크 → 구현 → 테스트.
**산출물은 이 저장소의 `docs/` 에 남긴다** (Obsidian Vault 아님 — 전역 설정보다 이 규칙이 우선).

## 명령

```bash
make install     # uv sync
make dev         # 개발 서버 :8000 (reload)
make test        # pytest + coverage
make check       # lint + typecheck + test — 커밋 전 필수
make docker      # 이미지 빌드
```

## 구조

```
src/finbrief_analyzer/
├── main.py          # create_app() 팩토리 + 엔트리포인트
├── api/routes.py    # 라우터
└── core/config.py   # Settings (APP_ 접두 환경변수)
tests/               # conftest.py 의 client 픽스처 사용
```

## 규칙

- **타입 힌트 필수.** mypy strict 를 켜 뒀다. `Any` 를 쓰려면 이유를 주석으로 남긴다.
- **설정은 `core/config.py` 의 `Settings` 로만** 읽는다. 코드 곳곳에서 `os.getenv` 금지.
- 함수 30줄 이하. 넘으면 쪼갠다.
- 주석·변수명은 영어, 문서와 대화는 한국어.
- 테스트는 Given/When/Then 주석 구조. 테스트 이름이 보장하는 성질을 말해야 한다.
- 커밋: Conventional Commits, subject 는 한국어.

## HTTP 가 필요 없다면

`api/`, `main.py` 의 FastAPI 부분과 `fastapi`/`uvicorn` 의존성을 지우고
`main.py` 를 일반 엔트리포인트로 바꿔 쓴다. 나머지(설정·테스트·린트·CI)는 그대로 쓸 수 있다.

## 인프라

```bash
make up                  # 로컬 의존 서비스 (PROFILES=db,cache,mq,mqtt,all)
make tf-plan             # 서비스 인프라 변경 미리 보기
make ecs-status          # 태스크가 어느 호스트·AZ 에 떠 있는지
make releases            # 배포할 수 있는 이미지 태그
```

- **AWS ECS on EC2.** 태스크를 2개 이상, 서로 다른 호스트·AZ 에 흩어 띄운다 —
  호스트 하나가 죽어도 서비스가 산다. `deploy/terraform/service/` 가 이 서비스의 정의다.
- **main 에 들어가면 배포된다.** push/merge → ECR 푸시(`날짜-커밋` 태그) → `deploy/ecs/deploy.sh` 가
  무중단 롤링. 롤백은 `make deploy RELEASE=<예전 태그>`.
- 태스크 정의의 모양(CPU·메모리·환경변수)은 terraform 이, 이미지 태그는 릴리스가 바꾼다.
  terraform 으로 바꾼 모양은 **다음 배포 때** 굴러간다.
- **`/health` 는 DB 등 외부 의존을 확인하지 않는다.** DB 는 이중화하지 않은 별도 EC2 다.
  헬스체크가 DB 를 보면 DB 가 느려지는 순간 ALB 가 멀쩡한 태스크를 전부 빼 버린다.
- **상태를 컨테이너 안에 두지 않는다.** 세션·파일·캐시·스케줄 잠금은 밖(DB·Redis·S3)에 둔다.
  태스크는 언제든 2개 이상이 동시에 돌고, 예고 없이 교체된다.
- **스키마 변경은 하위 호환으로.** 롤링 중에는 신·구 버전이 같은 DB 를 동시에 쓴다.
- **비밀값을 git 이나 `environment` 에 평문으로 넣지 않는다.** SSM Parameter Store 나
  Secrets Manager 에 두고 `secrets` 변수에 ARN 만 적는다. 상세는 `deploy/README.md`.
