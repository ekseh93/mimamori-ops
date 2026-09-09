# 실행·배포·장애 대응

## 1. 로컬 검증

현재 폴더에서 PowerShell로 실행한다. `.venv`가 없다면 먼저 만든다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m mimamori demo --output artifacts/local/demo.md
.\.venv\Scripts\python -m pip install -r requirements.txt --target build/dependencies
.\.venv\Scripts\python scripts/package.py
terraform -chdir=infra init -backend=false -input=false
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra validate
terraform -chdir=infra test
```

순서대로 성공을 확인한다. Python 표준 라이브러리만 쓸 때 AWS 모의 테스트와 release 테스트는 skip된다. 모든 테스트 실행에는 개발 의존성이 필요하다. Lambda 배포 zip은 runtime 의존성만 포함한다. `build/dependencies`는 패키지 버전을 바꿀 때 오래된 파일을 섞지 말고 새로운 임시 디렉터리에 다시 설치하여 `scripts/package.py <디렉터리>`로 만든다. CI는 매번 깨끗한 runner에서 빌드한다.

## 2. AWS 최초 배포 — 아직 실행하지 않음

이 단계는 계정 리소스 생성·비용·이메일 구독 요청이 발생할 수 있다. 계정, 허가된 대상 URL, 수신자, 비용 범위와 plan을 검토해 사용자가 승인한 뒤 실행한다.

1. 기존 프로젝트 계정을 추정해서 사용하지 않는다. 지정된 프로파일에 대해 `aws sts get-caller-identity --profile <승인된프로파일>`로 대상을 확인하고 ID/개인정보는 공개 산출물에 남기지 않는다.
2. 무료 플랜·잔액·기존 리소스·예산 알림을 확인한다. SNS 수신자는 본인 또는 동의한 운영자로 제한한다.
3. `infra/terraform.tfvars.example`을 `infra/terraform.tfvars`로 복사하고 소유/허가된 URL을 설정한다. 처음에는 `monitoring_enabled=false`, 이메일 기능도 꺼둔다.
4. PowerShell에서 `$env:AWS_PROFILE='<승인된프로파일>'`을 설정한다. 상태 파일이 이 스택의 실제 상태인지 확인한다.
5. `terraform -chdir=infra plan -out=review.tfplan` → 자원 수·이름·삭제·권한·비용을 검토한다. plan/state는 민감 자료로 취급해 Git에 넣지 않는다.
6. 승인된 정확한 plan을 `terraform -chdir=infra apply review.tfplan`으로 적용한다. 예전 plan을 새 변경에 재사용하지 않는다.
7. 승인된 SNS 수신자와 `enable_email_notifications=true`를 별도 plan으로 반영하고 수신자가 확인 링크를 눌렀는지 확인한다. 구독 요청 전송만으로 알림 수신 완료라 하지 않는다.
8. 1개 대상부터 `monitoring_enabled=true`로 새 plan·apply한다. 로그·DynamoDB 관측·실제 정상/장애/복구 수신을 확인한다.

Terraform apply는 초기 코드만 설치한다. 이후 코드는 release workflow가 관리한다. Terraform이 alias를 예전 버전으로 되돌리지 않도록 코드 hash·alias 버전 소유권을 분리했다. 환경 설정 변경은 Terraform이 관리하지만, **publish된 기존 alias의 환경 설정은 바뀌지 않으므로 이후 release workflow로 새 버전을 발행·검증·승격해야 한다.** 대상 URL 추가/변경 시 특히 이 순서를 지킨다.

## 3. GitHub 협업·배포 활성화 — 아직 설정하지 않음

- 사용자가 계정·저장소 이름·공개 범위를 정한 뒤 원격 저장소와 PR 생성.
- `main`에 PR·CI 필수 규칙 설정. 개인 검토를 타인의 승인처럼 기록하지 않는다.
- `aws-learning` environment에서 main만 배포 가능하도록 설정하고 사용 가능한 플랜이면 reviewer 승인 설정. 플랜 제한으로 approval protection을 쓸 수 없으면 `AWS_DEPLOY_ENABLED`를 비활성화한 채 수동 승인 방식으로 진행.
- 계정의 기존 GitHub OIDC provider를 사용하거나 별도 검토 후 생성. OIDC subject는 실제 저장소의 형식을 확인한다. 2026-07-15 이후 생성 저장소는 immutable owner/repo ID 형식이 적용될 수 있으므로 이름만 쓰는 예제를 그대로 복사하지 않는다.
- 확인된 provider ARN과 정확한 subject로 Terraform release role을 추가한다. 와일드카드 trust는 쓰지 않는다.
- repository variables: `AWS_DEPLOY_ENABLED=true`(자동 배포를 승인한 뒤), `AWS_RELEASE_ROLE_ARN`, `AWS_FUNCTION_NAME`. 환경 보호 규칙은 필수다. 활성화 후 main의 코드 변경은 CI 후 배포 경로를 탄다.
- 장기 access key를 GitHub secret에 복사하지 않는다. workflow는 OIDC로 단기 권한을 받는다.
- workflow actions는 공식 저장소의 확인한 commit SHA에 고정. Dependabot 변경도 리뷰한다.
- 배포 흐름: CI 통과 → 그 실행의 zip artifact → hash/RevisionId로 버전 발행 → 후보 설정 smoke → live alias 교체 → 재검증. 실패 시 이전 alias 복원 시도.
- 이 smoke는 설정/로드 확인이다. 고객 사이트 접속·DB 권한·SNS 실제 수신 검증은 별도다.

출처: [GitHub AWS OIDC 문서](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) (2026-09-09 확인).

## 4. 롤백

배포 artifact의 `release.json`에 이전 버전과 새 버전을 기록한다. 코드·환경 설정이 포함된 이전 published version으로 `live`를 돌린다. 현재 데이터 스키마는 동일하다는 전제이며, 향후 스키마 변경은 호환성 검토가 필요하다.

```powershell
.\.venv\Scripts\python scripts/release.py --function <승인된함수이름> --rollback <확인한이전버전번호>
```

또는 main의 Release workflow를 `rollback_version` 입력으로 실행한다. 다음 관측·Errors·SNS 수신을 확인한 후 복구 완료로 기록한다. 스크립트의 자동 alias 복원도 AWS 오류/동시 변경으로 실패할 수 있어 확인이 필요하다.

## 5. 알림별 1차 대응

| 증상 | 확인 순서 | 판단·에스컬레이션 |
|---|---|---|
| timeout/dns_error | 대상 DNS, 내 네트워크·다른 관측 지점, 최근 DNS 변경 | 단일 관측으로 사이트 전체 장애라고 단정하지 않음 |
| tls_error | 시스템 시각, 호스트명 일치, 체인·만료, 최근 인증서 변경 | 검증을 끄지 말고 사이트 관리자에게 사실 전달 |
| http_error | 상태 코드, 동일 URL 브라우저 확인, 최근 배포·WAF 정책 | 403은 봇 차단 가능, 503만으로 DB 원인 단정 불가 |
| redirect_not_followed | 최종 HTTPS URL과 변경 여부 | 승인된 최종 URL로 설정 변경 PR |
| Lambda Errors | CloudWatch request ID와 오류 범주, IAM/DB/SNS 상태 | 알림 실패나 저장 실패를 대상 사이트 장애와 구분 |
| no-checks | Scheduler 상태, Lambda invocation/throttle, 완료 로그, 대상 설정 버전 | 누락 시간을 정상으로 보고하지 않음 |
| SQS DLQ | Scheduler 전달 실패인지 Lambda 실행 실패인지 구분 | 과거 이벤트를 무조건 재실행하지 않음. 원인 수정 후 새 점검 확인 |

고객에게는 발생/확인 시각, 대상, 관측 사실, 아직 모르는 것, 다음 확인 시각을 전달한다. 비밀 값·전체 응답 본문·개인정보를 붙이지 않는다.

## 6. 장애 훈련

자동 로컬 demo: 00:05와 00:10 실패 → DOWN, 00:15와 00:20 성공 → UP, 00:25는 미관측. 보고서에서 9/10 관측·90% 커버율·77.78% 관측 성공률 확인. 이는 생성된 모의 시간이며 실제 탐지·복구 실적이 아니다.

사용자가 직접 할 실습: `tests/test_core.py`에서 일시 실패/지속 실패/복구/누락을 각각 실행하고 왜 알림 개수가 달라지는지 설명한다. AWS에서는 고객 사이트를 일부러 고장 내지 않고, 소유한 별도 테스트 URL의 응답을 조절하는 훈련만 승인 범위에서 수행한다.

## 7. 중단·보관·삭제

`monitoring_enabled=false`로 새 plan/apply하면 스케줄과 경보 action을 비활성화한다. 이미 큐에 들어간 invocation은 남을 수 있다. 무료 초과 긴급 상황에서는 승인된 계정의 해당 Scheduler를 우선 중지하고 요청 감소를 확인한다.

보고서는 `python -m mimamori report --table <테이블명> --id <대상ID> --start ... --end ...`으로 로컬에 저장한다. 보고서는 표본 요약이며 전체 DB 백업이 아니다. 필요 원시 데이터 백업은 별도 검토한다. **현재 PITR/자동 백업·복원은 구현하지 않았다.**

완료 후 해당 스택의 실제 state에서 `terraform plan -destroy`를 검토하고 승인 후 삭제한다. 빈/잘못된 state로 작업하지 않는다. DynamoDB 삭제 전 필요한 데이터가 보존되었는지 확인한다. 로컬 state/plan과 GitHub artifact 보관 정책도 검토한다.
