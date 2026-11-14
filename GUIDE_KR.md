# AWS 배포 따라하기 가이드

처음부터 끝까지 순서대로 따라 하면 돼요. 예상 소요 시간은 1.5~2시간 정도(AWS 계정이 이미 있으면 더 짧아요).
**각 단계 끝의 "확인" 항목이 맞는지 보고 다음으로 넘어가세요.** 안 맞으면 맨 아래 "문제 해결"을 먼저 보세요.

## 0. 전체 그림

```
내 코드 --push--> GitHub --Actions(테스트 -> 이미지 빌드)--> ECR(이미지 저장소)
                                                            |  새 이미지가 올라오면 자동 배포
브라우저 --HTTPS--> ECS Express Mode(Fargate 위의 내 FastAPI 컨테이너) --> DynamoDB(기록 저장, 30일 후 자동 삭제)
                      |-- Secrets Manager(API 키 보관)
                      |-- CloudWatch Logs(로그)
```

* **더미 데이터만** 씁니다. 실제 전문가 정보나 회사 내부 내용은 절대 올리지 마세요(GitHub에 공개되는 코드예요).
* Anthropic API 키는 **선택**이에요. 없어도 "템플릿 모드"로 전부 동작하고, 있으면 AI가 코멘트와 시간대 해석을 해줘요.
* 비용: 트래픽이 없어도 Fargate와 로드밸런서(ALB) 요금이 계속 나와요(대략 월 20달러 안팎). **다 쓰고 나면 11번으로 반드시 삭제**하세요.
  정확한 요금은 AWS 요금 페이지에서 확인하세요.

## 1. 준비물

* **AWS 계정** (카드 등록 필요). 새 계정이면 무료 크레딧이 있을 수 있어요.
* **GitHub 계정**
* 내 컴퓨터(Mac)에 **Python 3.12(또는 3.10 이상)**와 **git**
  * 확인: 터미널에서 `python3 --version`, `git --version`
* (선택) Anthropic API 키(`sk-ant-...`)

## 2. 내 컴퓨터에서 먼저 실행해 보기

압축을 푼 `expert-profile-api` 폴더에서:

