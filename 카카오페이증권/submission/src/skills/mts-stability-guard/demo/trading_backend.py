#!/usr/bin/env python3
"""주문 처리 백엔드 — 무방비(naive) vs 방어(guarded) 두 구현.

같은 모의 브로커에 같은 장애를 주입했을 때,
- NaiveOrderService: 외부 브로커 장애가 그대로 사용자에게 전파(주문 실패/예외 누출).
- GuardedOrderService: 헬스게이트→서킷브레이커→재시도→폴백으로 우아하게 강등.

'우아한 강등(graceful degradation)'이란 앱이 멈추거나 예외를 토하는 대신,
주문을 '보류(deferred)'로 명확히 안내하고 이후 재처리 큐에 넣는 것을 뜻한다.
이는 공개 사례에서 지적된 '미흡한 공지·대응'을 코드 단계에서 개선한 것이다.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal, Protocol, TypedDict, Union

from .broker_mock import (
    BrokerError,
    BrokerOverloaded,
    BrokerTimeout,
    Fill,
    Order,
    OrderInput,
    OrderValue,
)
from .resilience import (
    AdmissionError,
    CircuitBreaker,
    CircuitOpenError,
    HealthCheckError,
    HealthProbe,
    call_with_retry,
)


class Broker(Protocol):
    def healthy(self) -> bool: ...
    def place_order(self, order: Order) -> Fill: ...


class Admission(Protocol):
    def try_admit(self) -> bool: ...


class FilledResult(TypedDict):
    order_id: OrderValue
    status: Literal["filled"]
    fill: Fill


class DeferredResult(TypedDict):
    order_id: OrderValue
    status: Literal["deferred"]
    reason: str


class RejectedResult(TypedDict):
    order_id: None
    status: Literal["rejected"]
    reason: str


OrderResult = Union[FilledResult, DeferredResult, RejectedResult]

# 외부 브로커에서 올라오는, 재시도/폴백으로 다뤄야 할 장애들.
BROKER_FAULTS = (BrokerError, BrokerTimeout, BrokerOverloaded)


class NaiveOrderService:
    """보호 장치가 전혀 없는 기준선(baseline). 장애를 그대로 노출한다."""

    broker: Broker

    def __init__(self, broker: Broker) -> None:
        self.broker = broker

    def place_order(self, order: Order) -> FilledResult:
        # 외부 브로커를 직접 호출한다. 장애 시 예외가 그대로 위로 전파된다.
        fill = self.broker.place_order(order)
        return {"order_id": order.get("id"), "status": "filled", "fill": fill}


class GuardedOrderService:
    """방어 계층으로 감싼 주문 서비스.

    처리 순서: (1) admission 백프레셔 → (2) 헬스 게이트 → (3) 서킷브레이커 +
    재시도(지수 백오프) → (4) 실패 시 폴백(주문 보류 + 재처리 큐).
    어떤 경우에도 예외를 사용자에게 누출하지 않고 명시적 상태를 반환한다.
    """

    broker: Broker
    breaker: CircuitBreaker
    admission: Admission | None
    health: HealthProbe
    retries: int
    _sleep: Callable[[float], None] | None

    def __init__(
        self,
        broker: Broker,
        breaker: CircuitBreaker | None = None,
        admission: Admission | None = None,
        retries: int = 2,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.broker = broker
        self.breaker = breaker or CircuitBreaker(
            failure_threshold=3,
            reset_timeout=1.0,
            failure_exceptions=BROKER_FAULTS,
        )
        self.admission = admission
        self.health = HealthProbe(broker.healthy)
        self.retries = retries
        self._sleep = sleep
        self.deferred_queue: list[Order] = []

    def place_order(self, order: OrderInput) -> OrderResult:
        if not isinstance(order, Mapping):
            return {
                "order_id": None,
                "status": "rejected",
                "reason": "invalid-order: order must be a mapping",
            }
        order_id = order.get("id")
        # (1) 백프레셔: 폭주 윈도 수용량 초과 시 즉시 보류로 강등(자원 보호).
        try:
            if self.admission is not None and not self.admission.try_admit():
                return self._defer(
                    order, order_id, "backpressure: 개장 피크 수용량 초과 → 보류",
                )
        except AdmissionError as exc:
            return self._defer(
                order, order_id, f"admission-fault: {type(exc).__name__} → 보류",
            )
        # (2) 헬스 게이트: 이미 죽은 걸 아는 의존성은 두드리지 않는다.
        try:
            healthy = self.health.check()
        except HealthCheckError as exc:
            return self._defer(
                order, order_id, f"health-fault: {type(exc).__name__} → 보류",
            )
        if not healthy:
            return self._defer(order, order_id, "health-gate: 브로커 비정상 → 보류")
        # (3) 서킷브레이커 + 재시도로 체결 시도.
        try:
            if self._sleep is None:
                fill = self.breaker.call(
                    lambda: call_with_retry(
                        lambda: self.broker.place_order(order),
                        retries=self.retries,
                        retryable=BROKER_FAULTS,
                    ),
                )
            else:
                retry_sleep = self._sleep
                fill = self.breaker.call(
                    lambda: call_with_retry(
                        lambda: self.broker.place_order(order),
                        retries=self.retries,
                        retryable=BROKER_FAULTS,
                        sleep=retry_sleep,
                    ),
                )
            return {"order_id": order_id, "status": "filled", "fill": fill}
        except CircuitOpenError:
            # (4a) 서킷 열림: 빠른 실패 → 폴백.
            return self._defer(order, order_id, "circuit-open: 연쇄 장애 차단 → 보류")
        except BROKER_FAULTS as exc:
            # (4b) 재시도 소진: 폴백.
            return self._defer(
                order, order_id, f"broker-fault: {type(exc).__name__} → 보류",
            )

    def _defer(self, order: Order, order_id: OrderValue, reason: str) -> DeferredResult:
        self.deferred_queue.append(order)
        return {"order_id": order_id, "status": "deferred", "reason": reason}
