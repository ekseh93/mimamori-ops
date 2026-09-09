# 설계와 비용

## 요구사항과 설계 결정

| 요구사항 | 선택 | 이유·포기한 점 |
|---|---|---|
| 작은 규모, 사용량 최소화 | Scheduler → Python Lambda | EC2 상시 가동·OS 패치 부담을 줄임. Linux 운영을 실제로 했다는 근거는 별도 실습 필요 |
| 같은 로직을 무료 로컬에서 학습 | SQLite와 DynamoDB 저장 어댑터 | 네트워크/과금 없이 상태 전이를 설명. SQLite 검증이 AWS 가용성을 증명하지는 않음 |
| 월 무료 용량 활용 | DynamoDB Standard, provisioned 5 RCU/5 WCU | on-demand 요청 비용 무료를 가정하지 않음. 순간 동시 요청은 SDK 재시도·스로틀 모니터링 필요 |
| 변경 증거와 충돌 방지 | Terraform, 조건부 트랜잭션, PR/CI | 자동화된 변경 이력을 남김. 실제 타인 리뷰는 수행 후 기록 |
| 감시 자체가 멈췄을 때 감지 | 대상별 완료 로그 → 지표 → CloudWatch alarm | Lambda Errors만으로는 스케줄 중단을 알 수 없어 별도 heartbeat 필요 |
| 적은 운영 부담 | SNS 알림, 일본어 CLI 보고서 | 공개 사용자 API와 다중 고객 인증은 초기 범위에서 제외 |
| 비용·복잡도 제한 | VPC/NAT Gateway/ALB/EKS/RDS/고정 공인 IPv4 없이 시작 | 서비스 요구에 불필요한 상시 자원을 추가하지 않음. SAA의 네트워크/관계형 DB 범위는 별도 학습 |

## 데이터와 재시도

- `pk=target_id`, `sk=STATE`: 상태, 마지막 예정 관측 슬롯, 연속 성공/실패, 미전송 알림. 상태는 TTL 없음.
- `pk=target_id`, `sk=O#epoch`: 관측값. 5분 UTC 슬롯, 실제 관측 시작 시각, 오류 종류, 상태 코드, 지연, TLS 잔여일. 관측 TTL 40일.
- 슬롯 1개당 대상별 1개 관측만 저장. 이전/중복 슬롯은 재저장하지 않는다.
- 상태 갱신과 관측 저장은 DynamoDB 트랜잭션으로 함께 성공하거나 함께 실패한다. 읽은 상태와 현재 상태가 다르면 충돌로 처리한다.
- SNS publish 전 상태에 알림을 저장, 성공 후 조건부 해제. publish 성공 직후 프로세스가 죽으면 같은 ID의 알림이 다시 도착할 수 있는 **at-least-once** 방식이다.
- 미전송 알림이 계속 실패하면 해당 대상의 다음 점검도 지연될 수 있다. Errors·완료 누락 경보로 드러내며, 독립 outbox worker는 향후 확장 후보다.
- Scheduler 전송 실패와 Lambda 실행 실패는 별개다. 양쪽 재시도는 각각 최대 2회, 최대 이벤트 수명 15분, 실패 이벤트는 SQS에 7일 보관.
- 오래된 이벤트를 지금 다시 점검해 과거의 실제 상태처럼 기록하지 않는다. 수명 밖 이벤트는 실패 처리하고, 보고서에 예정 슬롯과 실제 확인 시각을 분리한다.
- DynamoDB TTL 삭제는 즉시가 아니다. 보고서가 조회 범위를 직접 제한하며 TTL을 정확한 삭제시각 보장으로 설명하지 않는다.

## 점검의 한계

- 공개 HTTPS 443, GET 응답 헤더의 2xx 성공만 판정. 리디렉션을 따라가지 않으므로 최종 URL을 설정해야 한다.
- 모든 DNS 결과가 공개 unicast IP여야 한다. 검증한 IP에 연결하고 원래 호스트명으로 TLS/SNI를 검증한다. IPv4를 우선한다.
- 소켓 제한 5초는 DNS+연결+TLS+응답 전체의 엄밀한 총 5초 보장이 아니다. Lambda 총 실행 제한은 60초다.
- 본문 내용, 로그인, 결제, 예약 완료까지 확인하지 않는다. TLS 잔여일은 기록하지만 만료 임박 예고 알림은 아직 없다.
- 단일 리전·단일 관측 지점. IPv6 전용 사이트의 실제 Lambda 연결, WAF 차단, 봇 차단, DNS 지연은 AWS 파일럿에서 확인해야 한다.
- 5분 간격 2회 실패라서 지속 장애 감지는 보통 약 5~10분+실행/알림 지연. 실측 SLO 달성이 아니다.
- 2회 성공 시 복구 판정. 관측 누락이 있으면 연속 판정 횟수를 다시 센다.
- 사용자 관점의 전체 가용성이 아닌 **관측 성공률**. 미관측을 정상으로 채우지 않는다.