```bash
cd expert-profile-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

**확인:** `18 passed`가 나와야 해요.

서버 실행:

```bash
export APP_API_KEY=dev-key
uvicorn app.main:app --reload
```

브라우저에서 http://localhost:8000 → 위쪽 "API key"를 펼쳐 `dev-key` 입력 → "Sample 1" 클릭 → "Generate profile".

**확인:** 서식이 적용된 프로필이 오른쪽에 나오고, 노란 안내문이 "template comment was used"라고 보이면 정상(키 없는 템플릿 모드)이에요.
끝났으면 터미널에서 `Ctrl+C`로 서버를 끄세요.

## 3. AWS 계정 안전 설정 (10분)

1. **루트 계정에 MFA 설정**: 콘솔 오른쪽 위 계정 이름 > Security credentials > Multi-factor authentication.
2. **예산 알림 설정**: 콘솔 검색창에 "Budgets" > Create budget > "Zero spend budget" 또는 월 5달러 예산 > 이메일 입력.
3. 학습용이라면 **루트 대신 IAM 사용자**로 쓰는 걸 추천해요: IAM > Users > Create user > 권한 `AdministratorAccess`(학습 용도로만) + MFA. 이 사용자로 로그인해서 아래를 진행하세요.
4. 콘솔 오른쪽 위에서 **리전을 "Asia Pacific (Tokyo) ap-northeast-1"**(서울 대신 도쿄를 쓰는 이유: 서비스를 올릴 리전을 하나로 맞추기 위해서예요)로 선택하세요. 아래 모든 단계가 이 리전 기준이에요.

## 4. GitHub 저장소 만들고 코드 올리기

1. GitHub에서 **New repository** → 이름 `expert-profile-api` → **Public**(공개) → README 등은 추가하지 않고 생성.
   * 공개 저장소로 만드는 이유: 6번에서 AWS CloudShell이 코드를 내려받아야 해서 가장 간단해요. 코드엔 더미 데이터와 비밀번호가 없는지 한 번 더 확인하세요(`.env`는 `.gitignore`에 들어 있어요).
2. 내 컴퓨터 터미널에서 (USER를 내 GitHub 아이디로):

```bash
cd expert-profile-api
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USER/expert-profile-api.git
git push -u origin main
```

**확인:** GitHub 저장소 > **Actions** 탭에 `ci-cd` 실행이 보여요. `test` 작업은 초록색(성공)이고 `build-and-push`는 **건너뜀(skipped)**이면 정상이에요. 아직 AWS 연결 전이라서 일부러 건너뛰게 해 놨어요.

## 5. AWS CloudShell 열기

콘솔 위쪽 검색창 왼쪽의 **CloudShell 아이콘(`>_`)**을 누르세요. 도쿄 리전인지 다시 확인하세요. 잠시 후 터미널이 열려요.

```bash
aws sts get-caller-identity
```

**확인:** 계정 번호가 JSON으로 나오면 정상이에요.

## 6. AWS 리소스 만들기 (setup.sh)

CloudShell 터미널에서 (USER를 내 GitHub 아이디로):

```bash
git clone https://github.com/USER/expert-profile-api.git
cd expert-profile-api
export GITHUB_REPO="USER/expert-profile-api"
export ANTHROPIC_API_KEY="sk-ant-..."     # 없으면 이 줄은 건너뛰세요
bash infra/setup.sh
```

이 스크립트가 만드는 것:
1. DynamoDB 테이블(기록 저장, 30일 뒤 자동 삭제)
2. ECR 저장소(컨테이너 이미지)
3. Secrets Manager 비밀값(서비스 API 키 자동 생성 + 선택적으로 Anthropic 키)
4. (ECS용 역할은 8단계 스크립트가 만들어요)
5. 실행 중 서비스의 최소 권한 역할(DynamoDB 쓰기/조회, 비밀값 읽기만)
6. GitHub Actions용 배포 역할(OIDC 방식이라 AWS 액세스 키를 GitHub에 저장하지 않아요)

**확인:** 마지막에 `Done. Next:` 안내와 함께 **`AWS_ROLE_ARN`** 값과 **API 키(긴 문자열)**가 출력돼요. 두 값을 메모해 두세요.
(API 키는 나중에 Secrets Manager 콘솔에서 `expert-profile-api/app-api-key`로도 볼 수 있어요.)

## 7. GitHub에 변수 2개 추가하고 이미지 올리기

1. GitHub 저장소 > **Settings > Secrets and variables > Actions > Variables 탭 > New repository variable**
   * `AWS_REGION` = `ap-northeast-1`
   * `AWS_ROLE_ARN` = 6번에서 출력된 `arn:aws:iam::...:role/expert-profile-api-github-deploy`
2. 내 컴퓨터 터미널에서 실행을 다시 일으키기:

```bash
git commit --allow-empty -m "trigger deploy"
git push
```

**확인:** GitHub **Actions**에서 `test`와 `build-and-push`가 둘 다 초록색이고, AWS 콘솔 > **ECR > Repositories > expert-profile-api**에 `latest` 이미지가 보여요.

## 8. ECS Express 서비스 만들기 (create-service.sh)

CloudShell에서:

```bash
cd ~/expert-profile-api
bash infra/create-service.sh
```

점이 찍히면서 몇 분 기다린 뒤 마지막에 `Service URL: https://xxxx.ecs.ap-northeast-1.on.aws` 형태의 주소이 출력돼요.

**확인:** 브라우저에서 `그 주소/health`를 열면 `{"status":"ok","llm":...,"storage":"dynamodb"}`가 보여요. `storage`가 **dynamodb**여야 정상(DB 연결됨)이에요.

## 9. 실제로 써 보기

