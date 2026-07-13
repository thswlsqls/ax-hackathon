#!/usr/bin/env python3
"""회귀 테스트 — before(장애 재현) → after(방어 통과)를 실행 가능한 게이트로 고정한다.

# noqa: SIZE_OK - cohesive stdlib regression matrix for resilience behavior.

각 테스트는 두 부분을 검증한다:
  1) [재현] 무방비(naive) 경로가 공개 장애 조건에서 실제로 실패함을 문서화한다.
  2) [완화] 같은 조건에서 방어(guarded) 경로가 우아하게 강등/회복함을 보장한다.
이 스위트가 통과하면 "장애 재현 → 방어코드 → 재테스트 통과"가 입증된다.

실행: python3 -m unittest discover -s tests   (또는 python3 tests/test_resilience.py)
"""
import os
import sys
import unittest
from collections.abc import Mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo.broker_mock import MockBroker, BrokerError, BrokerTimeout, BrokerOverloaded
from demo.trading_backend import NaiveOrderService, GuardedOrderService
from demo.resilience import (
    AdmissionController, AdmissionError, CircuitBreaker, CircuitOpenError,
    HealthCheckError, HealthProbe, call_with_retry,
)
from io_contract import SubmissionIOTestCase


def _order(i=0):
    return {"id": f"ord-{i}", "symbol": "AAPL", "qty": 1}


def _raiser(exc):
    """호출 시 항상 exc를 던지는 함수를 만든다(테스트 가독성용)."""
    def _fn(*args, **kwargs):
        raise exc
    return _fn


class FakeTime:
    """결정론적 clock/sleep. 실제 대기 없이 논리 시간만 흘린다."""

    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class CircuitBreakerTest(SubmissionIOTestCase):
    def test_opens_after_threshold_then_blocks(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=5.0, clock=lambda: 0.0)

        def boom():
            raise BrokerError("5xx")

        for _ in range(3):
            with self.assertRaises(BrokerError):
                cb.call(boom)
        self.assertEqual(cb.state, CircuitBreaker.OPEN)
        # 개방 후에는 브로커를 호출하지 않고 즉시 빠른 실패.
        with self.assertRaises(CircuitOpenError):
            cb.call(boom)

    def test_half_open_recovers_on_success(self):
        ft = FakeTime()
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1.0, clock=ft.clock)
        for _ in range(2):
            with self.assertRaises(BrokerError):
                cb.call(lambda: (_ for _ in ()).throw(BrokerError()))
        self.assertEqual(cb.state, CircuitBreaker.OPEN)
        ft.now += 1.5  # reset_timeout 경과 → HALF_OPEN 탐침 허용
        self.assertEqual(cb.call(lambda: "ok"), "ok")
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)

    def test_half_open_reopens_on_probe_failure(self):
        # HALF_OPEN 탐침이 실패하면 즉시 다시 OPEN 으로 돌아가야 한다.
        ft = FakeTime()
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1.0, clock=ft.clock)
        for _ in range(2):
            with self.assertRaises(BrokerError):
                cb.call(_raiser(BrokerError()))
        self.assertEqual(cb.state, CircuitBreaker.OPEN)
        ft.now += 1.5  # 탐침 허용 시점
        with self.assertRaises(BrokerError):
            cb.call(_raiser(BrokerError()))  # 탐침 실패
        self.assertEqual(cb.state, CircuitBreaker.OPEN)


class RetryTest(SubmissionIOTestCase):
    def test_absorbs_transient_then_succeeds(self):
        ft = FakeTime()
        seq = iter(["timeout", "timeout", "ok"])

        def flaky():
            if next(seq) != "ok":
                raise BrokerTimeout()
            return "filled"

        result = call_with_retry(flaky, retries=2, retryable=(BrokerTimeout,), sleep=ft.sleep)
        self.assertEqual(result, "filled")

    def test_gives_up_after_exhausting_retries(self):
        ft = FakeTime()
        with self.assertRaises(BrokerError):
            call_with_retry(lambda: (_ for _ in ()).throw(BrokerError()),
                            retries=2, retryable=(BrokerError,), sleep=ft.sleep)

    def test_does_not_retry_non_retryable(self):
        # retryable 목록에 없는 예외는 재시도하지 않고 즉시 전파해야 한다.
        ft = FakeTime()
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise ValueError

        with self.assertRaises(ValueError):
            call_with_retry(fn, retries=3, retryable=(BrokerTimeout,), sleep=ft.sleep)
        self.assertEqual(calls["n"], 1)  # 단 1회만 호출(재시도 없음)

    def test_zero_retry_calls_once_and_raises(self):
        ft = FakeTime()
        calls = {"n": 0}

        def fn():
            calls["n"] += 1
            raise BrokerTimeout("still down")

        with self.assertRaises(BrokerTimeout):
            call_with_retry(fn, retries=0, retryable=(BrokerTimeout,), sleep=ft.sleep)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(ft.now, 0.0)


