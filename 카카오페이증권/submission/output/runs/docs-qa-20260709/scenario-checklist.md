# MTS Stability Guard Scenario Checklist

## [사실]
- 분석 사건: 5건
- 연도별 집계 기준: 금감원 전자금융사고보고(RFARS) 제출 기준 MTS 전산장애 건수
- 출처: 다음 단독·서울경제TV(2026.04)
- 2023-07-04: None (overseas_latency) https://www.yna.co.kr/view/AKR20230704027600002
- 2025-10-07: None (internal_system) https://imnews.imbc.com/news/2025/econo/article/6763918_36737.html
- 2025-10-08: None (external_broker_dependency) https://www.seoul.co.kr/news/economy/2025/10/10/20251010016002
- 2025-10-09: None (internal_system) https://imnews.imbc.com/news/2025/econo/article/6763918_36737.html
- 2025-10-10: None (us_market_open_peak) https://v.daum.net/v/20251027071622348

## [해석]
- internal_system: 내부 시스템 장애로 주문 지연 관측 2건
  - 핵심 주문 경로 회귀 테스트 스위트(주문 생성·정정·취소) 릴리즈 게이트화
  - 배포 전 스모크 테스트 + 무중단 배포·자동 롤백
  - 주문 지연 SLA 모니터링 및 임계치 알람
- overseas_latency: 해외주식 서비스 지연 관측 1건
  - 네트워크 지연 주입 테스트(latency injection)로 지연 상황 재현
  - 지연 임계 초과 시 사용자 알림·보상 트리거 자동화
  - 구간별(앱→서버→브로커) 분산 트레이싱으로 지연 원인 격리
- external_broker_dependency: 외부 브로커/현지 중개사 장애 관측 1건
  - 브로커 API 장애주입(chaos): 타임아웃·5xx·지연을 주입해 체결 경로 검증
  - 서킷브레이커·타임아웃·재시도(지수 백오프) 및 대체 체결 경로 폴백
  - 브로커 상태 헬스체크 프로브 + 장애 시 자동 사용자 공지/상태페이지
- us_market_open_peak: 미국 정규장 개장 직후 트래픽 폭주 관측 1건
  - 개장 시각(한국시간) 스파이크 부하 테스트: 평시 대비 N배 동시접속 재현
  - 오토스케일링/커넥션 풀 한계 검증 및 대기열(큐잉) 폴백 도입
  - 개장 T-5분 예열(워밍업) 및 캐시 프리페치

## [사실] Chaos before/after
- external_broker_dependency: before crashed=10, after crashed=0, basis=2025-10-08 드라이브웰스 장애로 미국주식 체결 불가 (MBC/서울신문 2025.10)
- overseas_latency/transient: before crashed=6, after crashed=0, basis=해외주식 접속 지연·일시 장애 반복 (연합뉴스 2023.07 등)
- us_market_open_peak: before crashed=12, after crashed=0, basis=2025-10-10 개장 직후 앱 접속 불능 (다음 2025.10)

## [학습]
No prior matching lessons.