1. 서비스 주소 접속 → 위쪽 "API key"에 6번에서 메모한 키 입력 → "Sample 1" → "Generate profile".
2. 아래 "Recent" 목록에 방금 만든 항목이 나오면 DynamoDB 저장까지 성공한 거예요.
3. AWS 콘솔 > **DynamoDB > Tables > expert-profile-api-history > Explore table items**에서도 항목을 볼 수 있어요.
4. 로그: **CloudWatch > Log groups**에서 `expert-profile-api`가 들어간 로그 그룹에서 `profile created ...` 로그를 볼 수 있어요.
5. 키 없이 호출하면 막히는지도 확인해 보세요(면접 때 보여주기 좋아요):

```bash
curl -i -X POST https://그주소/api/profile -H "Content-Type: application/json" -d '{}'
```

**확인:** `401 Invalid or missing API key`가 나와요.

## 10. 자동 배포 체험하기 (CI/CD)

1. `app/static/index.html`의 제목 글자 하나를 바꾸고 push:

```bash
git add . && git commit -m "Change title" && git push
```

2. GitHub Actions가 테스트 → 이미지 빌드/푸시를 하고, 새 이미지가 ECR에 올라가요. 서비스에 반영하려면 CloudShell에서 `bash infra/create-service.sh` 대신 ECS 콘솔의 서비스 > **Update service > Force new deployment**를 누르세요.

## 11. 다 쓰고 나서 삭제하기 (중요)

데모를 확인했고 계속 켜 둘 필요가 없으면:

```bash
cd ~/expert-profile-api
bash infra/teardown.sh
```

서비스, 이미지 저장소, 테이블, 비밀값, 역할이 모두 삭제돼요. 나중에 면접 전에 다시 쓰려면 6번부터 다시 하면 돼요(약 20분).
(ECS Express는 일시 중지가 없어요. 비용을 멈추려면 삭제하세요.)

## 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| `pytest`에서 모듈을 못 찾음 | 가상환경이 꺼져 있어요. `source .venv/bin/activate` 후 다시 `pip install -r requirements-dev.txt` |
| 화면에서 `Invalid or missing API key` | 키를 잘못 넣었어요. 로컬은 `dev-key`, AWS는 6번에서 출력된 키예요 |
| `503 Server is not configured` | 서버에 `APP_API_KEY`가 없어요. 로컬은 `export APP_API_KEY=dev-key`를 하고 서버를 다시 켜세요 |
| `setup.sh`가 `Set GITHUB_REPO first`라고 함 | `export GITHUB_REPO="USER/expert-profile-api"`를 먼저 실행하세요 |
| Actions의 `build-and-push`가 계속 skipped | 7번의 변수 `AWS_ROLE_ARN`을 추가했는지 확인하세요(오타 주의) |
| Actions에서 `Could not assume role` 같은 오류 | ① `GITHUB_REPO` 오타, `main` 브랜치가 아님 → 바로잡고 `bash infra/setup.sh` 재실행(안전). ② 이름이 맞는데도 실패하면 GitHub가 보내는 `sub` 값이 다른 형식일 수 있어요(새 저장소는 `repo:아이디@숫자/저장소@숫자:ref:refs/heads/main`처럼 ID가 들어감). 워크플로에 `sub`를 출력하는 디버그 단계를 넣어 실제 값을 확인한 뒤, `export GITHUB_SUB="그 값"`을 설정하고 `bash infra/setup.sh`를 다시 실행하세요 |
| `create-service.sh`가 `No ':latest' image` | 7번이 끝나지 않았어요. Actions가 초록색인지, ECR에 이미지가 있는지 확인하세요 |
| 서비스 생성 오류 | ECS 콘솔 > 클러스터 default > 서비스의 Events/Logs에서 이유를 보세요. 이미지가 없거나 역할 권한이 아직 전파되지 않은 경우가 많아요. `teardown.sh`는 하지 말고 서비스만 콘솔에서 삭제한 뒤 1~2분 후 `create-service.sh`를 다시 실행하세요 |
| `/health`의 `storage`가 `memory` | 환경 변수 `DDB_TABLE`이 안 들어갔어요. create-service.sh로 만든 서비스인지 확인하세요 |
| 기록(Recent)이 안 보임 | 인스턴스 역할 권한 문제일 수 있어요. 로그에서 `history save failed`를 찾아 오류 내용을 확인하세요 |

