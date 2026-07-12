#!/usr/bin/env python3
"""입점·납품 계약서 리스크 조항 스캐너 (결정론적 baseline).

계약서 텍스트를 조항 단위로 분할하고, clause_rules.json 규칙의 trigger 키워드를
매칭해 리스크 후보 조항을 찾아낸다. LLM 스킬(SKILL.md)이 이 결과를 받아 검토·
보강하도록 설계된 사전 스캐너이며, 그 자체로 위법성을 확정하지 않는다.

표준 라이브러리만 사용한다. 외부 의존성 없음.

사용법:
    python3 scan_contract.py <계약서.txt> [--rules <clause_rules.json>]
                             [--format json|md] [--min-risk 상|중|하]

예:
    python3 scan_contract.py ../fixtures/sample_contract_01.md --format md
"""
import argparse
import json
import os
import re
import sys
from typing import Optional, TypedDict


class Rule(TypedDict, total=False):
    id: str
    name: str
    category: str
    risk: str
    triggers: list[str]
    law_reference: str
    why: str
    suggestion: str


class Finding(TypedDict):
    clause: str
    rule_id: str
    rule_name: str
    category: str
    risk: str
    matched_terms: list[str]
    law_reference: str
    why: str
    suggestion: str
    snippet: str

RISK_ORDER = {"상": 3, "중": 2, "하": 1}
DEFAULT_RULES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "rules", "clause_rules.json"
)

CLAUSE_HEADER = re.compile(
    r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?"
    r"(?:\s*(?:\([^)\n]*\)|\[[^\]\n]*\])|\s*[:：]\s*[^\n]+|\s+(?!.*제\s*\d+\s*조)[^\n]+)?\s*$",
    re.MULTILINE,
)


def load_rules(path: str) -> tuple[dict[str, str], list[Rule]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("meta", {}), data.get("rules", [])


def split_clauses(text: str) -> list[tuple[str, str]]:
    """계약서 텍스트를 조항(제N조) 단위로 분할한다.

    조항 헤더가 하나도 없으면 문단(빈 줄 기준)으로 분할한다.
    반환: [(label, body), ...]
    """
    matches = list(CLAUSE_HEADER.finditer(text))
    if not matches:
        chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
        return [("문단 %d" % (i + 1), c) for i, c in enumerate(chunks)]

    clauses = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        clauses.append(("전문", preamble))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # 헤더 라인을 라벨로 사용
        label = body.splitlines()[0].strip() if body else m.group(0)
        clauses.append((label, body))
    return clauses


def scan(
    text: str, rules: list[Rule], min_risk: str = "하"
) -> list[Finding]:
    threshold = RISK_ORDER.get(min_risk, 1)
    clauses = split_clauses(text)
    findings = []
    for label, body in clauses:
        for rule in rules:
            if RISK_ORDER.get(rule.get("risk", "하"), 1) < threshold:
                continue
            hits = [t for t in rule.get("triggers", []) if t in body]
            if not hits:
                continue
            findings.append(
                {
                    "clause": label,
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "category": rule.get("category", ""),
                    "risk": rule.get("risk", ""),
                    "matched_terms": hits,
                    "law_reference": rule.get("law_reference", ""),
                    "why": rule.get("why", ""),
                    "suggestion": rule.get("suggestion", ""),
                    "snippet": _snippet(body, hits[0]),
                }
            )
    findings.sort(key=lambda x: RISK_ORDER.get(x["risk"], 1), reverse=True)
    return findings


def _snippet(body: str, term: str, width: int = 40) -> str:
    idx = body.find(term)
    if idx < 0:
        return body[:80].replace("\n", " ")
    start = max(0, idx - width)
    end = min(len(body), idx + len(term) + width)
    return ("…" if start > 0 else "") + body[start:end].replace("\n", " ").strip() + (
        "…" if end < len(body) else ""
    )


def to_markdown(findings: list[Finding], meta: dict[str, str], source: str) -> str:
    lines = []
    lines.append("# 계약서 리스크 스캔 결과")
    lines.append("")
    lines.append("- 대상 파일: `%s`" % source)
    lines.append("- 탐지 조항 수: **%d건**" % len(findings))
    counts = {}
    for f in findings:
        counts[f["risk"]] = counts.get(f["risk"], 0) + 1
    if counts:
        lines.append(
            "- 위험등급 분포: "
            + ", ".join("%s %d건" % (k, counts[k]) for k in ["상", "중", "하"] if k in counts)
        )
    lines.append("")
    lines.append("> ⚠️ %s" % meta.get("disclaimer", "본 결과는 법률 자문이 아니다."))
    lines.append("")
    if not findings:
        lines.append("탐지된 리스크 조항이 없습니다. (규칙 미매칭 — 수동 검토 권장)")
        return "\n".join(lines)
    for i, f in enumerate(findings, 1):
        lines.append("## %d. [%s] %s" % (i, f["risk"], f["rule_name"]))
        lines.append("")
        lines.append("- **조항**: %s" % f["clause"])
        lines.append("- **매칭 표현**: %s" % ", ".join("`%s`" % t for t in f["matched_terms"]))
        lines.append("- **발췌**: %s" % f["snippet"])
        lines.append("- **근거 법조문**: %s" % f["law_reference"])
        lines.append("- **왜 리스크인가**: %s" % f["why"])
        lines.append("- **대체 문구 방향**: %s" % f["suggestion"])
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="입점·납품 계약서 리스크 조항 스캐너")
    parser.add_argument("contract", help="계약서 텍스트 파일 경로 (.txt/.md)")
    parser.add_argument("--rules", default=DEFAULT_RULES, help="규칙 카탈로그 JSON 경로")
    parser.add_argument("--format", choices=["json", "md"], default="md", help="출력 형식")
    parser.add_argument(
        "--min-risk", choices=["상", "중", "하"], default="하", help="이 등급 이상만 출력"
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.contract):
        sys.stderr.write("계약서 파일을 찾을 수 없습니다: %s\n" % args.contract)
        return 2

    meta, rules = load_rules(args.rules)
    with open(args.contract, "r", encoding="utf-8") as f:
        text = f.read()

    findings = scan(text, rules, min_risk=args.min_risk)

    if args.format == "json":
        print(
            json.dumps(
                {"source": args.contract, "count": len(findings), "findings": findings},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(to_markdown(findings, meta, args.contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
