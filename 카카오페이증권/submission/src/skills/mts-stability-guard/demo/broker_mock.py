#!/usr/bin/env python3
"""모의 외부 체결 브로커 — 공개 장애 패턴을 실제 네트워크 없이 재현한다.

카카오페이증권 해외주식 체결은 미국 현지 중개사(공개 보도상 드라이브웰스)에 의존하며,
그 외부 브로커 장애가 반복 전산장애의 한 축이었다(2025-10-08 체결 불가 — MBC/서울신문).
이 모의 브로커는 그 '외부 의존' 지점을 코드로 세워, 장애를 주입해 방어코드를 검증한다.

주입 가능한 장애:
- error   : 5xx류 오류(BrokerError)
- timeout : 응답 없음(BrokerTimeout)
- slow    : 지연 후 정상 체결(해외 지연 재현)
- healthy : 정상 체결
또한 `accept_budget`으로 개장 피크 '포화'를 재현한다(예산 소진 시 BrokerOverloaded).
`script([...])`로 "처음 K회 실패 후 회복" 같은 시퀀스를 재현할 수 있다.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from typing import Literal, TypedDict, Union

from .resilience import OperationalError

Behavior = Literal["healthy", "error", "timeout", "slow", "ok"]
OrderValue = Union[str, int, None]
Order = Mapping[str, OrderValue]
OrderInput = Union[Order, str, int, float, bool, None]


class Fill(TypedDict):
    broker: str
    order_id: OrderValue
    symbol: OrderValue
    qty: OrderValue
    status: Literal["filled"]


class BrokerError(OperationalError):
    """외부 브로커 5xx류 오류."""


class BrokerTimeout(OperationalError):
    """외부 브로커 응답 타임아웃."""


class BrokerOverloaded(OperationalError):
    """개장 피크 등으로 브로커 수용량이 포화됨."""


class BrokerInvalidOrder(TypeError):
    """The broker received an incompatible order value."""


class MockBroker:
    name: str
    slow_seconds: float
    _sleep: Callable[[float], None]
    calls: int

    def __init__(
        self,
        name: str = "drivewealth-mock",
        slow_seconds: float = 0.02,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self.mode: Behavior = "healthy"          # healthy | error | timeout | slow
        self.slow_seconds = slow_seconds
        self._sleep = sleep
        self._script: deque[Behavior] = deque()
        self.accept_budget: int | None = None
        self._report_healthy: bool | None = None
        self.calls = 0

    # --- 장애 주입 설정 -------------------------------------------------
    def set_mode(self, mode: Behavior) -> MockBroker:
        self.mode = mode
        return self

    def script(self, behaviors: Iterable[Behavior]) -> MockBroker:
        """행동 시퀀스를 지정한다(예: ["error", "error", "ok"])."""
        self._script = deque(behaviors)
        return self

    def saturate(self, budget: int) -> MockBroker:
        """개장 피크 포화 재현: budget회까지만 수용, 이후 BrokerOverloaded."""
        self.accept_budget = budget
        return self

    def report_health(self, is_healthy: bool) -> MockBroker:
        """헬스 응답을 강제한다. 예: 체결은 실패하는데 헬스는 정상이라 답하는 오탐 재현."""
        self._report_healthy = is_healthy
        return self

    # --- 헬스체크 -------------------------------------------------------
    def healthy(self) -> bool:
        """헬스 프로브용. 스크립트를 소비하지 않고 현재 상태만 본다."""
        if self._report_healthy is not None:
            return self._report_healthy
        return self.mode == "healthy" and (self.accept_budget is None or self.accept_budget > 0)

    # --- 주문 체결 ------------------------------------------------------
    def place_order(self, order: OrderInput) -> Fill:
        if not isinstance(order, Mapping):
            raise BrokerInvalidOrder(
                f"{self.name}: order must be a mapping, got {type(order).__name__}",
            )
        self.calls += 1

        if self.accept_budget is not None:
            if self.accept_budget <= 0:
                raise BrokerOverloaded(f"{self.name}: capacity exhausted")
            self.accept_budget -= 1

        behavior = self._script.popleft() if self._script else self._mode_behavior()

        if behavior == "timeout":
            raise BrokerTimeout(f"{self.name}: no response")
        if behavior == "error":
            raise BrokerError(f"{self.name}: 5xx")
        if behavior == "slow":
            self._sleep(self.slow_seconds)
        return {
            "broker": self.name,
            "order_id": order.get("id"),
            "symbol": order.get("symbol"),
            "qty": order.get("qty"),
            "status": "filled",
        }

    def _mode_behavior(self) -> Behavior:
        behaviors: dict[Behavior, Behavior] = {
            "error": "error",
            "timeout": "timeout",
            "slow": "slow",
        }
        return behaviors.get(self.mode, "ok")