## 30일·5개 대상·5분 주기 사용량 모델

계산 명령: `python -m mimamori estimate --targets 5 --interval 5`

| 항목 | 설계 또는 추정 | 공식 무료 기준·주의 |
|---|---|---|
| Scheduler | 43,200회/월 | 월 1,400만회. 타 리전 사용 등 합산 조건 확인 |
| Lambda | 43,200회, 256MB, 평균 2초 가정 → 21,600 GB-s | 월 100만 요청·400,000 GB-s. 평균 2초는 아직 AWS에서 측정하지 않은 가정 |
| 최악 실행시간 예시 | 모두 60초 실행하면 648,000 GB-s, 재시도 제외 | 이 경우 Lambda 컴퓨팅 무료량 초과. '항상 0원'이라고 표현할 수 없음 |
| DynamoDB | 테이블 1개, 5 RCU/5 WCU, 월 43,200 표본 | Standard provisioned 무료 25 RCU/25 WCU·25GB 조건 확인. 트랜잭션은 일반 쓰기보다 용량 소모가 큼 |
| 데이터 보관 | 표본 1KB 가정, 40일 약 57,600개 ≈ 56MiB + 오버헤드 | 상태·저장 오버헤드·TTL 지연·백업은 별도 |
| CloudWatch | custom metric 최대 5개, 표준 alarm 최대 7개, dashboard 1개, logs 7일 | 무료 metric 10개·표준 alarm metric 10개·dashboard 3개 조건 확인. Logs 5GB 조건과 유료 조회 API 주의 |
| SNS / SQS | 상태 전환·실패 때 사용 | 플래핑·전송 재시도·수신자 수 증가 시 요청/전송 비용 증가. SMS 사용 안 함 |
| GitHub Actions | CI와 승인된 배포 | 저장소 공개/비공개·계정 플랜에 따른 분·스토리지·artifact 비용 확인. AWS 무료량과 별개 |

공식 기준은 [Lambda](https://aws.amazon.com/lambda/pricing/), [DynamoDB](https://aws.amazon.com/dynamodb/pricing/), [Scheduler](https://aws.amazon.com/eventbridge/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [SNS](https://aws.amazon.com/sns/pricing/), [SQS](https://aws.amazon.com/sqs/pricing/)의 **2026-09-09 열람 자료**를 참고. 세금·환율까지 포함한 비용 견적서는 아니다. 각 무료 혜택은 계정/청구 단위의 다른 사용량과 공유될 수 있다.

## 2025년 이후 AWS 무료 플랜 구분

[AWS 공식 FAQ](https://aws.amazon.com/free/free-tier-faqs/)에 따르면 신규 무료 플랜은 최대 6개월 또는 크레딧 소진 중 먼저 도달하는 시점에 끝난다. 기본 100달러와 활동에 따른 최대 추가 100달러는 자격 조건이 있다. 기존 계정의 무료 조건은 별도다. 만료 후 계속 운영하려면 플랜·보관 정책을 확인해야 한다.

따라서 목표는 '로컬 실습 0원 + AWS 무료 이용 범위 내 소규모 파일럿'이다. 장기 유료 서비스 운영에서 무조건 0원을 약속하지 않는다. 계정의 실제 가입일·플랜·크레딧·타 프로젝트 사용량은 아직 조회하지 않았다.

## 배포 전 비용 조치

1. 정확한 AWS 계정/프로파일·Tokyo 리전·무료량 잔액 확인.
2. 계정 전체 월 $1 예산 알림(또는 사용자가 정한 한도), 무료량 알림 설정. **알림은 과금 차단기가 아니다.**
3. 1개 대상부터 시작하여 일일 요청수·평균/최대 Duration·DynamoDB 스로틀·로그량 확인.
4. 문제 시 먼저 Scheduler 비활성화. 로그/테이블 등 잔존 자원 비용을 따로 확인.
5. 사용 종료 시 보고서/필요 증거를 로컬로 보존하고 정확한 Terraform 상태를 기준으로 삭제 계획 검토.

## 접근과 공개 범위

런타임은 해당 테이블의 Get/Put/Update, 해당 SNS publish, 해당 로그 그룹 stream/write, 해당 DLQ send만 가진다. 보고서 조회 권한은 운영자의 별도 AWS 역할에 `dynamodb:Query`를 해당 테이블로 제한하여 부여한다. 실행 역할에 불필요한 Scan·관리자 권한을 넣지 않는다.

Lambda URL/API Gateway 공개 엔드포인트가 없다. GitHub OIDC 배포 역할은 한 함수의 코드·버전·alias·검증 호출로 제한한다. Terraform 인프라 변경은 이 역할로 수행하지 않는다.

Terraform state는 지금 로컬이다. **동시 인프라 협업 전** 버전 관리·암호화·public access block·잠금을 갖춘 S3 backend로 옮기고 백엔드 저장 비용을 확인한다. 현재 원격 상태 잠금이나 GitHub 보호 규칙이 설정되었다고 주장하지 않는다.
