import tempfile
import unittest
from pathlib import Path

from app.editorial_store import EditorialStore
from app.import_store import ImportStore
from app.normalization import CanonicalNormalizer


FIRST = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Ada /Halvorsen/
1 SEX F
1 BIRT
2 DATE 1 JAN 1840
2 PLAC Voss, Hordaland, Norway
1 DEAT
2 DATE 2 FEB 1910
1 FAMS @F1@
0 @P2@ INDI
1 NAME Bea /Halvorsen/
1 SEX F
1 BIRT
2 DATE 1 JAN 1870
2 PLAC Northfield, Minnesota
1 DEAT
2 DATE 2 FEB 1940
1 FAMC @F1@
0 @F1@ FAM
1 WIFE @P1@
1 CHIL @P2@
0 TRLR
"""


CHANGED_IDS = FIRST.replace("@P1@", "@I100@").replace("@P2@", "@I200@").replace(
    "@F1@", "@F900@"
)

CHANGED_FACT = FIRST.replace("2 DATE 1 JAN 1840", "2 DATE 2 JAN 1840")

INVALID = """0 @P1@ INDI
1 NAME Reversed /Example/
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1800
0 TRLR
"""

SOURCE_AWARE = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Ada /Halvorsen/
1 SOUR @S1@
2 PAGE Profile-level tree citation
1 BIRT
2 DATE 1 JAN 1840
2 PLAC Voss, Hordaland, Norway
2 SOUR @S1@
3 PAGE Ancestry tree profile
3 _APID tree:123
2 SOUR @S2@
3 PAGE Year: 1850; Census Place: Example County; Page: 4
3 _APID 1,8054::456
1 DEAT
2 DATE 2 FEB 1910
0 @S1@ SOUR
1 TITL Ancestry Family Trees
0 @S2@ SOUR
1 TITL 1850 United States Federal Census
1 AUTH National Archives
0 TRLR
"""


class CanonicalNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = root / "imports.sqlite3"
        self.gedcom = root / "first.ged"
        self.gedcom.write_text(FIRST, encoding="utf-8")
        self.import_store = ImportStore(self.database)
        self.editorial_store = EditorialStore(self.database)
        self.normalizer = CanonicalNormalizer(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalization_is_idempotent_and_keeps_provenance(self):
        staged = self.import_store.stage(self.gedcom)
        first = self.normalizer.normalize(staged["id"], self.gedcom)
        second = self.normalizer.normalize(staged["id"], self.gedcom)
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["people_count"], 2)
        self.assertEqual(first["union_count"], 1)
        self.assertEqual(first["relationship_count"], 1)
        self.assertEqual(first["publication_status"], "ready")
        with self.editorial_store.session() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM person_import_assertion"
            ).fetchone()[0], 2)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM imported_claim_assertion"
            ).fetchone()[0], first["claim_count"])
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM person_name WHERE preferred = 1"
            ).fetchone()[0], 2)
        unpublished = self.editorial_store.person_summary_for_identifier(
            "gedcom_xref", "P1"
        )
        self.assertEqual(unpublished["claims"], [])
        with self.assertRaisesRegex(ValueError, "explicit approval"):
            self.editorial_store.publish_normalization(
                first["id"], "Test Reviewer", "Not approved yet"
            )
        self.editorial_store.record_normalization_approval(
            first["id"], "approved", "Test Reviewer", "Validated fixture diff"
        )
        release = self.editorial_store.publish_normalization(
            first["id"], "Test Reviewer", "Validated fixture"
        )
        self.assertEqual(release["normalization_run_id"], first["id"])
        summary = self.editorial_store.person_summary_for_identifier(
            "gedcom_xref", "P1"
        )
        self.assertTrue(summary["claims"])

    def test_changed_xrefs_reuse_unique_identity_signatures(self):
        first_import = self.import_store.stage(self.gedcom)
        first_result = self.normalizer.normalize(first_import["id"], self.gedcom)
        changed = Path(self.temp_dir.name) / "changed.ged"
        changed.write_text(CHANGED_IDS, encoding="utf-8")
        second_import = self.import_store.stage(changed)
        result = self.normalizer.normalize(second_import["id"], changed)
        self.assertEqual(result["people_count"], 2)
        with self.editorial_store.session() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM canonical_person"
            ).fetchone()[0], 2)
            methods = [row[0] for row in connection.execute(
                """SELECT match_method FROM person_import_assertion
                   WHERE normalization_run_id = ? ORDER BY raw_person_xref""",
                (result["id"],),
            )]
            self.assertEqual(methods, ["identity_signature", "identity_signature"])
        difference = self.editorial_store.compare_normalization_runs(
            first_result["id"], result["id"]
        )
        self.assertEqual(difference["summary"]["people_reused"], 2)
        self.assertTrue(all(
            count == 0 for key, count in difference["summary"].items()
            if key != "people_reused"
        ))
        self.editorial_store.record_normalization_approval(
            first_result["id"], "approved", "Test Reviewer", "First diff reviewed"
        )
        self.editorial_store.record_normalization_approval(
            result["id"], "approved", "Test Reviewer", "Second diff reviewed"
        )
        first_release = self.editorial_store.publish_normalization(
            first_result["id"], "Test Reviewer", "First fixture release"
        )
        second_release = self.editorial_store.publish_normalization(
            result["id"], "Test Reviewer", "Second fixture release"
        )
        self.assertNotEqual(first_release["id"], second_release["id"])
        rolled_back = self.editorial_store.rollback_to_release(
            first_release["id"], "Test Reviewer", "Regression rollback"
        )
        self.assertEqual(rolled_back["id"], first_release["id"])
        self.assertEqual(rolled_back["action"], "rollback")

    def test_curated_claim_survives_imported_assertions(self):
        person_id = self.editorial_store.ensure_person(
            "Ada Halvorsen", "public", {"gedcom_xref": "P1"}
        )
        curated = self.editorial_store.add_claim(
            person_id, "birth_date", "1840-01-01", status="preferred"
        )
        staged = self.import_store.stage(self.gedcom)
        self.normalizer.normalize(staged["id"], self.gedcom)
        with self.editorial_store.session() as connection:
            status = connection.execute(
                "SELECT status FROM claim WHERE id = ?", (curated,)
            ).fetchone()[0]
            self.assertEqual(status, "preferred")
            self.assertGreater(connection.execute(
                "SELECT COUNT(*) FROM claim WHERE person_id = ?", (person_id,)
            ).fetchone()[0], 1)

    def test_semantic_diff_reports_a_changed_fact(self):
        first_import = self.import_store.stage(self.gedcom)
        first = self.normalizer.normalize(first_import["id"], self.gedcom)
        changed = Path(self.temp_dir.name) / "changed-fact.ged"
        changed.write_text(CHANGED_FACT, encoding="utf-8")
        second_import = self.import_store.stage(changed)
        second = self.normalizer.normalize(second_import["id"], changed)
        difference = self.editorial_store.compare_normalization_runs(
            first["id"], second["id"]
        )
        self.assertEqual(difference["summary"]["people_reused"], 2)
        self.assertEqual(difference["summary"]["claims_changed"], 1)
        changed_claim = difference["details"]["claims_changed"][0]
        self.assertEqual(changed_claim["claim_type"], "birth_date")
        self.assertEqual(changed_claim["before"][0]["raw"], "1 JAN 1840")
        self.assertEqual(changed_claim["after"][0]["raw"], "2 JAN 1840")

    def test_validation_errors_block_canonical_publication(self):
        invalid = Path(self.temp_dir.name) / "invalid.ged"
        invalid.write_text(INVALID, encoding="utf-8")
        staged = self.import_store.stage(invalid)
        result = self.normalizer.normalize(staged["id"], invalid)
        self.assertEqual(result["publication_status"], "blocked")
        with self.assertRaisesRegex(ValueError, "not publishable"):
            self.editorial_store.publish_normalization(
                result["id"], "Test Reviewer", "Should remain blocked"
            )

    def test_record_level_citations_and_source_classes_are_preserved(self):
        source_aware = Path(self.temp_dir.name) / "source-aware.ged"
        source_aware.write_text(SOURCE_AWARE, encoding="utf-8")
        staged = self.import_store.stage(source_aware)
        result = self.normalizer.normalize(staged["id"], source_aware)
        with self.editorial_store.session() as connection:
            rows = connection.execute(
                """SELECT source.title, source.source_class,
                          citation.locator_raw, citation.record_identifier
                   FROM imported_claim_assertion imported
                   JOIN claim ON claim.id = imported.claim_id
                   JOIN claim_citation link ON link.claim_id = claim.id
                   JOIN citation ON citation.id = link.citation_id
                   JOIN source ON source.id = citation.source_id
                   WHERE imported.normalization_run_id = ?
                     AND claim.claim_type = 'birth_date'
                   ORDER BY source.title""",
                (result["id"],),
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["source_class"] for row in rows}, {"record", "submitted_tree"}
        )
        census = next(row for row in rows if row["source_class"] == "record")
        self.assertIn("Census Place", census["locator_raw"])
        self.assertEqual(census["record_identifier"], "1,8054::456")
        with self.editorial_store.session() as connection:
            self.assertEqual(connection.execute(
                """SELECT COUNT(*) FROM person_citation_assertion
                   WHERE normalization_run_id = ?""",
                (result["id"],),
            ).fetchone()[0], 1)
        self.editorial_store.record_normalization_approval(
            result["id"], "approved", "Test Reviewer", "Sources reviewed"
        )
        self.editorial_store.publish_normalization(
            result["id"], "Test Reviewer", "Publish fixture"
        )
        summary = self.editorial_store.person_summary_for_identifier(
            "gedcom_xref", "P1"
        )
        birth = next(claim for claim in summary["claims"]
                     if claim["type"] == "birth_date")
        self.assertEqual(birth["evidenceClass"], "record")


if __name__ == "__main__":
    unittest.main()
