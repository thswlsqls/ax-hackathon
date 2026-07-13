#!/usr/bin/env python3
"""방어(resilience) 프리미티브 — 반복 전산장애를 완화하기 위한 재사용 부품.

이 모듈은 특정 회사 코드가 아니라, 공개 장애 패턴(외부 브로커 의존·개장 피크·해외
지연)을 겨냥한 **일반적 방어 설계**의 최소 구현이다. 표준 라이브러리만 사용하며,
시간에 의존하는 로직(서킷 리셋 타임아웃·백오프)은 테스트가 시간을 통제할 수 있도록
`clock`/`sleep`을 주입받는다.

사실/해석 구분: 여기 담긴 설계(서킷브레이커·재시도·폴백·백프레셔)는 이 스킬의
'해석(권고)'이다. 어떤 장애가 실제로 있었는지는 공개 이력(data/incidents.sample.json)이
'사실'로 근거를 제공한다.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final, Literal, TypeVar

T = TypeVar("T")
CircuitState = Literal["closed", "open", "half_open"]


class OperationalError(Exception):
    """Base class for expected dependency failures."""


class AdmissionError(OperationalError):
    """Admission control could not evaluate current capacity."""


class HealthCheckError(OperationalError):
    """A dependency health check failed operationally."""


class ResilienceConfigError(ValueError):
    """A resilience primitive received an invalid configuration."""


class CircuitOpenError(Exception):
    """서킷이 열려 있어 호출을 즉시 차단했음을 알린다(빠른 실패)."""


class CircuitBreaker:
    """연쇄 실패를 끊는 서킷브레이커.

    상태 전이: CLOSED → (연속 실패 threshold 도달) → OPEN
              OPEN → (reset_timeout 경과) → HALF_OPEN
              HALF_OPEN → (성공) → CLOSED / (실패) → OPEN

    외부 브로커가 죽었을 때 매 요청을 그대로 흘려보내 스레드·커넥션을 소진시키는 대신,
    OPEN 상태에서 즉시 CircuitOpenError로 빠르게 실패시켜 상위 폴백이 동작하게 한다.
    """

    CLOSED: Final[CircuitState] = "closed"
    OPEN: Final[CircuitState] = "open"
    HALF_OPEN: Final[CircuitState] = "half_open"
    failure_threshold: int
    reset_timeout: float
    _clock: Callable[[], float]
    failure_exceptions: tuple[type[Exception], ...]
    failures: int

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        failure_exceptions: tuple[type[Exception], ...] = (OperationalError,),
    ) -> None:
        if failure_threshold < 1:
            raise ResilienceConfigError("failure_threshold must be at least 1")
        if reset_timeout < 0:
            raise ResilienceConfigError("reset_timeout must be non-negative")
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self.failure_exceptions = failure_exceptions
        self.state: CircuitState = self.CLOSED
        self.failures = 0
        self._opened_at: float | None = None

    def _enter_open(self) -> None:
        self.state = self.OPEN
        self._opened_at = self._clock()

    def allow_request(self) -> bool:
        """호출 허용 여부를 판정하고 필요한 상태 전이를 수행한다."""
        if self.state == self.OPEN:
            opened_at = self._opened_at
            if opened_at is not None and self._clock() - opened_at >= self.reset_timeout:
                # 탐침을 한 번 허용한다.
                self.state = self.HALF_OPEN
                return True
            return False
        if self.state == self.HALF_OPEN:
            # 탐침이 진행 중인 동안 추가 호출은 차단한다(단일 탐침 유지).
            return False
        return True

    def on_success(self) -> None:
        self.failures = 0
        self.state = self.CLOSED
        self._opened_at = None

    def on_failure(self) -> None:
        self.failures += 1
        if self.state == self.HALF_OPEN or self.failures >= self.failure_threshold:
            self._enter_open()

    def call(self, fn: Callable[[], T]) -> T:
        """fn을 서킷 보호 아래 호출한다. 차단 시 CircuitOpenError를 던진다."""
        if not self.allow_request():
            raise CircuitOpenError("circuit is open")
        try:
            result = fn()
        except self.failure_exceptions:
            self.on_failure()
            raise
        self.on_success()
        return result


def call_with_retry(
    fn: Callable[[], T],
    retries: int = 2,
    base_delay: float = 0.02,
    max_delay: float = 0.2,
    retryable: tuple[type[Exception], ...] = (OperationalError,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """일시적(transient) 실패를 지수 백오프로 재시도한다.

    총 시도 횟수 = retries + 1. 마지막 시도까지 실패하면 마지막 예외를 그대로 올린다.
    개장 직후 순간적 5xx·타임아웃처럼 곧 회복되는 장애를 흡수하기 위한 것이며,
    영구 장애에서는 서킷브레이커가 재시도 폭주를 막는다.
    """
    if retries < 0:
        raise ResilienceConfigError("retries must be non-negative")
    attempt = 0
    while True:
        try:
            return fn()
        except retryable:
            if attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (2.0 ** attempt))
            sleep(delay)
            attempt += 1


class HealthProbe:
    """외부 의존성 헬스체크 프로브. 결과를 캐시해 게이트로 쓴다."""

    _check_fn: Callable[[], bool]
    last_healthy: bool

    def __init__(self, check_fn: Callable[[], bool]) -> None:
        self._check_fn = check_fn
        self.last_healthy = True

    def check(self) -> bool:
        try:
            self.last_healthy = bool(self._check_fn())
        except HealthCheckError:
            self.last_healthy = False
        return self.last_healthy


class AdmissionController:
    """개장 피크 폭주를 막는 백프레셔(load shedding).

    한 폭주 윈도 동안 capacity건까지만 수용하고, 초과분은 즉시 거절(빠른 실패)해
    상위에서 '보류·지연 안내'로 우아하게 강등하도록 한다. 무한 버퍼 대신 유계(bounded)
    수용으로 다운스트림 자원을 보호하는 것이 핵심이다. 다음 윈도 전에 reset()한다.
    """

    capacity: int
    admitted: int
    rejected: int

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ResilienceConfigError("capacity must be non-negative")
        self.capacity = capacity
        self.admitted = 0
        self.rejected = 0

    def try_admit(self) -> bool:
        if self.admitted >= self.capacity:
            self.rejected += 1
            return False
        self.admitted += 1
        return True

    def reset(self) -> None:
        self.admitted = 0
        self.rejected = 0
