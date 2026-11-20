import tempfile
import unittest
from pathlib import Path

from app.genealogy import GedcomRepository, parse_gedcom_date
from app.validation import validate_repository


INVALID_SAMPLE = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Parent /Example/
1 SEX F
1 BIRT
2 DATE 1800
1 DEAT
2 DATE 1830
1 FAMS @F1@
0 @P2@ INDI
1 NAME Child /Example/
1 BIRT
2 DATE 1840
1 DEAT
2 DATE 1950
1 FAMC @F1@
1 FAMC @F2@
0 @P3@ INDI
1 NAME Child. /Example/
1 BIRT
2 DATE 1840
1 DEAT
2 DATE 1950
0 @F1@ FAM
1 WIFE @P1@
1 CHIL @P2@
0 @F2@ FAM
1 CHIL @P2@
0 TRLR
"""


VALID_SAMPLE = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Parent /Example/
1 SEX F
1 BIRT
2 DATE 1800
1 DEAT
2 DATE 1880
1 FAMS @F1@
0 @P2@ INDI
1 NAME Child /Example/
1 BIRT
2 DATE 1830
1 DEAT
2 DATE 1900
1 FAMC @F1@
0 @F1@ FAM
1 WIFE @P1@
1 CHIL @P2@
0 TRLR
"""


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def repository(self, contents):
        path = Path(self.temp_dir.name) / "tree.ged"
        path.write_text(contents, encoding="utf-8")
        return GedcomRepository(path, show_living=True)

    def test_valid_tree_passes_publication_gate(self):
        report = validate_repository(self.repository(VALID_SAMPLE))
        self.assertTrue(report.publishable)
        self.assertEqual(report.counts["error"], 0)
        self.assertEqual(report.metrics["maximum_stated_lifespan"], 80)

    def test_impossible_chronology_blocks_publication(self):
        report = validate_repository(self.repository(INVALID_SAMPLE))
        codes = [finding.code for finding in report.findings]
        self.assertFalse(report.publishable)
        self.assertIn("BIRTH_AFTER_PARENT_DEATH", codes)
        self.assertIn("LIFESPAN_OVER_105", codes)

    def test_multiple_parent_families_are_not_silently_ignored(self):
        report = validate_repository(self.repository(INVALID_SAMPLE))
        finding = next(f for f in report.findings if f.code == "MULTIPLE_PARENT_FAMILIES")
        self.assertEqual(finding.people, ("P2",))
        self.assertEqual(finding.families, ("F1", "F2"))

    def test_punctuation_insensitive_duplicate_candidate(self):
        report = validate_repository(self.repository(INVALID_SAMPLE))
        finding = next(f for f in report.findings if f.code == "PROBABLE_DUPLICATE_PERSON")
        self.assertEqual(set(finding.people), {"P2", "P3"})

    def test_report_has_json_and_markdown_forms(self):
        report = validate_repository(self.repository(INVALID_SAMPLE))
        self.assertIn('"publishable": false', report.to_json())
        markdown = report.to_markdown("Test Audit")
        self.assertIn("# Test Audit", markdown)
        self.assertIn("**Publication gate:** BLOCKED", markdown)
        self.assertIn("BIRTH_AFTER_PARENT_DEATH", markdown)

    def test_gedcom_date_qualifiers_and_ranges_are_preserved(self):
        between = parse_gedcom_date("BET 1840 AND 1845")
        self.assertEqual((between.qualifier, between.start_year, between.end_year, between.precision),
                         ("BET", 1840, 1845, "range"))
        before = parse_gedcom_date("BEF 1900")
        self.assertEqual((before.qualifier, before.start_year, before.end_year),
                         ("BEF", None, 1899))
        self.assertEqual(before.year, 1900)
        after = parse_gedcom_date("AFT 1900")
        self.assertEqual((after.qualifier, after.start_year, after.end_year),
                         ("AFT", 1901, None))
        self.assertEqual(after.year, 1900)

    def test_parent_family_qualifiers_are_parsed_losslessly(self):
        repo = self.repository("""0 @P1@ INDI
1 NAME Child /Example/
1 FAMC @F1@
2 PEDI birth
2 STAT proven
1 FAMC @F2@
2 PEDI adopted
0 @F1@ FAM
1 CHIL @P1@
0 @F2@ FAM
1 CHIL @P1@
0 TRLR
""")
        person = repo.people["P1"]
        self.assertEqual(person.child_families, ["F1", "F2"])
        self.assertEqual(person.child_family, "F2")
        self.assertEqual(
            [(link.pedigree, link.status) for link in person.parent_family_links],
            [("birth", "proven"), ("adopted", "")],
        )


if __name__ == "__main__":
    unittest.main()