class HealthProbeTest(SubmissionIOTestCase):
    def test_unhealthy_when_check_raises(self):
        # 헬스체크 자체가 예외를 던지면 비정상으로 간주해야 한다(예외 누출 금지).
        probe = HealthProbe(_raiser(HealthCheckError("probe boom")))
        self.assertFalse(probe.check())
        self.assertFalse(probe.last_healthy)

    def test_reflects_check_result(self):
        state = {"ok": True}
        probe = HealthProbe(lambda: state["ok"])
        self.assertTrue(probe.check())
        state["ok"] = False
        self.assertFalse(probe.check())


class AdmissionControllerTest(SubmissionIOTestCase):
    def test_admits_up_to_capacity_then_rejects(self):
        ac = AdmissionController(capacity=2)
        self.assertTrue(ac.try_admit())
        self.assertTrue(ac.try_admit())
        self.assertFalse(ac.try_admit())  # 초과분 거절
        self.assertEqual(ac.rejected, 1)

    def test_reset_readmits(self):
        ac = AdmissionController(capacity=1)
        self.assertTrue(ac.try_admit())
        self.assertFalse(ac.try_admit())
        ac.reset()  # 다음 폭주 윈도
        self.assertTrue(ac.try_admit())


class GuardedServiceRecoveryTest(SubmissionIOTestCase):
    def test_recovers_transient_via_retry(self):
        # 서비스 레벨에서도 일시 장애(2회 실패 후 회복)를 재시도로 체결까지 끌고 가야 한다.
        ft = FakeTime()
        broker = MockBroker().script(["timeout", "timeout", "ok"])
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=1.0, clock=ft.clock)
        svc = GuardedOrderService(broker, breaker=cb, sleep=ft.sleep)
        res = svc.place_order(_order())
        self.assertEqual(res["status"], "filled")
        self.assertEqual(len(svc.deferred_queue), 0)

    def test_admission_failure_is_deferred_without_broker_call(self):
        class FailingAdmission:
            def __init__(self, failure=None):
                self.failure = RuntimeError() if failure is None else failure

            def try_admit(self):
                raise self.failure

        broker = MockBroker()
        operational_service = GuardedOrderService(
            broker, admission=FailingAdmission(AdmissionError("busy"))
        )
        result = operational_service.place_order(_order())
        self.assertEqual(result["status"], "deferred")
        self.assertTrue(result["reason"].startswith("admission-fault: AdmissionError"))

        svc = GuardedOrderService(broker, admission=FailingAdmission())

        with self.assertRaises(RuntimeError):
            svc.place_order(_order())
        self.assertEqual(svc.deferred_queue, [])
        self.assertEqual(broker.calls, 0)

        process_exit_service = GuardedOrderService(
            broker, admission=FailingAdmission(GeneratorExit("admission exit"))
        )
        with self.assertRaises(GeneratorExit):
            process_exit_service.place_order(_order())
        self.assertEqual(process_exit_service.deferred_queue, [])
        self.assertEqual(broker.calls, 0)

    def test_hostile_mapping_is_rejected_before_state_mutation(self):
        class HostileOrder(Mapping):
            def __getitem__(self, key):
                raise KeyError(key)

            def __iter__(self):
                return iter(())

            def __len__(self):
                return 0

            def get(self, key, default=None):
                raise RuntimeError

        broker = MockBroker()
        admission = AdmissionController(1)
        breaker = CircuitBreaker(failure_threshold=1)
        svc = GuardedOrderService(broker, breaker=breaker, admission=admission)

        with self.assertRaises(RuntimeError):
            svc.place_order(HostileOrder())
        self.assertEqual(svc.deferred_queue, [])
        self.assertEqual((admission.admitted, admission.rejected), (0, 0))
        self.assertEqual(broker.calls, 0)
        self.assertEqual((breaker.state, breaker.failures), (CircuitBreaker.CLOSED, 0))

        class ProcessExitOrder(HostileOrder):
            def get(self, key, default=None):
                raise GeneratorExit("mapping exit")

        with self.assertRaises(GeneratorExit):
            svc.place_order(ProcessExitOrder())
        self.assertEqual(svc.deferred_queue, [])
        self.assertEqual((admission.admitted, admission.rejected), (0, 0))
        self.assertEqual(broker.calls, 0)
        self.assertEqual((breaker.state, breaker.failures), (CircuitBreaker.CLOSED, 0))

    def test_backend_exception_is_deferred_but_process_control_reraises(self):
        class BackendAbort(Exception):
            pass

        class RaisingBroker(MockBroker):
            def __init__(self, failure):
                super().__init__()
                self.failure = failure

            def place_order(self, order):
                self.calls += 1
                raise self.failure

        svc = GuardedOrderService(RaisingBroker(BackendAbort("abort")), retries=0)
        with self.assertRaises(BackendAbort):
            svc.place_order(_order())
        self.assertEqual(svc.deferred_queue, [])
        self.assertEqual(svc.breaker.failures, 0)

        for failure in (KeyboardInterrupt(), SystemExit(), GeneratorExit()):
            with self.assertRaises(type(failure)):
                GuardedOrderService(RaisingBroker(failure), retries=0).place_order(_order())

    def test_health_exception_is_deferred_but_process_control_reraises(self):
        class HealthAbort(Exception):
            pass

        class RaisingHealthBroker(MockBroker):
            def __init__(self, failure):
                super().__init__()
                self.failure = failure

            def healthy(self):
                raise self.failure

        breaker = CircuitBreaker(failure_threshold=1)
        broker = MockBroker()
        svc = GuardedOrderService(broker, breaker=breaker)
        svc.health.check = _raiser(HealthCheckError("health unavailable"))
        result = svc.place_order(_order())
        self.assertEqual(result["status"], "deferred")
        self.assertTrue(result["reason"].startswith("health-fault: HealthCheckError"))

        programming_service = GuardedOrderService(broker, breaker=breaker)
        programming_service.health.check = _raiser(HealthAbort("health abort"))
        with self.assertRaises(HealthAbort):
            programming_service.place_order(_order())
        self.assertEqual(programming_service.deferred_queue, [])
        self.assertEqual(broker.calls, 0)
        self.assertEqual((breaker.state, breaker.failures), (CircuitBreaker.CLOSED, 0))

        for failure in (KeyboardInterrupt(), SystemExit(), GeneratorExit()):
            breaker = CircuitBreaker(failure_threshold=1)
            with self.assertRaises(type(failure)):
                GuardedOrderService(
                    RaisingHealthBroker(failure), breaker=breaker
                ).place_order(_order())
            self.assertEqual((breaker.state, breaker.failures), (CircuitBreaker.CLOSED, 0))


