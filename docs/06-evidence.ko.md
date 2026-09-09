# 구현·검증 상태

검증 시각: **2026-09-10 00:02 JST** (2026-09-09 15:02 UTC). 아래 결과는 AI가 이 작업에서 실행한 로컬 검증이며, 사용자가 직접 실습한 이력이나 상용 운영 이력이 아니다.

## 사용자 요청과 산출물

| 요청 | 산출물 | 완료 범위 |
|---|---|---|
| 일본 인프라 미경험 취업용 | 일본어 README·보고서·장애 기록, 역할별 증거·제약 | 작성 완료. 합격/실무 경력 보장 없음 |
| AWS SAA 수준 기획 | 네 영역 매핑, 서비스 선택·대안·추가 학습 표 | 작성 완료. 전체 시험 범위 실습은 아님 |
| 2026 트렌드·수익 아이디어 | 공식 자료·경쟁 비교·3개 후보·가격/고객 검증 가설 | 조사·기획 완료. 실제 고객/매출 없음 |
| 무료 범위 | 로컬 표준 라이브러리 실행, AWS 소규모 사용량 계산 | 로컬 실행 검증. 실제 계정 무료량 미확인 |
| 쉬운 설명 | 4주 학습표, 일본어→한국어 면접 문장 12개 | 문서 완료. 본인 설명·실습은 다음 단계 |
| CI/CD·모니터링·테스트·브랜치 | Python 서비스, Terraform, Actions, 롤백, main/feature | 로컬 검증. GitHub/AWS 원격 실행 전 |
| 실무 방식 | 요구사항·PR 양식·백로그·운영/장애 절차·증거 구분 | 개인 학습용 작업 방식 구현. 여러 사람의 협업 실적 없음 |

## 이번에 직접 실행해 확인한 결과

| 검증 | 결과 | 증거 |
|---|---|---|
| Python 테스트 | **30개 통과, skip 없음** | `artifacts/local/tests.log` |
| Ruff | 통과 | `artifacts/local/lint.log` |
| Terraform fmt / validate | 통과 | `artifacts/local/terraform-fmt.log`, `terraform-validate.log` |
| Terraform mock-provider 테스트 | **3개 통과** | `artifacts/local/terraform-mock-tests.log` |
| demo | 9/10 관측, 90% 커버율, 77.78% 관측 성공률, DOWN/UP 모의 알림 각 1개 | `artifacts/local/demo.md` |
| Lambda zip | SDK 포함 빌드 완료 | `artifacts/local/package.log` |
| YAML 구문 | workflow 2개·Dependabot 1개 파싱 성공 | 로컬 Python YAML 파서 실행 |
| GitHub Actions 참조 | 공식 원격 tag의 commit 확인 후 SHA 고정 | workflow 파일 |

전체 결과 기록: `artifacts/local/verification.json`. 재검증: `.\.venv\Scripts\python scripts/verify.py` (개발 의존성·Terraform init·패키지 의존성 staging 필요).

Lambda zip SHA256:

```text
6cf35112694ad0aac69252ce80a1acc847eb5f05917fb136ccaf8838c8f1c200
```

## 테스트가 확인한 실패 상황

- 일시 실패·지속 실패·복구, 감시 공백, 서로 다른 대상의 상태 분리.
- 중복·오래된 이벤트, 동시 갱신 충돌, 알림 실패 후 보존과 재시도.
- 전송 후 중단 시 같은 ID 재전송 가능성. exactly-once로 과장하지 않음.
- 내부/metadata/혼합 DNS 접근 거부, 검증 IP 고정·SNI, IPv4 우선, URL 제한.
- DNS·TLS·연결·HTTP·timeout 분류, 리디렉션 미추적, 고객 본문 미저장.
- 데이터가 없으면 성공률을 계산하지 않음, 예정·실제 확인 시각 분리.
- DynamoDB 트랜잭션·조회 페이지 처리·SNS 어댑터를 Moto로 모의 검증.
- 배포 후보 smoke 실패 시 alias 유지, 승격 후 실패 시 이전 alias 복원, artifact hash 고정.
- AWS 모의 plan에서 작은 기본 용량·비활성화 기본값·대상 수 제한·OIDC 와일드카드 금지.

## 아직 확인하지 않은 것

- 실제 AWS 계정·플랜·무료 잔액·청구액·서비스 quota.
- 실제 인터넷 HTTPS 대상에 대한 이 프로그램의 종단간 점검. 네트워크 테스트는 mock 기반이다.
- AWS IAM 실제 동작, 리전 리소스 생성, DNS/TLS 실제 Lambda 연결, CloudWatch 경보 발생, SNS 수신함 도착.
- GitHub 원격 저장소·PR·브랜치 보호·CI 실행·OIDC·승인 후 자동 배포.
- 7일 지속 운영, 장애 탐지/복구 소요시간 실측, 예산 알림, DB 백업·복원.
- 고객 동의·파일럿·지불 의사·매출.
- 사용자가 직접 수행한 학습·운영 기록.

현재 제공물은 **운영 지원 CLI MVP와 검증 가능한 인프라/자동화 정의**다. 회원가입·결제·다중 고객 웹 콘솔이 있는 상용 SaaS 완료본이 아니다.

## 다음 검증 순서

1. 사용자가 로컬 demo를 실행하고 상태 흐름을 설명한다.
2. 정확한 AWS 계정의 무료 사용 가능량을 읽기 전용으로 확인한다.
3. 허가된 사이트 1개·수신자·비용·plan을 검토하여 AWS 파일럿을 진행한다.
4. 실제 관측·장애·복구·감시 중단·롤백 근거를 추가한다.
5. 익명화한 본인 실습 기록으로 지원서 설명을 갱신한다.
