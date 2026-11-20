"""Immutable SQLite staging for GEDCOM imports and validation findings."""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from .genealogy import GedcomRepository
from .validation import RULESET_VERSION, validate_repository


SCHEMA_VERSION = 3
PARSER_VERSION = 3
RECORD_HEADER = re.compile(r"^0\s+(?:@([^@]+)@\s+)?(\S+)(?:\s+.*)?$")


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_batch (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    payload BLOB NOT NULL,
    encoding TEXT NOT NULL,
    parser_version INTEGER NOT NULL,
    ruleset_version TEXT NOT NULL,
    people_count INTEGER NOT NULL,
    family_count INTEGER NOT NULL,
    fatal_count INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    notice_count INTEGER NOT NULL,
    validation_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id TEXT NOT NULL REFERENCES import_batch(id),
    ordinal INTEGER NOT NULL,
    xref TEXT,
    record_type TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    UNIQUE (import_id, ordinal)
);

CREATE TABLE IF NOT EXISTS validation_finding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id TEXT NOT NULL REFERENCES import_batch(id),
    fingerprint TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('fatal', 'error', 'warning', 'notice')),
    message TEXT NOT NULL,
    people_json TEXT NOT NULL,
    families_json TEXT NOT NULL,
    values_json TEXT NOT NULL,
    UNIQUE (import_id, fingerprint)
);

-- Validation is versioned independently from the immutable source file. These
-- v2 tables allow the same import to be checked again when parsing or rules
-- change. The original validation_finding table is retained for migration
-- compatibility with the first local staging database.
CREATE TABLE IF NOT EXISTS validation_run (
    id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES import_batch(id),
    ran_at TEXT NOT NULL,
    parser_version INTEGER NOT NULL,
    ruleset_version TEXT NOT NULL,
    fatal_count INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    warning_count INTEGER NOT NULL,
    notice_count INTEGER NOT NULL,
    validation_json TEXT NOT NULL,
    UNIQUE (import_id, parser_version, ruleset_version)
);

CREATE TABLE IF NOT EXISTS validation_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    validation_run_id TEXT NOT NULL REFERENCES validation_run(id),
    fingerprint TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('fatal', 'error', 'warning', 'notice')),
    message TEXT NOT NULL,
    people_json TEXT NOT NULL,
    families_json TEXT NOT NULL,
    values_json TEXT NOT NULL,
    UNIQUE (validation_run_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS review_decision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    validation_run_id TEXT NOT NULL REFERENCES validation_run(id),
    finding_fingerprint TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('accepted', 'false_positive', 'corrected_upstream', 'superseded')
    ),
    rationale TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS raw_record_import_xref
    ON raw_record(import_id, xref);
CREATE INDEX IF NOT EXISTS validation_finding_import_severity
    ON validation_finding(import_id, severity, rule_code);
CREATE INDEX IF NOT EXISTS validation_run_import_version
    ON validation_run(import_id, parser_version, ruleset_version);
CREATE INDEX IF NOT EXISTS validation_result_run_severity
    ON validation_result(validation_run_id, severity, rule_code);
CREATE INDEX IF NOT EXISTS review_decision_finding
    ON review_decision(validation_run_id, finding_fingerprint, id);

