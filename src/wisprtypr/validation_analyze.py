from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any


def _classify_cluster(kind: str, normalized_text: str, corrected_text: str) -> tuple[str, str, str]:
    if kind in {"paste_replacement", "replacement"}:
        if normalized_text.lower() == corrected_text.lower():
            return "capitalization_fix", "Normalize casing in transcript output", "medium"
        stripped_normalized = normalized_text.replace(",", "").replace(".", "")
        stripped_corrected = corrected_text.replace(",", "").replace(".", "")
        if stripped_normalized == stripped_corrected:
            return "punctuation_fix", "Improve punctuation restoration in normalization", "medium"
        return "replacement_fix", "Investigate transcript substitutions and model defaults", "high"
    if kind == "deletion":
        return "overcommit_fix", "Investigate over-commit or unstable partial text", "high"
    if kind == "flagged_bad":
        return "flagged_bad", "Review user-flagged low-quality utterances", "medium"
    return "other", "Investigate validation correction cluster", "low"


def generate_ticket_drafts(db_path: Path, min_cases: int = 1) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                u.utterance_id,
                u.chunk_duration_seconds,
                u.raw_transcript,
                u.normalized_transcript,
                c.corrected_text,
                c.kind,
                c.confidence,
                c.observed
            FROM utterances u
            JOIN corrections c ON c.utterance_id = u.utterance_id
            WHERE c.observed = 1
            """
        ).fetchall()

        clusters: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for row in rows:
            cluster_key, _title, _severity = _classify_cluster(row[5], row[3], row[4])
            clusters[f"{cluster_key}:{row[1]}s"].append(row)

        generated = []
        for cluster_key, items in clusters.items():
            if len(items) < min_cases:
                continue
            sample = items[0]
            cluster_type, title, severity = _classify_cluster(sample[5], sample[3], sample[4])
            evidence = {
                "cluster_type": cluster_type,
                "chunk_duration_seconds": sample[1],
                "count": len(items),
                "examples": [
                    {
                        "utterance_id": item[0],
                        "raw_transcript": item[2],
                        "normalized_transcript": item[3],
                        "corrected_text": item[4],
                        "confidence": item[6],
                    }
                    for item in items[:5]
                ],
            }
            connection.execute(
                """
                INSERT INTO ticket_drafts (generated_at, cluster_key, title, severity, evidence_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    cluster_key,
                    title,
                    severity,
                    json.dumps(evidence, sort_keys=True),
                ),
            )
            generated.append(
                {
                    "cluster_key": cluster_key,
                    "title": title,
                    "severity": severity,
                    "evidence": evidence,
                }
            )
    return generated


def validation_analyze_main() -> None:
    parser = argparse.ArgumentParser(description="Analyze validation data and emit ticket drafts")
    parser.add_argument("--db", type=Path, default=Path("artifacts/validation/validation.sqlite3"))
    parser.add_argument("--min-cases", type=int, default=1)
    args = parser.parse_args()

    drafts = generate_ticket_drafts(args.db, min_cases=args.min_cases)
    for draft in drafts:
        print(f"[{draft['severity']}] {draft['title']} ({draft['cluster_key']})")
