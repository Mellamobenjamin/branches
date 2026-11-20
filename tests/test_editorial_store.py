import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.editorial_store import EditorialStore, artifact_source_class


class EditorialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = root / "editorial.sqlite3"
        self.register = root / "register.json"
        self.register.write_text(json.dumps({
            "register_version": 1,
            "accession_date": "2026-08-30",
            "batch_id": "TEST-BATCH",
            "default_provider": "Ancestry",
            "default_rights": {
                "rights_status": "ancestry-research-copy",
                "access_level": "private",
                "public_display": False,
            },
            "artifacts": [{
                "artifact_id": "ARC-TEST-0001",
                "original_filename": "record.jpg",
                "sha256": "a" * 64,
                "byte_size": 10,
                "title": "Test record",
                "artifact_type": "test",
                "subjects": {"people": ["Ada Halvorsen"], "families": ["Halvorsen"]},
                "observed": "A test observation.",
                "review_status": "needs_review",
                "alternate_files": [{
                    "filename": "record-small.jpg",
                    "sha256": "b" * 64,
                    "byte_size": 5,
                }],
            }],
        }), encoding="utf-8")
        self.store = EditorialStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migrations_are_versioned_and_idempotent(self):
        self.assertEqual(self.store.schema_versions(), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])

    def test_stories_are_seeded_and_refreshed_by_slug(self):
        stories = [{
            "slug": "test-story", "title": "A test story", "dek": "Summary",
            "status": "Tree evidence", "sections": [], "people": ["P1"],
            "places": ["minnesota"], "surnames": ["halvorsen"],
            "openQuestions": ["What does the record say?"],
        }]
        self.assertEqual(self.store.seed_stories(stories), 1)
        self.assertEqual(self.store.seed_stories(stories), 1)
        self.assertEqual(self.store.published_stories()[0]["slug"], "test-story")
        with self.store.session() as connection:
            subjects = connection.execute(
                "SELECT subject_type FROM story_subject ORDER BY subject_type"
            ).fetchall()
        self.assertEqual([row[0] for row in subjects], ["person", "place", "surname"])
        with self.store.session() as connection:
            row = connection.execute(
                "SELECT open_questions_json, rights_status FROM story"
            ).fetchone()
        self.assertEqual(json.loads(row["open_questions_json"]), ["What does the record say?"])
        self.assertEqual(row["rights_status"], "public-original")
        stories[0]["openQuestions"] = ["Which register confirms this?"]
        stories[0]["people"] = ["P2"]
        self.assertEqual(self.store.seed_stories(stories), 1)
        self.assertEqual(self.store.published_stories()[0]["openQuestions"],
                         ["Which register confirms this?"])
        with self.store.session() as connection:
            subjects = connection.execute(
                "SELECT subject_key FROM story_subject WHERE subject_type = 'person'"
            ).fetchall()
        self.assertEqual([row[0] for row in subjects], ["P2"])

    def test_artifact_source_classes_do_not_overstate_derivative_evidence(self):
        self.assertEqual(artifact_source_class("death_certificate"), "record")
        self.assertEqual(
            artifact_source_class("family_tree_screenshot"), "submitted_tree"
        )
        self.assertEqual(
            artifact_source_class("published_family_history"), "derivative"
        )
        EditorialStore(self.database)
        self.assertEqual(self.store.schema_versions(), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])

    def test_register_import_is_private_and_idempotent(self):
        first = self.store.import_accession_register(self.register)
        second = self.store.import_accession_register(self.register)
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(first["representations_inserted"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(self.store.counts()["artifact"], 1)
        with self.store.session() as connection:
            artifact = connection.execute("SELECT * FROM artifact").fetchone()
            self.assertEqual(artifact["access_level"], "private")
            self.assertEqual(artifact["public_display"], 0)
            labels = connection.execute(
                "SELECT subject_type FROM artifact_subject_label ORDER BY subject_type"
            ).fetchall()
            self.assertEqual([row[0] for row in labels], ["family", "person"])
            source = connection.execute("SELECT source_class FROM source").fetchone()
            self.assertEqual(source["source_class"], "record")

    def test_ancestry_copy_cannot_be_marked_for_public_display(self):
        self.store.import_accession_register(self.register)
        with self.store.session() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """UPDATE artifact SET public_display = 1,
                           access_level = 'public-display'"""
                )

    def test_competing_claims_are_preserved_as_a_conflict(self):
        self.store.import_accession_register(self.register)
        person_id = self.store.ensure_person(
            "Ada Halvorsen", "public", {"gedcom_xref": "P1"}
        )
        first = self.store.add_claim(
            person_id, "birth_date", "1840-01-01", status="asserted"
        )
        second = self.store.add_claim(
            person_id, "birth_date", "1841-01-01", status="needs_review",
            artifact_keys=("ARC-TEST-0001",),
        )
        conflict = self.store.add_conflict(first, second, "Dates disagree")
        self.assertTrue(conflict)
        self.assertEqual(self.store.counts()["claim"], 2)
        self.assertEqual(self.store.counts()["claim_conflict"], 1)
        summary = self.store.person_summary_for_identifier("gedcom_xref", "P1")
        self.assertEqual(len(summary["claims"]), 2)
        self.assertEqual(len(summary["conflicts"]), 1)
        self.assertNotIn("relative_path", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