class ExternalBrokerOutageTest(SubmissionIOTestCase):
    """external_broker_dependency (드라이브웰스 체결 불가) 재현/완화."""

    def test_naive_leaks_broker_failure(self):
        # [재현] 무방비 경로는 브로커 예외를 그대로 사용자에게 누출한다.
        svc = NaiveOrderService(MockBroker().set_mode("error"))
        with self.assertRaises(BrokerError):
            svc.place_order(_order())

    def test_guarded_degrades_gracefully(self):
        # [완화] 방어 경로는 예외 대신 명시적 'deferred'로 강등한다.
        ft = FakeTime()
        broker = MockBroker().set_mode("error").report_health(True)
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=1.0, clock=ft.clock)
        svc = GuardedOrderService(broker, breaker=cb, sleep=ft.sleep)
        results = [svc.place_order(_order(i)) for i in range(10)]
        self.assertTrue(all(r["status"] == "deferred" for r in results))
        self.assertEqual(len(svc.deferred_queue), 10)  # 유실 없이 재처리 큐에 보존
        # 서킷 개방으로 브로커 호출이 재시도-only 상한(10주문×3시도=30)보다 작아야 한다.
        self.assertLess(broker.calls, 30)

    def test_guarded_defers_when_health_gate_fails(self):
        # 헬스가 비정상을 알리면 브로커를 두드리지 않고 곧바로 보류.
        ft = FakeTime()
        broker = MockBroker().set_mode("error")  # healthy() == False
        svc = GuardedOrderService(broker, sleep=ft.sleep)
        res = svc.place_order(_order())
        self.assertEqual(res["status"], "deferred")
        self.assertEqual(broker.calls, 0)


class MarketOpenSpikeTest(SubmissionIOTestCase):
    """us_market_open_peak (개장 직후 폭주) 재현/완화."""

    def test_naive_loses_orders_on_saturation(self):
        # [재현] 수용량을 넘긴 주문이 브로커 포화로 유실된다.
        broker = MockBroker().saturate(8)
        svc = NaiveOrderService(broker)
        crashed = 0
        for i in range(20):
            try:
                svc.place_order(_order(i))
            except BrokerOverloaded:
                crashed += 1
        self.assertEqual(crashed, 12)  # 20 - 8

    def test_guarded_sheds_load_without_loss(self):
        # [완화] 백프레셔로 초과분을 유실 대신 '보류'로 강등한다.
        ft = FakeTime()
        broker = MockBroker().saturate(8)
        admission = AdmissionController(8)
        svc = GuardedOrderService(broker, admission=admission, sleep=ft.sleep)
        results = [svc.place_order(_order(i)) for i in range(20)]
        filled = [r for r in results if r["status"] == "filled"]
        deferred = [r for r in results if r["status"] == "deferred"]
        self.assertEqual(len(filled), 8)
        self.assertEqual(len(deferred), 12)
        # 어떤 주문도 예외로 누출되지 않는다.
        self.assertEqual(len(filled) + len(deferred), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