CREATE TRIGGER IF NOT EXISTS immutable_import_batch_update
BEFORE UPDATE ON import_batch BEGIN
    SELECT RAISE(ABORT, 'import_batch rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_import_batch_delete
BEFORE DELETE ON import_batch BEGIN
    SELECT RAISE(ABORT, 'import_batch rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_raw_record_update
BEFORE UPDATE ON raw_record BEGIN
    SELECT RAISE(ABORT, 'raw_record rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_raw_record_delete
BEFORE DELETE ON raw_record BEGIN
    SELECT RAISE(ABORT, 'raw_record rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_finding_update
BEFORE UPDATE ON validation_finding BEGIN
    SELECT RAISE(ABORT, 'validation_finding rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_finding_delete
BEFORE DELETE ON validation_finding BEGIN
    SELECT RAISE(ABORT, 'validation_finding rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_run_update
BEFORE UPDATE ON validation_run BEGIN
    SELECT RAISE(ABORT, 'validation_run rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_run_delete
BEFORE DELETE ON validation_run BEGIN
    SELECT RAISE(ABORT, 'validation_run rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_result_update
BEFORE UPDATE ON validation_result BEGIN
    SELECT RAISE(ABORT, 'validation_result rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_validation_result_delete
BEFORE DELETE ON validation_result BEGIN
    SELECT RAISE(ABORT, 'validation_result rows are immutable');
END;
CREATE TRIGGER IF NOT EXISTS immutable_review_decision_update
BEFORE UPDATE ON review_decision BEGIN
    SELECT RAISE(ABORT, 'review_decision rows are append-only');
END;
CREATE TRIGGER IF NOT EXISTS immutable_review_decision_delete
BEFORE DELETE ON review_decision BEGIN
    SELECT RAISE(ABORT, 'review_decision rows are append-only');
END;
"""


def split_raw_records(text):
    """Return lossless top-level GEDCOM blocks in source order."""
    blocks = []
    current = []
    for line in text.splitlines(keepends=True):
        if line.startswith("0 ") and current:
            blocks.append("".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append("".join(current))
    return blocks


def record_identity(raw_text):
    first_line = raw_text.splitlines()[0] if raw_text else ""
    match = RECORD_HEADER.match(first_line)
    if not match:
        return None, "UNKNOWN"
    return match.group(1), match.group(2)


def finding_fingerprint(finding):
    material = json.dumps({
        "rule": finding.code,
        "version": finding.rule_version,
        "people": finding.people,
        "families": finding.families,
        "values": finding.values,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ImportStore:
    def __init__(self, database_path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        with self.session() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """INSERT INTO schema_metadata(key, value) VALUES ('schema_version', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (str(SCHEMA_VERSION),),
            )

    def stage(self, gedcom_path):
        source = Path(gedcom_path)
        payload = source.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        # Strict decoding fails the staging operation rather than repairing bytes.
        text = payload.decode("utf-8-sig")
        repository = GedcomRepository(source, show_living=True)
        report = validate_repository(repository)
        counts = report.counts

        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM import_batch WHERE sha256 = ?", (checksum,)
            ).fetchone()
            inserted = existing is None
            import_id = existing["id"] if existing else str(uuid.uuid4())
            if inserted:
                connection.execute(
                    """INSERT INTO import_batch(
                        id, sha256, original_filename, imported_at, byte_size, payload,
                        encoding, parser_version, ruleset_version, people_count,
                        family_count, fatal_count, error_count, warning_count,
                        notice_count, validation_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        import_id, checksum, source.name,
                        datetime.now(timezone.utc).isoformat(), len(payload), payload,
                        "UTF-8", PARSER_VERSION, RULESET_VERSION,
                        report.people_count, report.family_count,
                        counts["fatal"], counts["error"], counts["warning"], counts["notice"],
                        report.to_json(),
                    ),
                )
                for ordinal, raw_text in enumerate(split_raw_records(text)):
                    xref, record_type = record_identity(raw_text)
                    connection.execute(
                        "INSERT INTO raw_record(import_id, ordinal, xref, record_type, raw_text) VALUES (?, ?, ?, ?, ?)",
                        (import_id, ordinal, xref, record_type, raw_text),
                    )

            validation_run_id = str(uuid.uuid4())
            cursor = connection.execute(
                """INSERT OR IGNORE INTO validation_run(
                    id, import_id, ran_at, parser_version, ruleset_version,
                    fatal_count, error_count, warning_count, notice_count, validation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    validation_run_id, import_id, datetime.now(timezone.utc).isoformat(),
                    PARSER_VERSION, RULESET_VERSION, counts["fatal"], counts["error"],
                    counts["warning"], counts["notice"], report.to_json(),
                ),
            )
            validation_inserted = cursor.rowcount == 1
            if validation_inserted:
                for finding in report.findings:
                    connection.execute(
                        """INSERT INTO validation_result(
                            validation_run_id, fingerprint, rule_code, rule_version,
                            severity, message, people_json, families_json, values_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            validation_run_id, finding_fingerprint(finding), finding.code,
                            finding.rule_version, finding.severity, finding.message,
                            json.dumps(finding.people), json.dumps(finding.families),
                            json.dumps(finding.values, sort_keys=True),
                        ),
                    )
            return {
                **self.get(import_id, connection),
                "inserted": inserted,
                "validation_inserted": validation_inserted,
            }

    def get(self, import_id, connection=None):
        own_connection = connection is None
        connection = connection or self.connect()
        try:
            row = connection.execute(
                """SELECT id, sha256, original_filename, imported_at, byte_size,
                          people_count, family_count, fatal_count, error_count,
                          warning_count, notice_count, ruleset_version
                   FROM import_batch WHERE id = ?""",
                (import_id,),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            validation = connection.execute(
                """SELECT id, parser_version, ruleset_version, fatal_count,
                          error_count, warning_count, notice_count
                   FROM validation_run WHERE import_id = ?
                   ORDER BY ran_at DESC, id DESC LIMIT 1""",
                (import_id,),
            ).fetchone()
            if validation:
                validation = dict(validation)
                result["validation_run_id"] = validation.pop("id")
                result.update(validation)
            result["record_count"] = connection.execute(
                "SELECT COUNT(*) FROM raw_record WHERE import_id = ?", (import_id,)
            ).fetchone()[0]
            unresolved = 0
            if validation:
                unresolved = connection.execute(
                    """SELECT COUNT(*) FROM validation_result result
                       WHERE result.validation_run_id = ? AND result.severity = 'warning'
                         AND COALESCE((
                             SELECT decision FROM review_decision decision
                             WHERE decision.validation_run_id = result.validation_run_id
                               AND decision.finding_fingerprint = result.fingerprint
                             ORDER BY decision.id DESC LIMIT 1
                         ), '') NOT IN ('accepted', 'false_positive')""",
                    (result["validation_run_id"],),
                ).fetchone()[0]
            result["unresolved_warning_count"] = unresolved
            result["publishable"] = not (
                result["fatal_count"] or result["error_count"] or unresolved
            )
            return result
        finally:
            if own_connection:
                connection.close()

    def list_imports(self):
        with self.session() as connection:
            ids = [row["id"] for row in connection.execute(
                "SELECT id FROM import_batch ORDER BY imported_at DESC"
            )]
            return [self.get(import_id, connection) for import_id in ids]

    def review_queue(self, import_id):
        with self.session() as connection:
            staged = self.get(import_id, connection)
            if not staged or not staged.get("validation_run_id"):
                return []
            rows = connection.execute(
                """SELECT result.fingerprint, result.rule_code, result.severity,
                          result.message, result.people_json, result.families_json,
                          result.values_json,
                          (SELECT decision FROM review_decision decision
                           WHERE decision.validation_run_id = result.validation_run_id
                             AND decision.finding_fingerprint = result.fingerprint
                           ORDER BY decision.id DESC LIMIT 1) AS decision,
                          (SELECT rationale FROM review_decision decision
                           WHERE decision.validation_run_id = result.validation_run_id
                             AND decision.finding_fingerprint = result.fingerprint
                           ORDER BY decision.id DESC LIMIT 1) AS rationale
                   FROM validation_result result
                   WHERE result.validation_run_id = ?
                   ORDER BY CASE result.severity
                       WHEN 'fatal' THEN 0 WHEN 'error' THEN 1
                       WHEN 'warning' THEN 2 ELSE 3 END,
                       result.rule_code, result.message""",
                (staged["validation_run_id"],),
            ).fetchall()
            return [{
                **{key: row[key] for key in row.keys()
                   if key not in ("people_json", "families_json", "values_json")},
                "people": json.loads(row["people_json"]),
                "families": json.loads(row["families_json"]),
                "values": json.loads(row["values_json"]),
            } for row in rows]

    def record_decision(self, import_id, fingerprint, decision, rationale, reviewer):
        allowed = {"accepted", "false_positive", "corrected_upstream", "superseded"}
        if decision not in allowed:
            raise ValueError(f"Unknown decision: {decision}")
        if not rationale.strip() or not reviewer.strip():
            raise ValueError("A reviewer and rationale are required")
        with self.session() as connection:
            staged = self.get(import_id, connection)
            if not staged or not staged.get("validation_run_id"):
                raise ValueError("Import or validation run not found")
            finding = connection.execute(
                """SELECT severity FROM validation_result
                   WHERE validation_run_id = ? AND fingerprint = ?""",
                (staged["validation_run_id"], fingerprint),
            ).fetchone()
            if not finding:
                raise ValueError("Finding not found in the latest validation run")
            if finding["severity"] in ("fatal", "error") and decision in ("accepted", "false_positive"):
                raise ValueError("Fatal and error findings cannot be waived; correct the source and re-import")
            connection.execute(
                """INSERT INTO review_decision(
                    validation_run_id, finding_fingerprint, decision, rationale,
                    reviewer, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    staged["validation_run_id"], fingerprint, decision,
                    rationale.strip(), reviewer.strip(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return self.get(import_id, connection)
