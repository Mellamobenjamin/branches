"""Canonical genealogy, evidence, and artifact storage.

This layer is intentionally separate from the public GEDCOM repository while the
site is migrated. It can share the staging SQLite file without changing current
Flask route behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import csv
import json
from pathlib import Path
import sqlite3
import uuid


MIGRATIONS = (
    (
        1,
        """
        CREATE TABLE canonical_person (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            privacy_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
                privacy_status IN ('public', 'private', 'living', 'unknown')
            ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE person_name (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            name_text TEXT NOT NULL,
            name_type TEXT NOT NULL DEFAULT 'primary' CHECK (
                name_type IN ('primary', 'birth', 'married', 'alias', 'variant')
            ),
            preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
            UNIQUE (person_id, name_text, name_type)
        );

        CREATE UNIQUE INDEX one_preferred_person_name
            ON person_name(person_id) WHERE preferred = 1;

        CREATE TABLE external_identifier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            system TEXT NOT NULL,
            value TEXT NOT NULL,
            import_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (system, value)
        );

        CREATE TABLE family_union (
            id TEXT PRIMARY KEY,
            union_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
                union_type IN ('marriage', 'partnership', 'unknown')
            ),
            status TEXT NOT NULL DEFAULT 'asserted' CHECK (
                status IN ('asserted', 'preferred', 'rejected', 'needs_review')
            ),
            created_at TEXT NOT NULL
        );

        CREATE TABLE union_partner (
            union_id TEXT NOT NULL REFERENCES family_union(id),
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            role TEXT NOT NULL DEFAULT 'partner',
            PRIMARY KEY (union_id, person_id)
        );

        CREATE TABLE parent_child_relationship (
            id TEXT PRIMARY KEY,
            parent_id TEXT NOT NULL REFERENCES canonical_person(id),
            child_id TEXT NOT NULL REFERENCES canonical_person(id),
            relationship_type TEXT NOT NULL DEFAULT 'unknown' CHECK (
                relationship_type IN ('biological', 'adoptive', 'step', 'foster', 'guardian', 'unknown')
            ),
            status TEXT NOT NULL DEFAULT 'asserted' CHECK (
                status IN ('asserted', 'preferred', 'rejected', 'needs_review')
            ),
            confidence TEXT NOT NULL DEFAULT 'unknown' CHECK (
                confidence IN ('high', 'medium', 'low', 'unknown')
            ),
            source_import_id TEXT,
            created_at TEXT NOT NULL,
            CHECK (parent_id <> child_id),
            UNIQUE (parent_id, child_id, relationship_type, source_import_id)
        );

        CREATE TABLE source (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'unknown',
            creator TEXT,
            publisher TEXT,
            repository TEXT,
            provider TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE citation (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source(id),
            locator_raw TEXT,
            source_url TEXT,
            accessed_at TEXT,
            verification_status TEXT NOT NULL DEFAULT 'provisional' CHECK (
                verification_status IN ('provisional', 'verified', 'rejected')
            ),
            created_at TEXT NOT NULL
        );

        CREATE TABLE artifact (
            id TEXT PRIMARY KEY,
            artifact_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
            original_filename TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            provider TEXT,
            description TEXT,
            review_status TEXT NOT NULL,
            rights_status TEXT NOT NULL CHECK (
                rights_status IN (
                    'unknown', 'ancestry-research-copy', 'owned',
                    'permission-granted', 'public-domain', 'licensed-display'
                )
            ),
            access_level TEXT NOT NULL CHECK (
                access_level IN ('private', 'family', 'public-citation', 'public-display')
            ),
            public_display INTEGER NOT NULL DEFAULT 0 CHECK (public_display IN (0, 1)),
            accessioned_at TEXT NOT NULL,
            CHECK (
                public_display = 0 OR (
                    access_level = 'public-display' AND
                    rights_status IN ('owned', 'permission-granted', 'public-domain', 'licensed-display')
                )
            )
        );

        CREATE TABLE artifact_representation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id TEXT NOT NULL REFERENCES artifact(id),
            filename TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
            representation_type TEXT NOT NULL DEFAULT 'alternate_capture',
            UNIQUE (artifact_id, filename)
        );

        CREATE TABLE artifact_subject_label (
            artifact_id TEXT NOT NULL REFERENCES artifact(id),
            subject_type TEXT NOT NULL CHECK (
                subject_type IN ('person', 'family', 'event', 'place')
            ),
            subject_label TEXT NOT NULL,
            resolution_status TEXT NOT NULL DEFAULT 'unresolved' CHECK (
                resolution_status IN ('unresolved', 'resolved', 'rejected')
            ),
            canonical_id TEXT,
            PRIMARY KEY (artifact_id, subject_type, subject_label)
        );

        CREATE TABLE citation_artifact (
            citation_id TEXT NOT NULL REFERENCES citation(id),
            artifact_id TEXT NOT NULL REFERENCES artifact(id),
            PRIMARY KEY (citation_id, artifact_id)
        );

        CREATE TABLE claim (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            claim_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'asserted' CHECK (
                status IN ('asserted', 'preferred', 'rejected', 'needs_review')
            ),
            summary TEXT,
            fingerprint TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE claim_value (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id TEXT NOT NULL REFERENCES claim(id),
            value_json TEXT NOT NULL,
            normalized_text TEXT,
            date_start TEXT,
            date_end TEXT,
            qualifier TEXT,
            UNIQUE (claim_id, value_json)
        );

        CREATE TABLE claim_citation (
            claim_id TEXT NOT NULL REFERENCES claim(id),
            citation_id TEXT NOT NULL REFERENCES citation(id),
            support_type TEXT NOT NULL DEFAULT 'supports' CHECK (
                support_type IN ('supports', 'contradicts', 'context')
            ),
            PRIMARY KEY (claim_id, citation_id, support_type)
        );

        CREATE TABLE claim_conflict (
            id TEXT PRIMARY KEY,
            first_claim_id TEXT NOT NULL REFERENCES claim(id),
            second_claim_id TEXT NOT NULL REFERENCES claim(id),
            status TEXT NOT NULL DEFAULT 'open' CHECK (
                status IN ('open', 'resolved', 'not_a_conflict')
            ),
            explanation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (first_claim_id <> second_claim_id),
            UNIQUE (first_claim_id, second_claim_id)
        );

        CREATE TABLE editorial_decision (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL CHECK (
                subject_type IN ('claim', 'relationship', 'artifact', 'conflict')
            ),
            subject_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            rationale TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            decided_at TEXT NOT NULL
        );

        CREATE TRIGGER immutable_editorial_decision_update
        BEFORE UPDATE ON editorial_decision BEGIN
            SELECT RAISE(ABORT, 'editorial decisions are append-only');
        END;
        CREATE TRIGGER immutable_editorial_decision_delete
        BEFORE DELETE ON editorial_decision BEGIN
            SELECT RAISE(ABORT, 'editorial decisions are append-only');
        END;

        CREATE INDEX external_identifier_person ON external_identifier(person_id);
        CREATE INDEX relationship_child ON parent_child_relationship(child_id, status);
        CREATE INDEX artifact_access ON artifact(access_level, public_display);
        CREATE INDEX artifact_subject_lookup ON artifact_subject_label(subject_type, subject_label);
        CREATE INDEX claim_person_type ON claim(person_id, claim_type, status);
        """,
    ),
    (
        2,
        """
        CREATE TABLE normalization_run (
            id TEXT PRIMARY KEY,
            import_id TEXT NOT NULL,
            normalizer_version INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK (
                status IN ('running', 'completed', 'failed')
            ),
            publication_status TEXT NOT NULL CHECK (
                publication_status IN ('blocked', 'ready', 'published', 'superseded')
            ),
            blocked_reason TEXT,
            people_count INTEGER NOT NULL DEFAULT 0,
            union_count INTEGER NOT NULL DEFAULT 0,
            relationship_count INTEGER NOT NULL DEFAULT 0,
            claim_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (import_id, normalizer_version)
        );

        CREATE TABLE person_import_assertion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            raw_person_xref TEXT NOT NULL,
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            match_method TEXT NOT NULL CHECK (
                match_method IN (
                    'external_identifier', 'identity_signature', 'new',
                    'ambiguous_new'
                )
            ),
            identity_signature TEXT NOT NULL,
            raw_name TEXT NOT NULL,
            privacy_status TEXT NOT NULL,
            UNIQUE (normalization_run_id, raw_person_xref)
        );

        CREATE TABLE person_identity_observation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            raw_person_xref TEXT NOT NULL,
            identity_signature TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            birth_start_year INTEGER,
            birth_end_year INTEGER,
            death_start_year INTEGER,
            death_end_year INTEGER,
            UNIQUE (normalization_run_id, raw_person_xref)
        );

        CREATE TABLE identity_match_candidate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            raw_person_xref TEXT NOT NULL,
            candidate_person_id TEXT NOT NULL REFERENCES canonical_person(id),
            match_reason TEXT NOT NULL,
            score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
            status TEXT NOT NULL DEFAULT 'open' CHECK (
                status IN ('open', 'accepted', 'rejected', 'superseded')
            ),
            UNIQUE (normalization_run_id, raw_person_xref, candidate_person_id)
        );

        CREATE TABLE imported_claim_assertion (
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            claim_id TEXT NOT NULL REFERENCES claim(id),
            raw_person_xref TEXT NOT NULL,
            event_ordinal INTEGER,
            field_name TEXT NOT NULL,
            PRIMARY KEY (normalization_run_id, claim_id)
        );

        CREATE TABLE family_union_identifier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            union_id TEXT NOT NULL REFERENCES family_union(id),
            system TEXT NOT NULL,
            value TEXT NOT NULL,
            normalization_run_id TEXT REFERENCES normalization_run(id),
            UNIQUE (system, value)
        );

        CREATE TABLE union_import_assertion (
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            raw_family_xref TEXT NOT NULL,
            union_id TEXT NOT NULL REFERENCES family_union(id),
            match_method TEXT NOT NULL CHECK (
                match_method IN ('external_identifier', 'new')
            ),
            PRIMARY KEY (normalization_run_id, raw_family_xref)
        );

        CREATE TABLE relationship_import_assertion (
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            relationship_id TEXT NOT NULL REFERENCES parent_child_relationship(id),
            raw_family_xref TEXT NOT NULL,
            raw_parent_xref TEXT NOT NULL,
            raw_child_xref TEXT NOT NULL,
            pedigree TEXT,
            pedigree_status TEXT,
            PRIMARY KEY (normalization_run_id, relationship_id, raw_family_xref)
        );

        CREATE TABLE normalization_finding (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            code TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (
                severity IN ('error', 'warning', 'notice')
            ),
            raw_xref TEXT,
            message TEXT NOT NULL,
            values_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX normalization_run_import
            ON normalization_run(import_id, normalizer_version);
        CREATE INDEX identity_observation_signature
            ON person_identity_observation(identity_signature, normalization_run_id);
        CREATE INDEX person_import_person
            ON person_import_assertion(person_id, normalization_run_id);
        CREATE INDEX identity_candidate_queue
            ON identity_match_candidate(normalization_run_id, status, score);
        CREATE INDEX imported_claim_run
            ON imported_claim_assertion(normalization_run_id, raw_person_xref);
        CREATE INDEX relationship_import_run
            ON relationship_import_assertion(normalization_run_id, raw_child_xref);
        """,
    ),
    (
        3,
        """
        UPDATE person_name
        SET preferred = 1
        WHERE id IN (
            SELECT MIN(candidate.id)
            FROM person_name candidate
            WHERE NOT EXISTS (
                SELECT 1 FROM person_name chosen
                WHERE chosen.person_id = candidate.person_id
                  AND chosen.preferred = 1
            )
            GROUP BY candidate.person_id
        );

        INSERT INTO person_name(person_id, name_text, name_type, preferred)
        SELECT person.id, person.display_name, 'primary', 1
        FROM canonical_person person
        WHERE NOT EXISTS (
            SELECT 1 FROM person_name name WHERE name.person_id = person.id
        );
        """,
    ),
    (
        4,
        """
        CREATE TABLE publication_release (
            id TEXT PRIMARY KEY,
            normalization_run_id TEXT NOT NULL UNIQUE REFERENCES normalization_run(id),
            created_at TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            rationale TEXT NOT NULL
        );

        CREATE TABLE publication_activation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            release_id TEXT NOT NULL REFERENCES publication_release(id),
            action TEXT NOT NULL CHECK (action IN ('publish', 'rollback')),
            activated_at TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            rationale TEXT NOT NULL
        );

        CREATE TRIGGER immutable_publication_release_update
        BEFORE UPDATE ON publication_release BEGIN
            SELECT RAISE(ABORT, 'publication releases are immutable');
        END;
        CREATE TRIGGER immutable_publication_release_delete
        BEFORE DELETE ON publication_release BEGIN
            SELECT RAISE(ABORT, 'publication releases are immutable');
        END;
        CREATE TRIGGER immutable_publication_activation_update
        BEFORE UPDATE ON publication_activation BEGIN
            SELECT RAISE(ABORT, 'publication activations are append-only');
        END;
        CREATE TRIGGER immutable_publication_activation_delete
        BEFORE DELETE ON publication_activation BEGIN
            SELECT RAISE(ABORT, 'publication activations are append-only');
        END;

        CREATE INDEX publication_activation_latest
            ON publication_activation(id DESC, release_id);
        """,
    ),
    (
        5,
        """
        CREATE TABLE normalization_approval (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
            reviewer TEXT NOT NULL,
            rationale TEXT NOT NULL,
            decided_at TEXT NOT NULL
        );

        CREATE TRIGGER immutable_normalization_approval_update
        BEFORE UPDATE ON normalization_approval BEGIN
            SELECT RAISE(ABORT, 'normalization approvals are append-only');
        END;
        CREATE TRIGGER immutable_normalization_approval_delete
        BEFORE DELETE ON normalization_approval BEGIN
            SELECT RAISE(ABORT, 'normalization approvals are append-only');
        END;

        CREATE INDEX normalization_approval_latest
            ON normalization_approval(normalization_run_id, id DESC);
        """,
    ),
    (
        6,
        """
        ALTER TABLE source ADD COLUMN source_class TEXT NOT NULL DEFAULT 'unknown';
        ALTER TABLE citation ADD COLUMN record_identifier TEXT;
        ALTER TABLE citation ADD COLUMN citation_text TEXT;

        CREATE INDEX source_classification ON source(source_class, source_type);
        CREATE INDEX citation_record_identifier ON citation(record_identifier);
        """,
    ),
    (
        7,
        """
        CREATE TABLE person_citation_assertion (
            normalization_run_id TEXT NOT NULL REFERENCES normalization_run(id),
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            raw_person_xref TEXT NOT NULL,
            citation_id TEXT NOT NULL REFERENCES citation(id),
            PRIMARY KEY (normalization_run_id, person_id, citation_id)
        );

        CREATE INDEX person_citation_person
            ON person_citation_assertion(person_id, normalization_run_id);
        """,
    ),
    (
        8,
        """
        UPDATE source
        SET source_class = CASE
            WHEN source_type = 'family_tree_screenshot' THEN 'submitted_tree'
            WHEN source_type = 'published_family_history' THEN 'derivative'
            ELSE 'record'
        END
        WHERE source_class = 'unknown'
          AND EXISTS (
              SELECT 1
              FROM citation
              JOIN citation_artifact
                ON citation_artifact.citation_id = citation.id
              WHERE citation.source_id = source.id
          );
        """,
    ),
    (
        9,
        """
        CREATE TABLE story (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            body_json TEXT NOT NULL,
            evidence_label TEXT NOT NULL,
            publication_status TEXT NOT NULL DEFAULT 'draft' CHECK (
                publication_status IN ('draft', 'published', 'withdrawn')
            ),
            published_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE story_subject (
            story_id TEXT NOT NULL REFERENCES story(id),
            subject_type TEXT NOT NULL CHECK (
                subject_type IN ('person', 'place', 'surname')
            ),
            subject_key TEXT NOT NULL,
            PRIMARY KEY (story_id, subject_type, subject_key)
        );
        CREATE INDEX story_subject_lookup
            ON story_subject(subject_type, subject_key);
        """,
    ),
    (
        10,
        """
        ALTER TABLE story ADD COLUMN open_questions_json TEXT NOT NULL DEFAULT '[]';
        ALTER TABLE story ADD COLUMN rights_status TEXT NOT NULL DEFAULT 'public-original'
            CHECK (rights_status IN ('public-original', 'licensed', 'restricted'));
        CREATE TABLE story_citation (
            story_id TEXT NOT NULL REFERENCES story(id),
            citation_id TEXT NOT NULL REFERENCES citation(id),
            note TEXT,
            PRIMARY KEY (story_id, citation_id)
        );
        """,
    ),
    (
        11,
        """
        CREATE TABLE person_name_next (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL REFERENCES canonical_person(id),
            name_text TEXT NOT NULL,
            name_type TEXT NOT NULL DEFAULT 'primary' CHECK (
                name_type IN ('primary','birth','married','alias','variant','formal','informal','maiden')
            ),
            preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0,1)),
            UNIQUE(person_id, name_text, name_type)
        );
        INSERT INTO person_name_next SELECT * FROM person_name;
        DROP TABLE person_name;
        ALTER TABLE person_name_next RENAME TO person_name;
        CREATE UNIQUE INDEX one_preferred_person_name ON person_name(person_id) WHERE preferred = 1;
        """,
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def artifact_source_class(artifact_type: str) -> str:
    if artifact_type == "family_tree_screenshot":
        return "submitted_tree"
    if artifact_type == "published_family_history":
        return "derivative"
    return "record"


class EditorialStore:
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
            connection.execute(
                """CREATE TABLE IF NOT EXISTS editorial_schema_migration (
                       version INTEGER PRIMARY KEY,
                       applied_at TEXT NOT NULL
                   )"""
            )
            applied = {
                row[0] for row in connection.execute(
                    "SELECT version FROM editorial_schema_migration"
                )
            }
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO editorial_schema_migration(version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )

    def schema_versions(self):
        with self.session() as connection:
            return [row[0] for row in connection.execute(
                "SELECT version FROM editorial_schema_migration ORDER BY version"
            )]

    def name_forms_for_identifier(self, system, value):
        with self.session() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT n.name_type AS type, n.name_text AS text
                   FROM person_name n JOIN external_identifier e ON e.person_id = n.person_id
                   JOIN canonical_person p ON p.id = n.person_id
                   WHERE e.system = ? AND e.value = ? AND p.privacy_status = 'public'
                     AND n.name_type IN ('formal','informal','married','variant','maiden')
                   ORDER BY n.preferred DESC, n.id""", (system, value))]

    def all_name_forms(self):
        with self.session() as connection:
            rows = connection.execute(
                """SELECT e.value, n.name_type AS type, n.name_text AS text
                   FROM person_name n JOIN external_identifier e ON e.person_id = n.person_id
                   JOIN canonical_person p ON p.id = n.person_id
                   WHERE e.system = 'gedcom_xref' AND p.privacy_status = 'public'
                     AND n.name_type IN ('formal','informal','married','variant','maiden')
                   ORDER BY n.preferred DESC, n.id""").fetchall()
        result = {}
        for row in rows:
            result.setdefault(row['value'], []).append({'type': row['type'], 'text': row['text']})
        return result

    def import_names(self, path, repository=None):
        from .genealogy import GedcomRepository
        repository = repository or GedcomRepository(Path(__file__).resolve().parents[1] / 'data' / 'family-tree.ged')
        curated = {}
        with Path(path).open(encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            if reader.fieldnames != ['gedcom_id', 'name_type', 'name', 'note']:
                raise ValueError('Expected CSV columns: gedcom_id,name_type,name,note')
            for line, row in enumerate(reader, 2):
                person = repository.people.get(row['gedcom_id'])
                if person is None:
                    raise ValueError(f'Line {line}: unknown GEDCOM id')
                if person.is_living or not repository.visible(person):
                    raise ValueError(f'Line {line}: living or private people cannot receive name rows')
                kind, name = row['name_type'].strip(), row['name'].strip()
                if kind not in {'informal', 'married', 'variant', 'maiden'} or not name:
                    raise ValueError(f'Line {line}: invalid name type or empty name')
                curated.setdefault(person.id, []).append({'type': kind, 'text': name})
        count = 0
        with self.session() as connection:
            for person in repository.people.values():
                if person.is_living or not repository.visible(person):
                    continue
                existing = connection.execute(
                    "SELECT person_id FROM external_identifier WHERE system = 'gedcom_xref' AND value = ?",
                    (person.id,)).fetchone()
                person_id = existing['person_id'] if existing else str(uuid.uuid4())
                now = utc_now()
                if not existing:
                    connection.execute(
                        'INSERT INTO canonical_person(id,display_name,privacy_status,created_at,updated_at) VALUES (?,?,?,?,?)',
                        (person_id, person.formal_name, 'public', now, now))
                    connection.execute(
                        "INSERT INTO external_identifier(person_id,system,value,created_at) VALUES (?,'gedcom_xref',?,?)",
                        (person_id, person.id, now))
                else:
                    privacy = connection.execute('SELECT privacy_status FROM canonical_person WHERE id = ?', (person_id,)).fetchone()[0]
                    if privacy != 'public':
                        if person.id in curated:
                            raise ValueError('Curated name resolves to a private canonical person')
                        continue
                # Generate automatic forms from the raw record, never yesterday's aliases.
                from .genealogy import Person
                automatic = Person(person.id, name=person.name).name_forms
                overrides = curated.get(person.id, [])
                types = {row['type'] for row in overrides}
                forms = [row for row in automatic if row['type'] not in types] + overrides
                connection.execute('DELETE FROM person_name WHERE person_id = ?', (person_id,))
                for row in forms:
                    connection.execute(
                        'INSERT OR IGNORE INTO person_name(person_id,name_text,name_type,preferred) VALUES (?,?,?,?)',
                        (person_id, row['text'], row['type'], int(row['type'] == 'formal')))
                    count += 1
        return {'people': len([p for p in repository.people.values() if not p.is_living and repository.visible(p)]),
                'forms': count, 'curated': sum(map(len, curated.values()))}

    def seed_stories(self, stories):
        """Seed or refresh the manifest stories; slugs are stable keys."""
        with self.session() as connection:
            existing = {
                row["slug"]: row["body_json"] for row in connection.execute(
                    "SELECT slug, body_json FROM story"
                ).fetchall()
            }
            now = utc_now()
            for item in stories:
                story_id = f"story:{item['slug']}"
                body = json.dumps(item)
                if item["slug"] in existing:
                    if existing[item["slug"]] == body:
                        continue
                    connection.execute(
                        """UPDATE story SET title = ?, summary = ?, body_json = ?,
                           evidence_label = ?, open_questions_json = ?, updated_at = ?
                           WHERE slug = ?""",
                        (item["title"], item["dek"], body, item["status"],
                         json.dumps(item.get("openQuestions", ())), now, item["slug"]),
                    )
                    connection.execute("DELETE FROM story_subject WHERE story_id = ?", (story_id,))
                else:
                    connection.execute(
                        """INSERT INTO story(
                               id, slug, title, summary, body_json, evidence_label,
                               publication_status, published_at, created_at, updated_at,
                               open_questions_json, rights_status
                           ) VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, 'public-original')""",
                        (story_id, item["slug"], item["title"], item["dek"],
                         body, item["status"], now, now, now,
                         json.dumps(item.get("openQuestions", ()))),
                    )
                for subject_type, keys in (
                    ("person", item.get("people", ())),
                    ("place", item.get("places", ())),
                    ("surname", item.get("surnames", ())),
                ):
                    connection.executemany(
                        "INSERT INTO story_subject(story_id, subject_type, subject_key) VALUES (?, ?, ?)",
                        ((story_id, subject_type, key) for key in keys),
                    )
            return len(stories)

    def published_stories(self):
        with self.session() as connection:
            rows = connection.execute(
                """SELECT body_json FROM story
                   WHERE publication_status = 'published'
                   ORDER BY published_at, slug"""
            ).fetchall()
            return [json.loads(row["body_json"]) for row in rows]

    def import_accession_register(self, register_path):
        register_path = Path(register_path)
        register = json.loads(register_path.read_text(encoding="utf-8"))
        defaults = register["default_rights"]
        provider = register.get("default_provider")
        accessioned_at = register["accession_date"]
        inserted = 0
        unchanged = 0
        representations = 0
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for item in register["artifacts"]:
                existing = connection.execute(
                    "SELECT id, sha256 FROM artifact WHERE artifact_key = ?",
                    (item["artifact_id"],),
                ).fetchone()
                if existing:
                    if existing["sha256"] != item["sha256"]:
                        raise ValueError(
                            f"Artifact {item['artifact_id']} changed checksum; "
                            "accession records are immutable"
                        )
                    artifact_id = existing["id"]
                    unchanged += 1
                else:
                    checksum_owner = connection.execute(
                        "SELECT artifact_key FROM artifact WHERE sha256 = ?",
                        (item["sha256"],),
                    ).fetchone()
                    if checksum_owner:
                        raise ValueError(
                            f"Payload already accessioned as {checksum_owner['artifact_key']}"
                        )
                    artifact_id = str(uuid.uuid4())
                    connection.execute(
                        """INSERT INTO artifact(
                               id, artifact_key, title, artifact_type, sha256, byte_size,
                               original_filename, relative_path, provider, description,
                               review_status, rights_status, access_level, public_display,
                               accessioned_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact_id, item["artifact_id"], item["title"],
                            item["artifact_type"], item["sha256"], item["byte_size"],
                            item["original_filename"],
                            f"originals/{item['artifact_id']}/{item['original_filename']}",
                            provider, item.get("observed"), item["review_status"],
                            defaults["rights_status"], defaults["access_level"],
                            int(defaults["public_display"]), accessioned_at,
                        ),
                    )
                    source_id = str(uuid.uuid4())
                    citation_id = str(uuid.uuid4())
                    connection.execute(
                        """INSERT INTO source(
                               id, title, source_type, provider, created_at,
                               source_class
                           ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            source_id, item["title"], item["artifact_type"],
                            provider, utc_now(),
                            artifact_source_class(item["artifact_type"]),
                        ),
                    )
                    connection.execute(
                        """INSERT INTO citation(
                               id, source_id, locator_raw, verification_status, created_at
                           ) VALUES (?, ?, ?, 'provisional', ?)""",
                        (citation_id, source_id, item.get("observed"), utc_now()),
                    )
                    connection.execute(
                        "INSERT INTO citation_artifact(citation_id, artifact_id) VALUES (?, ?)",
                        (citation_id, artifact_id),
                    )
                    inserted += 1

                subject_types = {
                    "people": "person", "families": "family",
                    "events": "event", "places": "place",
                }
                for subject_type, labels in item.get("subjects", {}).items():
                    singular = subject_types.get(subject_type, subject_type)
                    for label in labels:
                        connection.execute(
                            """INSERT OR IGNORE INTO artifact_subject_label(
                                   artifact_id, subject_type, subject_label
                               ) VALUES (?, ?, ?)""",
                            (artifact_id, singular, label),
                        )
                for alternate in item.get("alternate_files", []):
                    cursor = connection.execute(
                        """INSERT OR IGNORE INTO artifact_representation(
                               artifact_id, filename, relative_path, sha256, byte_size
                           ) VALUES (?, ?, ?, ?, ?)""",
                        (
                            artifact_id, alternate["filename"],
                            f"originals/{item['artifact_id']}/{alternate['filename']}",
                            alternate["sha256"], alternate["byte_size"],
                        ),
                    )
                    representations += cursor.rowcount
        return {
            "batch_id": register["batch_id"],
            "inserted": inserted,
            "unchanged": unchanged,
            "representations_inserted": representations,
            "total": len(register["artifacts"]),
        }

    def ensure_person(self, display_name, privacy_status="unknown", identifiers=None):
        identifiers = identifiers or {}
        with self.session() as connection:
            matches = []
            for system, value in identifiers.items():
                row = connection.execute(
                    """SELECT person_id FROM external_identifier
                       WHERE system = ? AND value = ?""",
                    (system, value),
                ).fetchone()
                if row:
                    matches.append(row["person_id"])
            if len(set(matches)) > 1:
                raise ValueError("External identifiers resolve to different people")
            person_id = matches[0] if matches else str(uuid.uuid4())
            if not matches:
                now = utc_now()
                connection.execute(
                    """INSERT INTO canonical_person(
                           id, display_name, privacy_status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (person_id, display_name, privacy_status, now, now),
                )
                connection.execute(
                    """INSERT INTO person_name(person_id, name_text, preferred)
                       VALUES (?, ?, 1)""",
                    (person_id, display_name),
                )
            for system, value in identifiers.items():
                connection.execute(
                    """INSERT OR IGNORE INTO external_identifier(
                           person_id, system, value, created_at
                       ) VALUES (?, ?, ?, ?)""",
                    (person_id, system, value, utc_now()),
                )
            return person_id

    def resolve_person_label(self, artifact_key, subject_label, person_id):
        with self.session() as connection:
            cursor = connection.execute(
                """UPDATE artifact_subject_label
                   SET resolution_status = 'resolved', canonical_id = ?
                   WHERE artifact_id = (
                       SELECT id FROM artifact WHERE artifact_key = ?
                   ) AND subject_type = 'person' AND subject_label = ?""",
                (person_id, artifact_key, subject_label),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"Person label not found: {artifact_key}/{subject_label}"
                )

    def citation_for_artifact(self, connection, artifact_key):
        row = connection.execute(
            """SELECT citation.id FROM citation
               JOIN citation_artifact ON citation_artifact.citation_id = citation.id
               JOIN artifact ON artifact.id = citation_artifact.artifact_id
               WHERE artifact.artifact_key = ?""",
            (artifact_key,),
        ).fetchone()
        if not row:
            raise ValueError(f"No citation found for artifact {artifact_key}")
        return row["id"]

    def add_claim(
        self, person_id, claim_type, value, *, status="asserted", summary=None,
        artifact_keys=(), qualifier=None, date_start=None, date_end=None,
    ):
        value_json = stable_json(value)
        fingerprint_material = stable_json({
            "person_id": person_id,
            "claim_type": claim_type,
            "value": value,
            "artifacts": sorted(artifact_keys),
        })
        fingerprint = hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()
        with self.session() as connection:
            existing = connection.execute(
                "SELECT id FROM claim WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing:
                return existing["id"]
            claim_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO claim(
                       id, person_id, claim_type, status, summary, fingerprint, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (claim_id, person_id, claim_type, status, summary, fingerprint, utc_now()),
            )
            normalized = value if isinstance(value, str) else None
            connection.execute(
                """INSERT INTO claim_value(
                       claim_id, value_json, normalized_text, date_start, date_end, qualifier
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (claim_id, value_json, normalized, date_start, date_end, qualifier),
            )
            for artifact_key in artifact_keys:
                citation_id = self.citation_for_artifact(connection, artifact_key)
                connection.execute(
                    """INSERT INTO claim_citation(claim_id, citation_id, support_type)
                       VALUES (?, ?, 'supports')""",
                    (claim_id, citation_id),
                )
            return claim_id

    def add_conflict(self, first_claim_id, second_claim_id, explanation):
        ordered = sorted((first_claim_id, second_claim_id))
        with self.session() as connection:
            existing = connection.execute(
                """SELECT id FROM claim_conflict
                   WHERE first_claim_id = ? AND second_claim_id = ?""",
                ordered,
            ).fetchone()
            if existing:
                return existing["id"]
            conflict_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO claim_conflict(
                       id, first_claim_id, second_claim_id, explanation, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (conflict_id, ordered[0], ordered[1], explanation, utc_now()),
            )
            return conflict_id

    def person_summary_for_identifier(self, system, value):
        """Return public-safe editorial metadata; never return artifact paths."""
        with self.session() as connection:
            person = connection.execute(
                """SELECT person.id, person.display_name
                   FROM canonical_person person
                   JOIN external_identifier identifier ON identifier.person_id = person.id
                   WHERE identifier.system = ? AND identifier.value = ?
                     AND person.privacy_status = 'public'""",
                (system, value),
            ).fetchone()
            if not person:
                return None
            active_release = self.current_release(connection)
            active_run_id = (
                active_release["normalization_run_id"] if active_release else ""
            )
            claims = []
            claim_rows = connection.execute(
                """SELECT claim.id, claim.claim_type, claim.status, claim.summary,
                          value.value_json, value.qualifier
                   FROM claim
                   JOIN claim_value value ON value.claim_id = claim.id
                   WHERE claim.person_id = ? AND claim.status <> 'rejected'
                     AND (
                       NOT EXISTS (
                         SELECT 1 FROM imported_claim_assertion imported
                         WHERE imported.claim_id = claim.id
                       ) OR EXISTS (
                         SELECT 1 FROM imported_claim_assertion imported
                         WHERE imported.claim_id = claim.id
                           AND imported.normalization_run_id = ?
                       )
                     )
                   ORDER BY claim.claim_type,
                     CASE claim.status
                       WHEN 'preferred' THEN 0 WHEN 'needs_review' THEN 1 ELSE 2
                     END,
                     claim.created_at""",
                (person["id"], active_run_id),
            ).fetchall()
            for row in claim_rows:
                citations = connection.execute(
                    """SELECT source.title, source.source_class,
                              citation.verification_status,
                              claim_citation.support_type
                       FROM claim_citation
                       JOIN citation ON citation.id = claim_citation.citation_id
                       JOIN source ON source.id = citation.source_id
                       WHERE claim_citation.claim_id = ?
                       ORDER BY source.title""",
                    (row["id"],),
                ).fetchall()
                claims.append({
                    "id": row["id"],
                    "type": row["claim_type"],
                    "label": row["claim_type"].replace("_", " ").title(),
                    "status": row["status"],
                    "statusLabel": {
                        "preferred": "Preferred fact",
                        "needs_review": "Needs review",
                        "asserted": "Imported assertion",
                    }.get(row["status"], row["status"].replace("_", " ").title()),
                    "value": json.loads(row["value_json"]),
                    "qualifier": row["qualifier"],
                    "summary": row["summary"],
                    "citations": [dict(citation) for citation in citations],
                    "evidenceClass": (
                        "record" if any(
                            citation["source_class"] == "record"
                            for citation in citations
                        ) else "submitted_tree" if citations and all(
                            citation["source_class"] == "submitted_tree"
                            for citation in citations
                        ) else "provisional"
                    ),
                })
            visible_claim_ids = {claim["id"] for claim in claims}
            conflicts = [
                {
                    "id": row["id"],
                    "explanation": row["explanation"],
                    "status": row["status"],
                }
                for row in connection.execute(
                """SELECT conflict.id, conflict.explanation, conflict.status,
                          conflict.first_claim_id, conflict.second_claim_id
                   FROM claim_conflict conflict
                   JOIN claim first_claim ON first_claim.id = conflict.first_claim_id
                   JOIN claim second_claim ON second_claim.id = conflict.second_claim_id
                   WHERE first_claim.person_id = ? OR second_claim.person_id = ?
                   ORDER BY conflict.created_at""",
                (person["id"], person["id"]),
                )
                if row["first_claim_id"] in visible_claim_ids
                and row["second_claim_id"] in visible_claim_ids
            ]
            return {
                "personId": person["id"],
                "displayName": person["display_name"],
                "claims": claims,
                "conflicts": conflicts,
            }

    def publish_normalization(self, run_id, reviewer, rationale):
        if not reviewer.strip() or not rationale.strip():
            raise ValueError("A reviewer and rationale are required")
        with self.session() as connection:
            run = connection.execute(
                """SELECT status, publication_status, blocked_reason
                   FROM normalization_run WHERE id = ?""",
                (run_id,),
            ).fetchone()
            if not run:
                raise ValueError("Normalization run not found")
            if run["status"] != "completed" or run["publication_status"] != "ready":
                reason = run["blocked_reason"] or run["status"]
                raise ValueError(f"Normalization run is not publishable: {reason}")
            open_candidates = connection.execute(
                """SELECT COUNT(*) FROM identity_match_candidate
                   WHERE normalization_run_id = ? AND status = 'open'""",
                (run_id,),
            ).fetchone()[0]
            if open_candidates:
                raise ValueError("Normalization run has unresolved identity matches")
            approval = connection.execute(
                """SELECT decision FROM normalization_approval
                   WHERE normalization_run_id = ? ORDER BY id DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if not approval or approval["decision"] != "approved":
                raise ValueError(
                    "Normalization run requires a current explicit approval"
                )
            release = connection.execute(
                "SELECT id FROM publication_release WHERE normalization_run_id = ?",
                (run_id,),
            ).fetchone()
            release_id = release["id"] if release else str(uuid.uuid4())
            if not release:
                connection.execute(
                    """INSERT INTO publication_release(
                           id, normalization_run_id, created_at, reviewer, rationale
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        release_id, run_id, utc_now(), reviewer.strip(),
                        rationale.strip(),
                    ),
                )
            connection.execute(
                """INSERT INTO publication_activation(
                       release_id, action, activated_at, reviewer, rationale
                   ) VALUES (?, 'publish', ?, ?, ?)""",
                (release_id, utc_now(), reviewer.strip(), rationale.strip()),
            )
            return self.current_release(connection)

    def record_normalization_approval(
        self, run_id, decision, reviewer, rationale
    ):
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be approved or rejected")
        if not reviewer.strip() or not rationale.strip():
            raise ValueError("A reviewer and rationale are required")
        with self.session() as connection:
            run = connection.execute(
                "SELECT status FROM normalization_run WHERE id = ?", (run_id,)
            ).fetchone()
            if not run or run["status"] != "completed":
                raise ValueError("Only a completed normalization run can be reviewed")
            cursor = connection.execute(
                """INSERT INTO normalization_approval(
                       normalization_run_id, decision, reviewer, rationale, decided_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    run_id, decision, reviewer.strip(), rationale.strip(), utc_now(),
                ),
            )
            return {
                "id": cursor.lastrowid,
                "normalization_run_id": run_id,
                "decision": decision,
                "reviewer": reviewer.strip(),
                "rationale": rationale.strip(),
            }

    def rollback_to_release(self, release_id, reviewer, rationale):
        if not reviewer.strip() or not rationale.strip():
            raise ValueError("A reviewer and rationale are required")
        with self.session() as connection:
            exists = connection.execute(
                "SELECT 1 FROM publication_release WHERE id = ?", (release_id,)
            ).fetchone()
            if not exists:
                raise ValueError("Publication release not found")
            connection.execute(
                """INSERT INTO publication_activation(
                       release_id, action, activated_at, reviewer, rationale
                   ) VALUES (?, 'rollback', ?, ?, ?)""",
                (release_id, utc_now(), reviewer.strip(), rationale.strip()),
            )
            return self.current_release(connection)

    def current_release(self, connection=None):
        own_connection = connection is None
        connection = connection or self.connect()
        try:
            row = connection.execute(
                """SELECT release.id, release.normalization_run_id,
                          activation.action, activation.activated_at,
                          activation.reviewer, activation.rationale
                   FROM publication_activation activation
                   JOIN publication_release release ON release.id = activation.release_id
                   ORDER BY activation.id DESC LIMIT 1"""
            ).fetchone()
            return dict(row) if row else None
        finally:
            if own_connection:
                connection.close()

    def normalization_report(self, run_id=None):
        with self.session() as connection:
            if run_id:
                run = connection.execute(
                    "SELECT * FROM normalization_run WHERE id = ?", (run_id,)
                ).fetchone()
            else:
                run = connection.execute(
                    """SELECT * FROM normalization_run
                       ORDER BY started_at DESC, id DESC LIMIT 1"""
                ).fetchone()
            if not run:
                return None
            run_id = run["id"]
            match_methods = {
                row["match_method"]: row["count"] for row in connection.execute(
                    """SELECT match_method, COUNT(*) AS count
                       FROM person_import_assertion
                       WHERE normalization_run_id = ? GROUP BY match_method""",
                    (run_id,),
                )
            }
            privacy = {
                row["privacy_status"]: row["count"] for row in connection.execute(
                    """SELECT privacy_status, COUNT(*) AS count
                       FROM person_import_assertion
                       WHERE normalization_run_id = ? GROUP BY privacy_status""",
                    (run_id,),
                )
            }
            claim_status = {
                row["status"]: row["count"] for row in connection.execute(
                    """SELECT claim.status, COUNT(*) AS count
                       FROM imported_claim_assertion imported
                       JOIN claim ON claim.id = imported.claim_id
                       WHERE imported.normalization_run_id = ? GROUP BY claim.status""",
                    (run_id,),
                )
            }
            missing_preferred_names = connection.execute(
                """SELECT COUNT(*) FROM person_import_assertion imported
                   WHERE imported.normalization_run_id = ? AND NOT EXISTS (
                       SELECT 1 FROM person_name name
                       WHERE name.person_id = imported.person_id AND name.preferred = 1
                   )""",
                (run_id,),
            ).fetchone()[0]
            evidence_by_claim = {}
            for row in connection.execute(
                """SELECT imported.claim_id, source.source_class
                   FROM imported_claim_assertion imported
                   JOIN claim_citation link ON link.claim_id = imported.claim_id
                   JOIN citation ON citation.id = link.citation_id
                   JOIN source ON source.id = citation.source_id
                   WHERE imported.normalization_run_id = ?""",
                (run_id,),
            ):
                evidence_by_claim.setdefault(row["claim_id"], set()).add(
                    row["source_class"]
                )
            evidence_classes = {
                "record": 0,
                "submitted_tree": 0,
                "import_only": 0,
                "unknown": 0,
            }
            for classes in evidence_by_claim.values():
                if "record" in classes:
                    evidence_classes["record"] += 1
                elif classes == {"submitted_tree"}:
                    evidence_classes["submitted_tree"] += 1
                elif classes <= {"import_container"}:
                    evidence_classes["import_only"] += 1
                else:
                    evidence_classes["unknown"] += 1
            source_classes = {
                row["source_class"]: row["count"]
                for row in connection.execute(
                    """SELECT source.source_class,
                              COUNT(DISTINCT source.id) AS count
                       FROM imported_claim_assertion imported
                       JOIN claim_citation link ON link.claim_id = imported.claim_id
                       JOIN citation ON citation.id = link.citation_id
                       JOIN source ON source.id = citation.source_id
                       WHERE imported.normalization_run_id = ?
                       GROUP BY source.source_class""",
                    (run_id,),
                )
            }
            return {
                "run": dict(run),
                "match_methods": match_methods,
                "privacy": privacy,
                "imported_claim_status": claim_status,
                "missing_preferred_names": missing_preferred_names,
                "evidence_classes": evidence_classes,
                "source_classes": source_classes,
                "record_citation_count": connection.execute(
                    """SELECT COUNT(DISTINCT link.citation_id)
                       FROM imported_claim_assertion imported
                       JOIN claim_citation link ON link.claim_id = imported.claim_id
                       WHERE imported.normalization_run_id = ?""",
                    (run_id,),
                ).fetchone()[0],
                "person_citation_count": connection.execute(
                    """SELECT COUNT(*) FROM person_citation_assertion
                       WHERE normalization_run_id = ?""",
                    (run_id,),
                ).fetchone()[0],
                "open_identity_candidates": connection.execute(
                    """SELECT COUNT(*) FROM identity_match_candidate
                       WHERE normalization_run_id = ? AND status = 'open'""",
                    (run_id,),
                ).fetchone()[0],
                "current_release": self.current_release(connection),
                "latest_approval": (
                    dict(approval) if (approval := connection.execute(
                        """SELECT decision, reviewer, rationale, decided_at
                           FROM normalization_approval
                           WHERE normalization_run_id = ?
                           ORDER BY id DESC LIMIT 1""",
                        (run_id,),
                    ).fetchone()) else None
                ),
            }

    def compare_normalization_runs(self, base_run_id, target_run_id):
        with self.session() as connection:
            runs = {
                row["id"]: dict(row) for row in connection.execute(
                    """SELECT id, import_id, status, publication_status,
                              people_count, union_count, relationship_count, claim_count
                       FROM normalization_run WHERE id IN (?, ?)""",
                    (base_run_id, target_run_id),
                )
            }
            if base_run_id not in runs or target_run_id not in runs:
                raise ValueError("Both normalization runs must exist")

            def person_map(run_id):
                return {
                    row["person_id"]: {
                        "person_id": row["person_id"],
                        "xref": row["raw_person_xref"],
                        "name": row["raw_name"],
                        "privacy": row["privacy_status"],
                    }
                    for row in connection.execute(
                        """SELECT person_id, raw_person_xref, raw_name, privacy_status
                           FROM person_import_assertion
                           WHERE normalization_run_id = ?""",
                        (run_id,),
                    )
                }

            def claim_set(run_id):
                return {
                    (row["person_id"], row["claim_type"], row["value_json"])
                    for row in connection.execute(
                        """SELECT claim.person_id, claim.claim_type, value.value_json
                           FROM imported_claim_assertion imported
                           JOIN claim ON claim.id = imported.claim_id
                           JOIN claim_value value ON value.claim_id = claim.id
                           WHERE imported.normalization_run_id = ?""",
                        (run_id,),
                    )
                }

            def relationship_set(run_id):
                return {
                    (
                        relationship["parent_id"], relationship["child_id"],
                        relationship["relationship_type"],
                    )
                    for relationship in connection.execute(
                        """SELECT DISTINCT relationship.parent_id,
                                  relationship.child_id,
                                  relationship.relationship_type
                           FROM relationship_import_assertion imported
                           JOIN parent_child_relationship relationship
                             ON relationship.id = imported.relationship_id
                           WHERE imported.normalization_run_id = ?""",
                        (run_id,),
                    )
                }

            base_people = person_map(base_run_id)
            target_people = person_map(target_run_id)
            base_ids, target_ids = set(base_people), set(target_people)
            common_ids = base_ids & target_ids
            privacy_changes = [
                {
                    "person_id": person_id,
                    "name": target_people[person_id]["name"],
                    "before": base_people[person_id]["privacy"],
                    "after": target_people[person_id]["privacy"],
                }
                for person_id in sorted(common_ids)
                if base_people[person_id]["privacy"]
                != target_people[person_id]["privacy"]
            ]

            base_claims, target_claims = claim_set(base_run_id), claim_set(target_run_id)
            removed_claims = base_claims - target_claims
            added_claims = target_claims - base_claims
            changed_keys = {
                (person_id, claim_type)
                for person_id, claim_type, _ in removed_claims
            } & {
                (person_id, claim_type)
                for person_id, claim_type, _ in added_claims
            }
            claim_changes = []
            for person_id, claim_type in sorted(changed_keys):
                before = sorted([
                    json.loads(value) for pid, kind, value in removed_claims
                    if pid == person_id and kind == claim_type
                ], key=stable_json)
                after = sorted([
                    json.loads(value) for pid, kind, value in added_claims
                    if pid == person_id and kind == claim_type
                ], key=stable_json)
                claim_changes.append({
                    "person_id": person_id,
                    "claim_type": claim_type,
                    "before": before,
                    "after": after,
                })
            removed_claims = {
                item for item in removed_claims if item[:2] not in changed_keys
            }
            added_claims = {
                item for item in added_claims if item[:2] not in changed_keys
            }

            base_relationships = relationship_set(base_run_id)
            target_relationships = relationship_set(target_run_id)
            details = {
                "people_added": [target_people[item] for item in sorted(target_ids - base_ids)],
                "people_removed": [base_people[item] for item in sorted(base_ids - target_ids)],
                "people_reused": len(common_ids),
                "privacy_changes": privacy_changes,
                "claims_changed": claim_changes,
                "claims_added": [
                    {"person_id": pid, "claim_type": kind, "value": json.loads(value)}
                    for pid, kind, value in sorted(added_claims)
                ],
                "claims_removed": [
                    {"person_id": pid, "claim_type": kind, "value": json.loads(value)}
                    for pid, kind, value in sorted(removed_claims)
                ],
                "relationships_added": [
                    {"parent_id": parent, "child_id": child, "type": kind}
                    for parent, child, kind in sorted(target_relationships - base_relationships)
                ],
                "relationships_removed": [
                    {"parent_id": parent, "child_id": child, "type": kind}
                    for parent, child, kind in sorted(base_relationships - target_relationships)
                ],
            }
            return {
                "base_run": runs[base_run_id],
                "target_run": runs[target_run_id],
                "summary": {
                    key: len(value) if isinstance(value, list) else value
                    for key, value in details.items()
                },
                "details": details,
            }

    def counts(self):
        tables = (
            "canonical_person", "claim", "claim_conflict", "artifact",
            "artifact_representation", "citation",
        )
        with self.session() as connection:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }
