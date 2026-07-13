from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "src" / "bin" / "independence_screen.py"
SERVICE_HEADER = (
    "client_id,client_name,service_type,service_description,service_year,fee_million_krw"
)


def write_csv(path: Path, lines: tuple[str, ...]) -> str:
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return os.fspath(path)


def write_rules(path: Path, review_service_type: str) -> str:
    rules = {
        "prohibited_service_types": [],
        "review_service_types": [review_service_type],
        "network_service_keywords": [],
    }
    _ = path.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    return os.fspath(path)


def test_markdown_table_escapes_pipe_characters_when_input_contains_delimiters(
    tmp_path: Path,
) -> None:
    # Given: matched CSV rows whose Markdown table cells contain pipe delimiters.
    audit = write_csv(
        tmp_path / "audit.csv",
        ("client_id,client_name,audit_year", "A001,감사|고객,2025"),
    )
    services = write_csv(
        tmp_path / "services.csv",
        (SERVICE_HEADER, "A001,감사|고객,tax|advisory,계약|설명,2025,20"),
    )
    rules = write_rules(tmp_path / "rules.json", "tax|advisory")

    # When: the CLI renders a Markdown report.
    result = subprocess.run(
        [
            sys.executable,
            os.fspath(SCRIPT),
            "--audit-clients",
            audit,
            "--non-audit-services",
            services,
            "--rules",
            rules,
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: table-cell delimiters from input are escaped rather than splitting columns.
    assert result.returncode == 0, result.stderr
    assert "감사\\|고객" in result.stdout
    assert "tax\\|advisory" in result.stdout
    assert "감사|고객" not in result.stdout


def test_markdown_table_escapes_backslashes_when_input_contains_paths(
    tmp_path: Path,
) -> None:
    # Given: matched CSV rows contain Windows-style path separators.
    audit = write_csv(
        tmp_path / "audit.csv",
        ("client_id,client_name,audit_year", r"A001,C:\Audit\Client,2025"),
    )
    services = write_csv(
        tmp_path / "services.csv",
        (
            SERVICE_HEADER,
            r"A001,C:\Audit\Client,C:\Projects\ERP,path review,2025,20",
        ),
    )
    rules = write_rules(tmp_path / "rules.json", r"C:\Projects\ERP")

    # When: the CLI renders a Markdown report.
    result = subprocess.run(
        [
            sys.executable,
            os.fspath(SCRIPT),
            "--audit-clients",
            audit,
            "--non-audit-services",
            services,
            "--rules",
            rules,
        ],
        cwd=PLUGIN_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: backslashes are escaped so Markdown does not reinterpret the input.
    assert result.returncode == 0, result.stderr
    assert r"C:\\Audit\\Client" in result.stdout
    assert r"C:\\Projects\\ERP" in result.stdout
    assert r"C:\Audit\Client" not in result.stdout
