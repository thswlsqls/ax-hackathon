#!/usr/bin/env python3
"""Stop-hook helper: saves the AI chat transcript into the submission's logs/ folder.

Invoked automatically by the Claude Code / Codex Stop hook after each turn.
Output: logs/<tool>/<session_id>.jsonl  (tool = claude-code | codex).
You do not need to run or edit this file.
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Union

JsonValue = Union[None, bool, int, float, str, list["JsonValue"], dict[str, "JsonValue"]]
JsonObject = dict[str, JsonValue]

_CODEX_CONV_EVENTS = ("user_message", "agent_message")
_CODEX_SYSTEM_PREFIXES = ("<permissions", "<environment_context", "<user_instructions")
_SUBMISSION_ROOT = Path(__file__).resolve().parents[1]


def _content_text(content: JsonValue) -> str:
    """message content (str or block list) -> conversation text only.

    Ignores tool_use/tool_result/thinking blocks, so a line carrying only those
    yields "" (and is dropped). Used to decide whether a line is real conversation.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if block.get("type") in ("text", "input_text", "output_text") and isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _claude_conversation(obj: JsonValue) -> Union[JsonObject, None]:
    if not isinstance(obj, dict) or obj.get("type") not in ("user", "assistant"):
        return None
    if obj.get("isMeta"):
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    text = _content_text(message.get("content"))
    if not text:
        return None
    return {"type": obj["type"], "message": text}


def _codex_event_conversation(obj: JsonValue) -> Union[JsonObject, None]:
    if not isinstance(obj, dict) or obj.get("type") != "event_msg":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") not in _CODEX_CONV_EVENTS:
        return None
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    role = "user" if payload["type"] == "user_message" else "assistant"
    return {"type": role, "message": message.strip()}


def _codex_response_conversation(obj: JsonValue) -> Union[JsonObject, None]:
    if not isinstance(obj, dict) or obj.get("type") != "response_item":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("role") not in ("user", "assistant"):
        return None
    text = _content_text(payload.get("content"))
    if not text or text.lstrip().startswith(_CODEX_SYSTEM_PREFIXES):
        return None
    return {"type": payload["role"], "message": text}


def slim_transcript(raw: str, tool: str) -> Union[str, None]:
    """Normalize supported conversation events into a minimal JSONL schema.

    Drops lines that carry no user/assistant conversation text — tool calls/results,
    thinking/reasoning, session metadata, skill listings. Returns None when nothing
    parses or no supported conversation event is found. Unparseable lines are skipped.
    """
    parsed: list[JsonValue] = []
    for line in raw.split("\n"):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except (ValueError, TypeError):
            continue
        parsed.append(obj)
    if not parsed:
        return None
    if tool == "codex":
        kept = [event for obj in parsed if (event := _codex_event_conversation(obj)) is not None]
        if not kept:
            kept = [
                event
                for obj in parsed
                if (event := _codex_response_conversation(obj)) is not None
            ]
    else:
        kept = [event for obj in parsed if (event := _claude_conversation(obj)) is not None]
    if not kept:
        return None
    return "\n".join(
        json.dumps(event, ensure_ascii=False, separators=(",", ":")) for event in kept
    ) + "\n"


def main() -> int:
    # Never write to stdout — Codex parses Stop-hook stdout as a decision.
    # Always exit 0 so a logging failure never blocks the participant's session.
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True, choices=["claude-code", "codex"])
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print("save_log: invalid hook payload", file=sys.stderr)
        return 0

    if not isinstance(payload, dict):
        print("save_log: invalid hook payload", file=sys.stderr)
        return 0

    transcript_path = payload.get("transcript_path")
    session_id = payload.get("session_id") or "session"

    if not transcript_path or not os.path.isfile(transcript_path):
        print("save_log: transcript unavailable", file=sys.stderr)
        return 0

    safe_session = os.path.basename(str(session_id))
    if safe_session in ("", ".", ".."):
        safe_session = "session"
    dest_dir = _SUBMISSION_ROOT / "logs" / args.tool
    dest = dest_dir / f"{safe_session}.jsonl"

    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        slim = slim_transcript(raw, args.tool)
        if slim is None:
            print("save_log: no supported conversation events", file=sys.stderr)
            return 0
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(slim, encoding="utf-8")
    except OSError:
        print("save_log: transcript capture failed", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