## 12. 이력서에 쓰기 (실제로 끝낸 항목만!)

면접(1차 실무면접)에서 구조를 직접 설명할 수 있어야 해요. 아래 체크리스트를 **직접 해 본 것만** 쓰세요.

- [ ] 로컬에서 실행하고 `pytest` 18개 통과를 직접 확인했다
- [ ] AWS에 실제로 배포하고 URL에서 동작을 확인했다
- [ ] GitHub push로 자동 배포되는 것을 직접 확인했다
- [ ] CloudWatch 로그와 DynamoDB 항목을 직접 열어 봤다

문구 예시(해당하는 것만 사용):

* **AI 프로필 생성 API** (Python, FastAPI, Docker, AWS) — 경력 텍스트와 검증 질문을 받아 서식화된 프로필을 생성하는 REST API를 구현하고,
  Claude API로 코멘트와 면접 가능 시간(시간대·서머타임 반영) 변환을 처리. LLM 키가 없거나 호출이 실패해도 템플릿으로 동작하도록 설계.
* Amazon ECS Express Mode(Fargate 컨테이너 + ALB), DynamoDB(TTL), Secrets Manager, CloudWatch로 구성하고, GitHub Actions(OIDC)로 테스트·이미지 빌드·ECR 푸시·이미지 배포 파이프라인 구축.
  최소 권한 IAM 역할 분리와 API 키 인증 적용. pytest 18개 테스트 작성.

면접 예상 질문과 준비할 답:
* **왜 ECS Express Mode를 썼나요?** App Runner가 2026-04-30부터 신규 계정에 닫혀서, AWS가 권장하는 후속 서비스를 썼어요. 서버 관리 없이 Fargate 컨테이너와 HTTPS 로드밸런서를 한 번에 구성해줘요.
* **보안은 어떻게 했나요?** AWS 키를 GitHub에 저장하지 않고 OIDC로 단기 자격증명을 쓰고, 역할을 이미지 pull / 서비스 실행 / CI로 나눠 최소 권한을 부여했어요. API 키는 Secrets Manager에서 주입해요.
* **LLM이 실패하면요?** 템플릿 코멘트와 ISO 형식 파서로 대체해서 서비스가 멈추지 않아요.
* **한계는요?** DynamoDB Scan 사용, 단일 공유 API 키, WAF/레이트 리밋 없음. 개선안은 GSI, 사용자별 키, WAF, Terraform이에요.

## 부록. GitHub가 보내는 `sub` 값 직접 확인하기 (디버그)

`Could not assume role` 오류가 이름이 맞는데도 나올 때만 쓰세요. `.github/workflows/ci-cd.yml`의 `build-and-push` 작업에서
`actions/checkout` 단계 바로 아래에 아래 단계를 임시로 넣고 push하면, 로그에 실제 `sub` 값이 찍혀요. 확인이 끝나면 지우세요.

```yaml
      - name: Print OIDC claims (debug)
        continue-on-error: true
        run: |
          RESP=$(curl -sS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com")
          echo "$RESP" | python3 -c "
          import sys, json, base64
          t = json.load(sys.stdin)['value'].split('.')[1]
          t += '=' * (-len(t) % 4)
          d = json.loads(base64.urlsafe_b64decode(t))
          print({k: d.get(k) for k in ['sub', 'aud', 'repository', 'ref']})
          "
```

예를 들어 `repo:아이디@104573477/expert-profile-api@1457614909:ref:refs/heads/main`처럼 숫자가 붙어 있으면,
`export GITHUB_SUB="그 값"`을 설정한 뒤 `bash infra/setup.sh`를 다시 실행하세요.


| `Account ... can't create new App Runner services` | App Runner는 신규 계정에 닫혀 있어요. 이 버전의 `create-service.sh`는 ECS Express Mode를 쓰니 최신 파일로 다시 실행하세요 |