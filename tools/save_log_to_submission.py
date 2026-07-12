#!/usr/bin/env python3
"""Claude Code Stop/SessionEnd 훅 래퍼 — log-hooks 로그를 카카오페이증권 제출 폴더로 보낸다.

공식 save_log.py는 로그를 `<payload.cwd>/logs/<tool>/`에 저장한다. 이 세션의 작업
디렉터리는 저장소 루트라 기본값으로는 루트에 저장되므로, 여기서 payload의 cwd만
제출 패키지 경로로 덮어써서 최종 산출물이 `카카오페이증권/submission/logs/claude-code/`에
쌓이도록 한다. save_log.py 자체는 원본 그대로 두고 위임한다(로그 가공 아님).
"""
import json
import os
import subprocess
import sys

REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBMISSION = os.path.join(REPOSITORY_ROOT, "카카오페이증권", "submission")


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001 - 비치명적, 로깅 실패가 세션을 막지 않게 한다
        payload = {}
    payload["cwd"] = SUBMISSION  # 출력 경로만 제출 폴더로 라우팅
    save_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save_log.py")
    try:
        subprocess.run(
            [sys.executable, save_log, "--tool", "claude-code"],
            input=json.dumps(payload), text=True,
        )
    except Exception as exc:  # noqa: BLE001 - 비치명적
        print(f"save_log_to_submission: delegate failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
