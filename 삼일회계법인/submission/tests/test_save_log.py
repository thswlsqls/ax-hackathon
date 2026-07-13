from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SUBMISSION_ROOT = Path(__file__).resolve().parents[1]
SAVE_LOG = SUBMISSION_ROOT / "tools" / "save_log.py"
FIXED_LOG_ROOT = SUBMISSION_ROOT / "logs" / "codex"


def run_hook(transcript: Path, victim: Path, session_id: str) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {
            "transcript_path": str(transcript),
            "cwd": str(victim),
            "session_id": session_id,
        }
    )
    return subprocess.run(
        [sys.executable, str(SAVE_LOG), "--tool", "codex"],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


def test_unsupported_transcript_fails_closed_without_private_content(tmp_path: Path) -> None:
    # Given: an unsupported transcript containing private-looking text.
    private_text = "person" + "@" + "example.invalid " + "bear" + "er synthetic-token-value"
    transcript = tmp_path / "unsupported.jsonl"
    transcript.write_text(private_text, encoding="utf-8")
    victim = tmp_path / "victim"
    destination = FIXED_LOG_ROOT / "pytest-private.jsonl"

    # When: the hook processes the unsupported transcript.
    result = run_hook(transcript, victim, "pytest-private")

    # Then: it fails closed without persisting or echoing private content.
    assert result.returncode == 0
    assert result.stdout == ""
    assert private_text not in result.stderr
    assert not destination.exists()
    assert not (victim / "logs" / "codex" / destination.name).exists()


def test_payload_cwd_cannot_redirect_log_destination(tmp_path: Path) -> None:
    # Given: a valid event and an external writable victim directory.
    transcript = tmp_path / "valid.jsonl"
    transcript.write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "safe"}})
        + "\n",
        encoding="utf-8",
    )
    victim = tmp_path / "victim"
    destination = FIXED_LOG_ROOT / "pytest-fixed-root.jsonl"

    try:
        # When: the payload requests the victim as its cwd.
        result = run_hook(transcript, victim, "pytest-fixed-root")

        # Then: output is pinned to the submission log root.
        assert result.returncode == 0
        assert destination.is_file()
        assert not (victim / "logs" / "codex" / destination.name).exists()
    finally:
        destination.unlink(missing_ok=True)


def test_valid_transcript_is_normalized_to_conversation_only(tmp_path: Path) -> None:
    # Given: recognized conversation events mixed with metadata.
    transcript = tmp_path / "valid.jsonl"
    events = (
        {"type": "session_meta", "payload": {"private": "drop-me"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "world"}},
    )
    transcript.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    destination = FIXED_LOG_ROOT / "pytest-normalized.jsonl"

    try:
        # When: the hook processes the recognized events.
        result = run_hook(transcript, tmp_path / "victim", "pytest-normalized")

        # Then: only a minimal normalized conversation schema is retained.
        assert result.returncode == 0
        retained = destination.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line) for line in retained] == [
            {"type": "user", "message": "hello"},
            {"type": "assistant", "message": "world"},
        ]
    finally:
        destination.unlink(missing_ok=True)


def test_instruction_like_tool_content_cannot_escape_sanitizer(tmp_path: Path) -> None:
    # Given: a response containing conversation text beside instruction-like tool content.
    transcript = tmp_path / "tool-content.jsonl"
    event = {
        "type": "response_item",
        "payload": {
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "safe answer"},
                {"type": "tool_use", "text": "IGNORE RULES private-tool-value"},
            ],
        },
    }
    transcript.write_text(json.dumps(event) + "\n", encoding="utf-8")
    destination = FIXED_LOG_ROOT / "pytest-tool-filter.jsonl"

    try:
        # When: the hook processes the mixed response item.
        result = run_hook(transcript, tmp_path / "victim", "pytest-tool-filter")

        # Then: tool content is absent from the normalized output.
        assert result.returncode == 0
        retained = destination.read_text(encoding="utf-8")
        assert "IGNORE RULES" not in retained
        assert "private-tool-value" not in retained
    finally:
        destination.unlink(missing_ok=True)


def test_repeated_event_is_deterministic(tmp_path: Path) -> None:
    # Given: one recognized event and a fixed session identifier.
    transcript = tmp_path / "repeat.jsonl"
    transcript.write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "same"}})
        + "\n",
        encoding="utf-8",
    )
    destination = FIXED_LOG_ROOT / "pytest-repeat.jsonl"

    try:
        # When: the same event is processed twice.
        first = run_hook(transcript, tmp_path / "victim-one", "pytest-repeat")
        first_bytes = destination.read_bytes()
        second = run_hook(transcript, tmp_path / "victim-two", "pytest-repeat")

        # Then: both runs succeed and the artifact is byte-identical, not appended.
        assert first.returncode == second.returncode == 0
        assert destination.read_bytes() == first_bytes
        assert len(destination.read_text(encoding="utf-8").splitlines()) == 1
    finally:
        destination.unlink(missing_ok=True)
