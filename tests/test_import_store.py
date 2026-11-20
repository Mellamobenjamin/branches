import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.import_store import ImportStore


SAMPLE = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Ada /Halvorsen/
1 BIRT
2 DATE 1840
1 DEAT
2 DATE 1910
0 TRLR
"""

WARNING_ONLY = """0 @P1@ INDI
1 NAME Long /Example/
1 BIRT
2 DATE 1800
1 DEAT
2 DATE 1910
0 TRLR
"""


class ImportStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.gedcom = root / "sample.ged"
        self.database = root / "imports.sqlite3"
        self.gedcom.write_text(SAMPLE, encoding="utf-8")
        self.store = ImportStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_stages_payload_records_and_validation_once(self):
        first = self.store.stage(self.gedcom)
        second = self.store.stage(self.gedcom)
        self.assertTrue(first["inserted"])
        self.assertTrue(first["validation_inserted"])
        self.assertFalse(second["inserted"])
        self.assertFalse(second["validation_inserted"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["people_count"], 1)
        self.assertEqual(first["record_count"], 3)
        self.assertTrue(first["publishable"])
        self.assertEqual(len(self.store.list_imports()), 1)

    def test_import_rows_are_immutable(self):
        staged = self.store.stage(self.gedcom)
        with self.store.session() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE import_batch SET original_filename = 'changed.ged' WHERE id = ?",
                    (staged["id"],),
                )

    def test_warning_requires_append_only_review_decision(self):
        self.gedcom.write_text(WARNING_ONLY, encoding="utf-8")
        staged = self.store.stage(self.gedcom)
        self.assertFalse(staged["publishable"])
        self.assertEqual(staged["unresolved_warning_count"], 1)
        finding = self.store.review_queue(staged["id"])[0]
        reviewed = self.store.record_decision(
            staged["id"], finding["fingerprint"], "accepted",
            "Identity continuity is supported by reviewed records.", "Test Reviewer",
        )
        self.assertTrue(reviewed["publishable"])
        self.assertEqual(reviewed["unresolved_warning_count"], 0)

    def test_error_cannot_be_waived(self):
        self.gedcom.write_text("""0 @P1@ INDI
1 NAME Reversed /Example/
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1800
0 TRLR
""", encoding="utf-8")
        staged = self.store.stage(self.gedcom)
        finding = self.store.review_queue(staged["id"])[0]
        with self.assertRaisesRegex(ValueError, "cannot be waived"):
            self.store.record_decision(
                staged["id"], finding["fingerprint"], "accepted",
                "Trying to waive an error.", "Test Reviewer",
            )


if __name__ == "__main__":
    unittest.main()
