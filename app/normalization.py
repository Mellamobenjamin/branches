"""Normalize an immutable GEDCOM import into canonical editorial staging."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid

from .editorial_store import EditorialStore, stable_json, utc_now
from .genealogy import GedcomRepository, is_user_tree_source, normalized_name
from .import_store import ImportStore


NORMALIZER_VERSION = 3

EVENT_CLAIM_NAMES = {
    "BIRT": "birth",
    "DEAT": "death",
    "BURI": "burial",
    "RESI": "residence",
    "IMMI": "immigration",
    "EMIG": "emigration",
    "BAPM": "baptism",
    "EVEN": "event",
    "ARRIVAL": "arrival",
    "DEPARTURE": "departure",
}


def person_identity_signature(person) -> str:
    birth = person.event("BIRT")
    death = person.event("DEAT")
    birth_date = birth.date_value if birth else None
    death_date = death.date_value if death else None
    material = {
        "name": normalized_name(person.clean_name),
        "birth": [
            birth_date.start_year if birth_date else None,
            birth_date.end_year if birth_date else None,
        ],
        "death": [
            death_date.start_year if death_date else None,
            death_date.end_year if death_date else None,
        ],
    }
    return hashlib.sha256(stable_json(material).encode("utf-8")).hexdigest()


def pedigree_type(value: str) -> str:
    normalized = (value or "").strip().casefold()
    return {
        "birth": "biological",
        "biological": "biological",
        "adopted": "adoptive",
        "adoptive": "adoptive",
        "step": "step",
        "foster": "foster",
        "guardian": "guardian",
    }.get(normalized, "unknown")


class CanonicalNormalizer:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.import_store = ImportStore(self.database_path)
        self.editorial_store = EditorialStore(self.database_path)

    def _run_result(self, connection, run_id, *, reused=False):
        row = connection.execute(
            "SELECT * FROM normalization_run WHERE id = ?", (run_id,)
        ).fetchone()
        result = dict(row)
        result["reused"] = reused
        result["identity_candidate_count"] = connection.execute(
            """SELECT COUNT(*) FROM identity_match_candidate
               WHERE normalization_run_id = ? AND status = 'open'""",
            (run_id,),
        ).fetchone()[0]
        result["finding_count"] = connection.execute(
            "SELECT COUNT(*) FROM normalization_finding WHERE normalization_run_id = ?",
            (run_id,),
        ).fetchone()[0]
        return result

    def normalize(self, import_id, gedcom_path):
        gedcom_path = Path(gedcom_path)
        staged = self.import_store.get(import_id)
        if not staged:
            raise ValueError(f"Import not found: {import_id}")
        payload = gedcom_path.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        if checksum != staged["sha256"]:
            raise ValueError("GEDCOM checksum does not match the immutable import")

        with self.editorial_store.session() as connection:
            existing = connection.execute(
                """SELECT id, status FROM normalization_run
                   WHERE import_id = ? AND normalizer_version = ?""",
                (import_id, NORMALIZER_VERSION),
            ).fetchone()
            if existing:
                return self._run_result(connection, existing["id"], reused=True)
            run_id = str(uuid.uuid4())
            blocked_reason = None
            publication_status = "ready"
            if not staged["publishable"]:
                publication_status = "blocked"
                blocked_reason = (
                    f"Validation gate: {staged['fatal_count']} fatal, "
                    f"{staged['error_count']} error, and "
                    f"{staged['unresolved_warning_count']} unresolved warning findings."
                )
            connection.execute(
                """INSERT INTO normalization_run(
                       id, import_id, normalizer_version, started_at, status,
                       publication_status, blocked_reason
                   ) VALUES (?, ?, ?, ?, 'running', ?, ?)""",
                (
                    run_id, import_id, NORMALIZER_VERSION, utc_now(),
                    publication_status, blocked_reason,
                ),
            )

        repository = GedcomRepository(gedcom_path, show_living=True)
        try:
            self._normalize_repository(run_id, import_id, staged, repository)
        except Exception:
            with self.editorial_store.session() as connection:
                connection.execute(
                    """UPDATE normalization_run
                       SET status = 'failed', completed_at = ? WHERE id = ?""",
                    (utc_now(), run_id),
                )
            raise
        with self.editorial_store.session() as connection:
            return self._run_result(connection, run_id)

    @staticmethod
    def _deterministic_id(kind, *parts):
        material = ":".join(("family-branches", kind, *parts))
        return str(uuid.uuid5(uuid.NAMESPACE_URL, material))

    def _match_person(self, connection, run_id, import_id, person, signature):
        exact = connection.execute(
            """SELECT person_id FROM external_identifier
               WHERE system = 'gedcom_xref' AND value = ?""",
            (person.id,),
        ).fetchone()
        if exact:
            return exact["person_id"], "external_identifier", []

        prior = connection.execute(
            """SELECT DISTINCT observation.person_id
               FROM person_identity_observation observation
               JOIN normalization_run run ON run.id = observation.normalization_run_id
               WHERE observation.identity_signature = ?
                 AND observation.normalization_run_id <> ?
                 AND run.status = 'completed'""",
            (signature, run_id),
        ).fetchall()
        candidate_ids = [row["person_id"] for row in prior]
        if len(candidate_ids) == 1:
            return candidate_ids[0], "identity_signature", []

        person_id = str(uuid.uuid4())
        method = "ambiguous_new" if candidate_ids else "new"
        return person_id, method, candidate_ids

    def _normalize_repository(self, run_id, import_id, staged, repository):
        people_by_xref = {}
        claim_count = 0
        with self.editorial_store.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source_id = self._deterministic_id("gedcom-source", import_id)
            citation_id = self._deterministic_id("gedcom-citation", import_id)
            connection.execute(
                """INSERT OR IGNORE INTO source(
                       id, title, source_type, provider, created_at, source_class
                   ) VALUES (?, ?, 'gedcom_import', 'GEDCOM', ?, 'import_container')""",
                (source_id, f"GEDCOM import: {staged['original_filename']}", utc_now()),
            )
            connection.execute(
                """INSERT OR IGNORE INTO citation(
                       id, source_id, locator_raw, verification_status, created_at
                   ) VALUES (?, ?, ?, 'provisional', ?)""",
                (
                    citation_id, source_id,
                    f"Immutable import {import_id}; SHA-256 {staged['sha256']}",
                    utc_now(),
                ),
            )

            for raw_source in repository.sources.values():
                classified = (
                    "submitted_tree" if is_user_tree_source(raw_source.title)
                    else "record" if raw_source.title else "unknown"
                )
                source_type = (
                    "submitted_family_tree"
                    if classified == "submitted_tree" else "gedcom_source"
                )
                connection.execute(
                    """INSERT OR IGNORE INTO source(
                           id, title, source_type, creator, publisher, provider,
                           created_at, source_class
                       ) VALUES (?, ?, ?, ?, ?, 'GEDCOM', ?, ?)""",
                    (
                        self._deterministic_id(
                            "gedcom-source-definition", import_id, raw_source.id
                        ),
                        raw_source.title or f"GEDCOM source {raw_source.id}",
                        source_type, raw_source.author or None,
                        raw_source.publication or None, utc_now(), classified,
                    ),
                )

            for person in sorted(repository.people.values(), key=lambda item: item.id):
                signature = person_identity_signature(person)
                person_id, method, candidates = self._match_person(
                    connection, run_id, import_id, person, signature
                )
                privacy = "living" if person.is_living else "public"
                existing_person = connection.execute(
                    "SELECT privacy_status FROM canonical_person WHERE id = ?",
                    (person_id,),
                ).fetchone()
                if not existing_person:
                    now = utc_now()
                    connection.execute(
                        """INSERT INTO canonical_person(
                               id, display_name, privacy_status, created_at, updated_at
                           ) VALUES (?, ?, ?, ?, ?)""",
                        (person_id, person.clean_name, privacy, now, now),
                    )
                    preferred_name = 1
                else:
                    connection.execute(
                        """UPDATE canonical_person SET display_name = ?,
                               privacy_status = CASE
                                 WHEN privacy_status IN ('living', 'private') THEN privacy_status
                                 ELSE ?
                               END,
                               updated_at = ? WHERE id = ?""",
                        (person.clean_name, privacy, utc_now(), person_id),
                    )
                    preferred_name = 0
                connection.execute(
                    """INSERT OR IGNORE INTO person_name(
                           person_id, name_text, name_type, preferred
                       ) VALUES (?, ?, 'primary', ?)""",
                    (person_id, person.clean_name, preferred_name),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO external_identifier(
                           person_id, system, value, import_id, created_at
                       ) VALUES (?, 'gedcom_xref', ?, ?, ?)""",
                    (person_id, person.id, import_id, utc_now()),
                )
                connection.execute(
                    """INSERT INTO person_import_assertion(
                           normalization_run_id, raw_person_xref, person_id,
                           match_method, identity_signature, raw_name, privacy_status
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id, person.id, person_id, method, signature,
                        person.name, privacy,
                    ),
                )
                birth = person.event("BIRT")
                death = person.event("DEAT")
                birth_date = birth.date_value if birth else None
                death_date = death.date_value if death else None
                connection.execute(
                    """INSERT INTO person_identity_observation(
                           normalization_run_id, person_id, raw_person_xref,
                           identity_signature, normalized_name, birth_start_year,
                           birth_end_year, death_start_year, death_end_year
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id, person_id, person.id, signature,
                        normalized_name(person.clean_name),
                        birth_date.start_year if birth_date else None,
                        birth_date.end_year if birth_date else None,
                        death_date.start_year if death_date else None,
                        death_date.end_year if death_date else None,
                    ),
                )
                for candidate_id in candidates:
                    connection.execute(
                        """INSERT INTO identity_match_candidate(
                               normalization_run_id, raw_person_xref,
                               candidate_person_id, match_reason, score
                           ) VALUES (?, ?, ?, 'exact identity signature shared by multiple prior people', 1.0)""",
                        (run_id, person.id, candidate_id),
                    )
                if candidates and method == "ambiguous_new":
                    connection.execute(
                        """INSERT INTO normalization_finding(
                               normalization_run_id, code, severity, raw_xref,
                               message, values_json
                           ) VALUES (?, 'IDENTITY_MATCH_AMBIGUOUS', 'warning', ?, ?, ?)""",
                        (
                            run_id, person.id,
                            f"{person.clean_name} matches multiple prior canonical people.",
                            stable_json({"candidate_person_ids": candidates}),
                        ),
                    )
                people_by_xref[person.id] = person_id
                claim_count += self._import_person_claims(
                    connection, run_id, import_id, person_id, person,
                    repository, citation_id
                )

            union_count = self._import_unions(
                connection, run_id, repository, people_by_xref
            )
            relationship_count = self._import_relationships(
                connection, run_id, import_id, repository, people_by_xref
            )
            open_candidates = connection.execute(
                """SELECT COUNT(*) FROM identity_match_candidate
                   WHERE normalization_run_id = ? AND status = 'open'""",
                (run_id,),
            ).fetchone()[0]
            if open_candidates:
                connection.execute(
                    """UPDATE normalization_run SET publication_status = 'blocked',
                           blocked_reason = COALESCE(blocked_reason || ' ', '') || ?
                       WHERE id = ?""",
                    (f"{open_candidates} identity matches require review.", run_id),
                )
            connection.execute(
                """UPDATE normalization_run
                   SET status = 'completed', completed_at = ?, people_count = ?,
                       union_count = ?, relationship_count = ?, claim_count = ?
                   WHERE id = ?""",
                (
                    utc_now(), len(repository.people), union_count,
                    relationship_count, claim_count, run_id,
                ),
            )

    def _insert_imported_claim(
        self, connection, run_id, import_id, person_id, raw_xref,
        event_ordinal, field_name, claim_type, value, citation_ids,
        *, normalized_text=None, date_start=None, date_end=None, qualifier=None,
    ):
        value_json = stable_json(value)
        fingerprint = hashlib.sha256(stable_json({
            "import_id": import_id,
            "raw_xref": raw_xref,
            "event_ordinal": event_ordinal,
            "field": field_name,
            "value": value,
            "normalizer_version": NORMALIZER_VERSION,
        }).encode("utf-8")).hexdigest()
        claim_id = self._deterministic_id("imported-claim", fingerprint)
        connection.execute(
            """INSERT INTO claim(
                   id, person_id, claim_type, status, summary, fingerprint, created_at
               ) VALUES (?, ?, ?, 'asserted', ?, ?, ?)""",
            (
                claim_id, person_id, claim_type,
                f"Imported assertion from GEDCOM record {raw_xref}.",
                fingerprint, utc_now(),
            ),
        )
        connection.execute(
            """INSERT INTO claim_value(
                   claim_id, value_json, normalized_text, date_start, date_end, qualifier
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (claim_id, value_json, normalized_text, date_start, date_end, qualifier),
        )
        for citation_id in citation_ids:
            connection.execute(
                """INSERT INTO claim_citation(claim_id, citation_id, support_type)
                   VALUES (?, ?, 'supports')""",
                (claim_id, citation_id),
            )
        connection.execute(
            """INSERT INTO imported_claim_assertion(
                   normalization_run_id, claim_id, raw_person_xref,
                   event_ordinal, field_name
               ) VALUES (?, ?, ?, ?, ?)""",
            (run_id, claim_id, raw_xref, event_ordinal, field_name),
        )

    def _import_person_claims(
        self, connection, run_id, import_id, person_id, person, repository,
        fallback_citation_id
    ):
        count = 0
        person_citations = self._citation_ids(
            connection, import_id, f"person:{person.id}", person.citations,
            repository, fallback_citation_id,
        )
        if person.citations:
            for citation_id in person_citations:
                connection.execute(
                    """INSERT INTO person_citation_assertion(
                           normalization_run_id, person_id, raw_person_xref,
                           citation_id
                       ) VALUES (?, ?, ?, ?)""",
                    (run_id, person_id, person.id, citation_id),
                )
        if person.sex:
            self._insert_imported_claim(
                connection, run_id, import_id, person_id, person.id,
                None, "sex", "sex", person.sex, [fallback_citation_id],
                normalized_text=person.sex,
            )
            count += 1
        for ordinal, event in enumerate(person.events):
            prefix = EVENT_CLAIM_NAMES.get(event.kind, event.kind.casefold())
            event_citations = self._citation_ids(
                connection, import_id, f"person:{person.id}:event:{ordinal}",
                event.citations, repository, fallback_citation_id,
            )
            if event.date:
                date_value = event.date_value
                value = {
                    "raw": date_value.raw,
                    "qualifier": date_value.qualifier,
                    "start_year": date_value.start_year,
                    "end_year": date_value.end_year,
                    "precision": date_value.precision,
                }
                self._insert_imported_claim(
                    connection, run_id, import_id, person_id, person.id,
                    ordinal, "date", f"{prefix}_date", value, event_citations,
                    normalized_text=date_value.raw,
                    date_start=str(date_value.start_year) if date_value.start_year else None,
                    date_end=str(date_value.end_year) if date_value.end_year else None,
                    qualifier=date_value.qualifier,
                )
                count += 1
            if event.place:
                self._insert_imported_claim(
                    connection, run_id, import_id, person_id, person.id,
                    ordinal, "place", f"{prefix}_place", event.place, event_citations,
                    normalized_text=event.place,
                )
                count += 1
        return count

    def _citation_ids(
        self, connection, import_id, scope, citations, repository,
        fallback_citation_id,
    ):
        if not citations:
            return [fallback_citation_id]
        result = []
        for ordinal, raw_citation in enumerate(citations):
            raw_source_id = raw_citation.source_id or "UNRESOLVED"
            source_id = self._deterministic_id(
                "gedcom-source-definition", import_id, raw_source_id
            )
            source = repository.sources.get(raw_source_id)
            if not connection.execute(
                "SELECT 1 FROM source WHERE id = ?", (source_id,)
            ).fetchone():
                connection.execute(
                    """INSERT INTO source(
                           id, title, source_type, provider, created_at, source_class
                       ) VALUES (?, ?, 'unresolved_gedcom_source', 'GEDCOM', ?, 'unknown')""",
                    (
                        source_id,
                        source.title if source else f"Unresolved GEDCOM source {raw_source_id}",
                        utc_now(),
                    ),
                )
            citation_material = stable_json({
                "scope": scope,
                "ordinal": ordinal,
                "source_id": raw_source_id,
                "page": raw_citation.page,
                "apid": raw_citation.apid,
                "text": raw_citation.text,
            })
            citation_id = self._deterministic_id(
                "gedcom-record-citation", import_id, citation_material
            )
            connection.execute(
                """INSERT OR IGNORE INTO citation(
                       id, source_id, locator_raw, verification_status, created_at,
                       record_identifier, citation_text
                   ) VALUES (?, ?, ?, 'provisional', ?, ?, ?)""",
                (
                    citation_id, source_id, raw_citation.page or None, utc_now(),
                    raw_citation.apid or None, raw_citation.text or None,
                ),
            )
            result.append(citation_id)
        return result

    def _import_unions(self, connection, run_id, repository, people_by_xref):
        count = 0
        for family in sorted(repository.families.values(), key=lambda item: item.id):
            existing = connection.execute(
                """SELECT union_id FROM family_union_identifier
                   WHERE system = 'gedcom_family_xref' AND value = ?""",
                (family.id,),
            ).fetchone()
            if existing:
                union_id = existing["union_id"]
                method = "external_identifier"
            else:
                union_id = str(uuid.uuid4())
                method = "new"
                union_type = "marriage" if any(
                    event.kind == "MARR" for event in family.events
                ) else "unknown"
                connection.execute(
                    """INSERT INTO family_union(
                           id, union_type, status, created_at
                       ) VALUES (?, ?, 'asserted', ?)""",
                    (union_id, union_type, utc_now()),
                )
                connection.execute(
                    """INSERT INTO family_union_identifier(
                           union_id, system, value, normalization_run_id
                       ) VALUES (?, 'gedcom_family_xref', ?, ?)""",
                    (union_id, family.id, run_id),
                )
            for role, raw_partner in (
                ("husband", family.husband), ("wife", family.wife)
            ):
                if raw_partner in people_by_xref:
                    connection.execute(
                        """INSERT OR IGNORE INTO union_partner(
                               union_id, person_id, role
                           ) VALUES (?, ?, ?)""",
                        (union_id, people_by_xref[raw_partner], role),
                    )
            connection.execute(
                """INSERT INTO union_import_assertion(
                       normalization_run_id, raw_family_xref, union_id, match_method
                   ) VALUES (?, ?, ?, ?)""",
                (run_id, family.id, union_id, method),
            )
            count += 1
        return count

    def _import_relationships(
        self, connection, run_id, import_id, repository, people_by_xref
    ):
        assertions = {}
        for child in repository.people.values():
            for link in child.parent_family_links:
                assertions[(child.id, link.family_id)] = link
        for family in repository.families.values():
            for child_xref in family.children:
                assertions.setdefault((child_xref, family.id), None)

        count = 0
        for (child_xref, family_xref), link in sorted(assertions.items()):
            family = repository.families.get(family_xref)
            child_id = people_by_xref.get(child_xref)
            if not family or not child_id:
                continue
            relationship_type = pedigree_type(link.pedigree if link else "")
            for parent_xref in (family.husband, family.wife):
                parent_id = people_by_xref.get(parent_xref)
                if not parent_id:
                    continue
                existing = connection.execute(
                    """SELECT id FROM parent_child_relationship
                       WHERE parent_id = ? AND child_id = ?
                         AND relationship_type = ? AND status <> 'rejected'
                       ORDER BY created_at LIMIT 1""",
                    (parent_id, child_id, relationship_type),
                ).fetchone()
                if existing:
                    relationship_id = existing["id"]
                else:
                    relationship_id = str(uuid.uuid4())
                    connection.execute(
                        """INSERT INTO parent_child_relationship(
                               id, parent_id, child_id, relationship_type, status,
                               confidence, source_import_id, created_at
                           ) VALUES (?, ?, ?, ?, 'asserted', 'unknown', ?, ?)""",
                        (
                            relationship_id, parent_id, child_id,
                            relationship_type, import_id, utc_now(),
                        ),
                    )
                connection.execute(
                    """INSERT INTO relationship_import_assertion(
                           normalization_run_id, relationship_id, raw_family_xref,
                           raw_parent_xref, raw_child_xref, pedigree, pedigree_status
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id, relationship_id, family_xref, parent_xref,
                        child_xref, link.pedigree if link else "",
                        link.status if link else "",
                    ),
                )
                count += 1
        return count
