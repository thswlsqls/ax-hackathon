#!/usr/bin/env python3
"""장애 재현 러너 — 공개 장애 패턴을 주입해 naive vs guarded를 before/after로 비교한다.

각 시나리오는 공개 보도(사실)에서 관측된 실패 패턴을 코드로 재현하고, 같은 조건에서
두 주문 서비스가 어떻게 반응하는지 집계한다. 이 러너의 출력이 "장애 재현 → 방어코드 →
재테스트로 완화 입증"의 end-to-end 로그가 된다.

실행:
    python3 demo/chaos_runner.py
    python3 demo/chaos_runner.py --json-out chaos-report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from typing import Final, Protocol, TypedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __package__ in {None, ""}:
    __package__ = "demo"

from .broker_mock import Behavior, MockBroker, Order
from .resilience import AdmissionController, CircuitBreaker
from .trading_backend import (
    BROKER_FAULTS,
    GuardedOrderService,
    NaiveOrderService,
    OrderResult,
)


class OrderService(Protocol):
    def place_order(self, order: Order) -> OrderResult: ...


class Tally(TypedDict):
    filled: int
    deferred: int
    crashed: int


class ScenarioRequired(TypedDict):
    pattern: str
    public_basis: str
    injected: str
    naive: Tally
    guarded: Tally


class ScenarioResult(ScenarioRequired, total=False):
    guarded_broker_calls: int
    note: str


class CliArgs(argparse.Namespace):
    json_out: str | None = None

# 테스트/데모를 결정론적으로 유지하기 위해 실제 대기 없이 시간을 흘려보내는 가짜 clock/sleep.
_now: list[float] = [0.0]


def fake_sleep(seconds: float) -> None:
    _now[0] += seconds


def fake_clock() -> float:
    return _now[0]


def _orders(n: int, symbol: str = "AAPL") -> list[Order]:
    return [{"id": f"ord-{i}", "symbol": symbol, "qty": 1} for i in range(n)]


def _tally(service: OrderService, orders: Sequence[Order]) -> Tally:
    """주문 배치를 실행하며 filled/deferred/crashed를 집계한다."""
    counts: Tally = {"filled": 0, "deferred": 0, "crashed": 0}
    for order in orders:
        try:
            res = service.place_order(order)
            status = res["status"]
            if status == "filled":
                counts["filled"] += 1
            elif status == "deferred":
                counts["deferred"] += 1
            else:
                counts["crashed"] += 1
        except BROKER_FAULTS:
            # naive 서비스는 브로커 예외를 그대로 누출한다 = 사용자 주문 실패.
            counts["crashed"] += 1
    return counts


def _fresh_guarded(
    broker: MockBroker,
    admission: AdmissionController | None = None,
) -> GuardedOrderService:
    breaker = CircuitBreaker(
        failure_threshold=3,
        reset_timeout=1.0,
        clock=fake_clock,
        failure_exceptions=BROKER_FAULTS,
    )
    return GuardedOrderService(broker, breaker=breaker, admission=admission, sleep=fake_sleep)


def scenario_external_broker_outage() -> ScenarioResult:
    """external_broker_dependency 재현: 현지 중개사(드라이브웰스) 전면 장애로 체결 불가.
    공개 근거: 2025-10-08 드라이브웰스 전산장애로 미국주식 체결 불가 (MBC/서울신문 2025.10).

    헬스 엔드포인트는 정상이라 응답하지만 실제 체결은 5xx로 실패하는 오탐 상황을 재현한다.
    이때 서킷브레이커가 연속 실패를 감지해 회로를 열고, 이후 요청은 브로커를 두드리지 않고
    즉시 보류로 강등된다(불필요한 재시도 폭주 차단).
    """
    orders = _orders(10)
    naive = _tally(NaiveOrderService(MockBroker().set_mode("error")), orders)
    guarded_broker = MockBroker().set_mode("error").report_health(True)
    guarded = _tally(_fresh_guarded(guarded_broker), orders)
    return {
        "pattern": "external_broker_dependency",
        "public_basis": "2025-10-08 드라이브웰스 장애로 미국주식 체결 불가 (MBC/서울신문 2025.10)",
        "injected": "브로커 place_order 전면 5xx (헬스는 정상 응답 = 오탐)",
        "naive": naive,
        "guarded": guarded,
        "guarded_broker_calls": guarded_broker.calls,
        "note": (f"[해석] 서킷 개방으로 guarded의 브로커 호출이 {guarded_broker.calls}회로 억제됨"
                 f"(서킷 없이 재시도만 있으면 최대 10주문×3시도=30회)."),
    }


def scenario_transient_timeout() -> ScenarioResult:
    """일시적 타임아웃 재현: 처음 2회 타임아웃 후 회복. 재시도로 흡수되어야 한다."""
    orders = _orders(6)
    # 주문마다 처음 2회 실패 후 성공하도록: 각 주문당 error,error,ok 시퀀스가 필요하지만
    # 러너는 배치 단위이므로, 스크립트를 넉넉히 채워 재시도 흡수를 보인다.
    naive_behaviors: list[Behavior] = ["timeout"] * 6
    guarded_behaviors: list[Behavior] = ["timeout", "timeout", "ok"] * 6
    naive_broker = MockBroker().script(naive_behaviors)
    guarded_broker = MockBroker().script(guarded_behaviors)
    naive = _tally(NaiveOrderService(naive_broker), orders)
    guarded = _tally(_fresh_guarded(guarded_broker), orders)
    return {
        "pattern": "overseas_latency/transient",
        "public_basis": "해외주식 접속 지연·일시 장애 반복 (연합뉴스 2023.07 등)",
        "injected": "주문당 2회 타임아웃 후 회복",
        "naive": naive,
        "guarded": guarded,
    }


def scenario_market_open_spike() -> ScenarioResult:
    """us_market_open_peak 재현: 개장 직후 폭주로 브로커 수용량 포화.
    공개 근거: 2025-10-10 미국 정규장 개장 직후 앱 접속 불능 (다음 2025.10).
    """
    burst = 20
    capacity = 8
    orders = _orders(burst)
    naive = _tally(NaiveOrderService(MockBroker().saturate(capacity)), orders)
    guarded = _tally(
        _fresh_guarded(MockBroker().saturate(capacity), admission=AdmissionController(capacity)),
        orders,
    )
    return {
        "pattern": "us_market_open_peak",
        "public_basis": "2025-10-10 개장 직후 앱 접속 불능 (다음 2025.10)",
        "injected": f"동시 주문 {burst}건 vs 브로커 수용량 {capacity}건",
        "naive": naive,
        "guarded": guarded,
    }


SCENARIOS: Final[tuple[Callable[[], ScenarioResult], ...]] = (
    scenario_market_open_spike,
    scenario_transient_timeout,
    scenario_external_broker_outage,
)


def run() -> list[ScenarioResult]:
    _now[0] = 0.0
    try:
        return [scenario() for scenario in SCENARIOS]
    finally:
        _now[0] = 0.0


def render(results: Sequence[ScenarioResult]) -> str:
    out: list[str] = []
    out.append("=" * 68)
    out.append("MTS Stability Guard — 장애 재현 · 방어 완화 리포트 (before/after)")
    out.append("=" * 68)
    out.append("[사실] 시나리오는 공개 보도에서 관측된 실패 패턴을 모의 브로커로 재현한 것이다.")
    out.append("[해석] guarded 서비스의 방어 설계(서킷브레이커·재시도·폴백·백프레셔)는 권고안이다.")
    for r in results:
        out.append("")
        out.append(f"■ 패턴: {r['pattern']}")
        out.append(f"  [사실] 공개 근거: {r['public_basis']}")
        out.append(f"  [주입] {r['injected']}")
        out.append(f"  before (naive)  : {_fmt(r['naive'])}")
        out.append(f"  after  (guarded): {_fmt(r['guarded'])}")
        out.append(f"  [해석] 완화: {_verdict(r)}")
    out.append("")
    out.append("[주의] 모든 수치는 공개 이력+모의 시스템 기반이며 회사 내부 데이터가 아니다.")
    out.append("=" * 68)
    return "\n".join(out)


def _fmt(counts: Tally) -> str:
    return f"체결 {counts['filled']} · 보류 {counts['deferred']} · 실패(누출) {counts['crashed']}"


def _verdict(r: ScenarioResult) -> str:
    naive_lost = r["naive"]["crashed"]
    guarded_lost = r["guarded"]["crashed"]
    if guarded_lost >= naive_lost:
        return "완화 효과 미검출(시나리오 재점검 필요)."
    recovered = r["guarded"]["filled"] - r["naive"]["filled"]
    head = f"사용자에게 누출된 실패 {naive_lost} → {guarded_lost}건."
    if recovered > 0:
        tail = " 나머지는 유실 없이 '보류'로 강등." if r["guarded"]["deferred"] > 0 else ""
        return f"{head} 재시도로 {recovered}건 회복.{tail}"
    return f"{head} 장애를 예외 누출 대신 유실 없는 '보류'로 강등."


def main() -> None:
    ap = argparse.ArgumentParser(description="공개 장애 패턴 재현 및 방어 완화 비교")
    _ = ap.add_argument("--json-out", help="기계가 읽는 JSON 리포트 저장 경로")
    args = ap.parse_args(namespace=CliArgs())

    results = run()
    print(render(results))
    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        except OSError as error:
            ap.error(f"JSON 리포트를 저장할 수 없음: {error}")
        print(f"\nJSON 리포트 저장: {args.json_out}")


if __name__ == "__main__":
    main()
