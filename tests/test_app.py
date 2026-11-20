import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from app import create_app, default_gedcom_path
from app.editorial_store import EditorialStore
from app.genealogy import GedcomRepository, country_for, display_place, tidy_name
from app.site_profile import profile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_GEDCOM = PROJECT_ROOT / "samples" / "example-family.ged"

SAMPLE = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Ada /Halvorsen/
1 BIRT
2 DATE 1 JAN 1840
2 PLAC Voss, Hordaland, Norway
1 DEAT
2 DATE 2 FEB 1910
1 BAPM
2 DATE 10 JAN 1840
2 SOUR @S1@
3 PAGE Parish register, page 4
3 _APID 1,123::456
1 FAMS @F1@
0 @P2@ INDI
1 NAME Bea /Halvorsen/
1 BIRT
2 DATE 1 JAN 1870
2 PLAC Northfield, Rice, Minnesota, USA
1 DEAT
2 DATE 2 FEB 1940
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @P1@
1 CHIL @P2@
0 @S1@ SOUR
1 TITL Voss Parish Register
0 TRLR
"""


NAME_ARTIFACTS = """0 @P1@ INDI
1 NAME Kari /HALVORSEN*/
1 DEAT
2 DATE 1 JAN 1900
0 @P2@ INDI
1 NAME Henry VIII /Tudor/
1 DEAT
2 DATE 1 JAN 1547
0 TRLR
"""

SHOWCASE_SIBLINGS = """0 HEAD
1 CHAR UTF-8
0 @P1@ INDI
1 NAME Michael /Brennan/
1 BIRT
2 DATE 1 JAN 1838
2 PLAC Pittsburgh, Pennsylvania, USA
1 DEAT
2 DATE 1 JAN 1902
2 PLAC Stillwater, Minnesota, USA
1 FAMS @F1@
0 @I13@ INDI
1 NAME Francis /Brennan/
1 BIRT
2 DATE 1 JAN 1874
2 PLAC Stillwater, Minnesota, USA
1 DEAT
2 DATE 1 JAN 1921
2 PLAC Dunedin, Otago, New Zealand
1 FAMC @F1@
0 @P3@ INDI
1 NAME Anne /Brennan/
1 BIRT
2 DATE 1 JAN 1866
2 PLAC Stillwater, Minnesota, USA
1 DEAT
2 DATE 1 JAN 1940
2 PLAC Stillwater, Minnesota, USA
1 FAMC @F1@
0 @P4@ INDI
1 NAME Daniel /Brennan/
1 BIRT
2 DATE 1 JAN 1870
2 PLAC Stillwater, Minnesota, USA
1 DEAT
2 DATE 1 JAN 1928
2 PLAC Minneapolis, Minnesota, USA
1 FAMC @F1@
0 @P5@ INDI
1 NAME Rose /Brennan/
1 BIRT
2 DATE 1 JAN 1872
2 PLAC Stillwater, Minnesota, USA
1 DEAT
2 DATE 1 JAN 1950
2 PLAC Saint Paul, Minnesota, USA
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @P1@
1 CHIL @I13@
1 CHIL @P3@
1 CHIL @P4@
1 CHIL @P5@
0 TRLR
"""

SUBMITTED_TREE_ONLY = """0 @P1@ INDI
1 NAME Ada /Halvorsen/
1 BIRT
2 DATE 1 JAN 1840
3 SOUR @S1@
1 DEAT
2 DATE 1 JAN 1900
0 @S1@ SOUR
1 TITL Ancestry Family Trees
0 TRLR
"""


class FamilyBranchesTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.gedcom = Path(self.temp_dir.name) / "sample.ged"
        self.gedcom.write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_narrative_and_archive_routes_are_public(self):
        editorial_path = Path(self.temp_dir.name) / "narrative.sqlite3"
        gedcom = Path(self.temp_dir.name) / "showcase.ged"
        gedcom.write_text(SHOWCASE_SIBLINGS, encoding="utf-8")
        client = create_app({
            "TESTING": True, "EDITORIAL_DB_PATH": str(editorial_path),
            "GEDCOM_PATH": str(gedcom),
        }).test_client()
        for path in (
            "/stories", "/story/fraser-moe-duluth-1880",
            "/story/francis-brennan-dunedin-1921", "/story/an-age-that-asks-for-doubt",
            "/surnames", "/surnames/brennan", "/timeline", "/records",
            "/search?q=Brennan", "/contribute", "/about",
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
        self.assertIn(b"Needs verification", client.get("/story/an-age-that-asks-for-doubt").data)
        self.assertIn(b"Questions still open", client.get("/story/an-age-that-asks-for-doubt").data)
        homepage = client.get("/").data
        self.assertIn(b"A life in family context", homepage)
        self.assertNotIn(b"an-age-that-asks-for-doubt", homepage)
        self.assertNotIn(b"A recorded lifespan", homepage)
        self.assertNotIn(b"an-age-that-asks-for-doubt", client.get("/stories").data)
        from app.stories import STORY_PERSON_IDS
        self.assertNotIn("I50", STORY_PERSON_IDS)
        self.assertIn(b"Every line carries a different shape", homepage)

    def test_parses_people_families_and_tree(self):
        repo = GedcomRepository(self.gedcom)
        tree = repo.tree("P1")
        self.assertEqual(len(repo.people), 2)
        self.assertEqual(len(repo.families), 1)
        self.assertEqual({node["name"] for node in tree["nodes"]}, {"Ada Halvorsen", "Bea Halvorsen"})
        self.assertEqual(tree["links"][0]["kind"], "parent")
        baptism = repo.people["P1"].event("BAPM")
        self.assertEqual(baptism.citations[0].page, "Parish register, page 4")
        self.assertEqual(repo.evidence_summary(baptism.citations)["label"], "Record-supported")

    def test_name_artifacts_are_cleaned_but_suffixes_survive(self):
        path = Path(self.temp_dir.name) / "names.ged"
        path.write_text(NAME_ARTIFACTS, encoding="utf-8")
        repo = GedcomRepository(path)
        self.assertEqual(repo.people["P1"].clean_name, "Kari Halvorsen")
        self.assertEqual(repo.people["P1"].surname, "Halvorsen")
        self.assertEqual(repo.people["P2"].clean_name, "Henry VIII Tudor")

    def test_submitted_tree_citations_do_not_count_as_documented(self):
        """The exclusion has to match the title Ancestry actually exports."""
        path = Path(self.temp_dir.name) / "evidence.ged"
        path.write_text(SUBMITTED_TREE_ONLY, encoding="utf-8")
        repo = GedcomRepository(path)
        birth = repo.people["P1"].event("BIRT")
        self.assertEqual(repo.evidence_summary(birth.citations)["level"], "tree")

    def test_tree_reports_the_depth_actually_available(self):
        repo = GedcomRepository(self.gedcom)
        deep = repo.tree("P1", "descendants", 9)
        self.assertEqual(deep["availableDepth"], 1)
        self.assertEqual(len(deep["nodes"]), len(repo.tree("P1", "descendants", 1)["nodes"]))

    def test_tree_endpoint_does_not_fall_through_to_opposite_direction(self):
        repo = GedcomRepository(self.gedcom)
        earlier = repo.tree("P1", "ancestors", 9)
        self.assertEqual([node["id"] for node in earlier["nodes"]], ["P1"])
        self.assertEqual(earlier["availableDepth"], 0)
        self.assertEqual([person["id"] for person in earlier["rootConnections"]["later"]], ["P2"])

        later = repo.tree("P2", "descendants", 9)
        self.assertEqual([node["id"] for node in later["nodes"]], ["P2"])
        self.assertEqual([person["id"] for person in later["rootConnections"]["earlier"]], ["P1"])

    def test_living_grandparent_can_be_a_narrow_branch_orientation_point(self):
        # None of these names match the profile's anchors, so branch anchors fall
        # back to the reference person's grandparents.
        path = Path(self.temp_dir.name) / "orientation.ged"
        path.write_text("""0 @P90@ INDI
1 NAME Nora /Halvorsen/
1 BIRT
2 DATE 1 JAN 2000
1 FAMC @F0@
0 @P89@ INDI
1 NAME Erik /Halvorsen/
1 FAMC @F1@
0 @P93@ INDI
1 NAME Karin /Lindqvist/
1 FAMC @F2@
0 @P77@ INDI
1 NAME Olav /Halvorsen/
1 DEAT
2 DATE 1 JAN 2013
0 @P88@ INDI
1 NAME Margit /Brennan/
1 BIRT
2 DATE 1 JAN 1939
0 @P97@ INDI
1 NAME Wilhelm /Lindqvist/
1 DEAT
2 DATE 1 JAN 2001
0 @P96@ INDI
1 NAME Rut /Fraser/
1 DEAT
2 DATE 1 JAN 2002
0 @F0@ FAM
1 HUSB @P89@
1 WIFE @P93@
1 CHIL @P90@
0 @F1@ FAM
1 HUSB @P77@
1 WIFE @P88@
1 CHIL @P89@
0 @F2@ FAM
1 HUSB @P97@
1 WIFE @P96@
1 CHIL @P93@
0 TRLR
""", encoding="utf-8")
        with mock.patch.object(profile, "REFERENCE_PERSON_ID", "P90"):
            repo = GedcomRepository(path)
            branches = repo.starting_branches()
            self.assertEqual([branch["label"] for branch in branches], [
                "Halvorsen branch", "Brennan branch", "Fraser branch", "Lindqvist branch"
            ])
            brennan = next(branch for branch in branches if branch["label"] == "Brennan branch")
            self.assertEqual(brennan["root"]["name"], "Margit Brennan")
            tree = repo.tree(brennan["root"]["id"], "ancestors", 10)
            self.assertEqual(tree["rootPerson"]["name"], "Margit Brennan")
            self.assertFalse(tree["rootRecordAvailable"])

    def test_named_branch_anchors_survive_ancestry_id_changes(self):
        path = Path(self.temp_dir.name) / "new-export-ids.ged"
        path.write_text("""0 @I1@ INDI
1 NAME Arne /Halvorsen/
1 DEAT
2 DATE 1 JAN 2004
0 @I2@ INDI
1 NAME Margaret "Peggy" /Brennan/
1 BIRT
2 DATE 1 JAN 1939
0 @I3@ INDI
1 NAME Walter /Lindqvist/
1 DEAT
2 DATE 1 JAN 1998
0 @I4@ INDI
1 NAME Ruth /Fraser/
1 DEAT
2 DATE 1 JAN 2016
0 TRLR
""", encoding="utf-8")
        repo = GedcomRepository(path)
        self.assertEqual(repo.default_root().clean_name, "Arne Halvorsen")
        self.assertEqual([branch["label"] for branch in repo.starting_branches()], [
            "Halvorsen branch", "Brennan branch", "Fraser branch", "Lindqvist branch"
        ])
        brennan = next(branch for branch in repo.starting_branches()
                       if branch["label"] == "Brennan branch")
        self.assertEqual(brennan["root"]["name"], "Peggy Brennan")

    def test_people_index_lists_every_public_relative(self):
        index = GedcomRepository(self.gedcom).people_index()
        self.assertEqual(index["total"], 2)
        self.assertEqual([group["surname"] for group in index["groups"]], ["Halvorsen"])
        ada = index["groups"][0]["people"][0]
        self.assertEqual(ada["geography"], "Voss, Norway")
        self.assertIn("relationship", ada)

    def test_flagged_people_get_a_small_research_review_indicator(self):
        path = Path(self.temp_dir.name) / "flagged.ged"
        path.write_text("""0 @P1@ INDI
1 NAME Early /Parent/
1 BIRT
2 DATE 1 JAN 1800
1 DEAT
2 DATE 1 JAN 1810
1 FAMS @F1@
0 @P2@ INDI
1 NAME Later /Child/
1 BIRT
2 DATE 1 JAN 1820
1 DEAT
2 DATE 1 JAN 1890
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @P1@
1 CHIL @P2@
0 TRLR
""", encoding="utf-8")
        repo = GedcomRepository(path)
        self.assertTrue(repo.person_summary(repo.people["P1"])["researchReview"])
        self.assertTrue(repo.person_summary(repo.people["P2"])["researchReview"])

        app = create_app({"GEDCOM_PATH": str(path), "TESTING": True})
        client = app.test_client()
        self.assertIn(b"Research review", client.get("/people").data)
        self.assertIn(b"Research review", client.get("/people/P2").data)
        tree = client.get("/api/tree?root=P2").get_json()
        self.assertTrue(all(person["researchReview"] for person in tree["nodes"]))
        with client.get("/static/js/explore.js") as script:
            self.assertIn(b"node-research-review", script.data)

    def test_surname_search_has_somewhere_to_land(self):
        """The search hint offers surnames, so surnames must resolve to a group."""
        repo = GedcomRepository(self.gedcom)
        rows = repo.search("hal")
        surnames = [row for row in rows if row["kind"] == "surname"]
        self.assertEqual([row["name"] for row in surnames], ["Halvorsen"])
        self.assertEqual(surnames[0]["slug"], "halvorsen")
        self.assertTrue(all(row["kind"] == "person"
                            for row in repo.search("hal", include_surnames=False)))

        app = create_app({"GEDCOM_PATH": str(self.gedcom), "SHOW_LIVING": False, "TESTING": True})
        page = app.test_client().get("/people")
        self.assertIn(b'id="surname-halvorsen"', page.data)

    def test_branch_distance_names_its_anchor(self):
        context = GedcomRepository(self.gedcom).branch_context("P2")
        if context:
            self.assertIn(context["anchor"], context["distance"])

    def test_people_index_and_missing_pages_are_navigable(self):
        app = create_app({"GEDCOM_PATH": str(self.gedcom), "SHOW_LIVING": False, "TESTING": True})
        client = app.test_client()
        listing = client.get("/people")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Ada Halvorsen", listing.data)
        missing = client.get("/people/DOES-NOT-EXIST")
        self.assertEqual(missing.status_code, 404)
        self.assertIn(profile.SITE["name"].encode(), missing.data)

    def test_living_people_are_not_searchable(self):
        path = Path(self.temp_dir.name) / "living.ged"
        path.write_text("0 @P1@ INDI\n1 NAME Private /Halvorsen/\n1 BIRT\n2 DATE 1 JAN 2000\n", encoding="utf-8")
        self.assertEqual(GedcomRepository(path).search("Private"), [])

    def test_missing_death_is_historical_at_age_100(self):
        path = Path(self.temp_dir.name) / "historical.ged"
        birth_year = date.today().year - 100
        path.write_text(f"0 @P1@ INDI\n1 NAME Older /Halvorsen/\n1 BIRT\n2 DATE 1 JAN {birth_year}\n", encoding="utf-8")
        matches = GedcomRepository(path).search("Older")
        self.assertEqual(matches[0]["name"], "Older Halvorsen")

    def test_missing_death_stays_private_under_age_100(self):
        path = Path(self.temp_dir.name) / "private-under-100.ged"
        birth_year = date.today().year - 99
        path.write_text(f"0 @P1@ INDI\n1 NAME Younger /Halvorsen/\n1 BIRT\n2 DATE 1 JAN {birth_year}\n", encoding="utf-8")
        self.assertEqual(GedcomRepository(path).search("Younger"), [])

    def test_health_and_api(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom)})
        client = app.test_client()
        self.assertTrue(client.get("/health").get_json()["ok"])
        tree = client.get("/api/tree?root=P1")
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.get_json()["rootPerson"]["name"], "Ada Halvorsen")
        geography = client.get("/api/geography")
        self.assertEqual(geography.status_code, 200)
        self.assertEqual(set(geography.get_json()), {"origins", "gateways", "homesteads"})
        self.assertTrue(all(stage["anecdote"] for stage in geography.get_json().values()))
        self.assertNotIn("familyStreams", geography.get_json()["origins"])
        self.assertIn("familyStreams", geography.get_json()["gateways"])
        self.assertTrue(all(
            "familyBranches" in item
            for item in geography.get_json()["origins"]["items"]
        ))
        self.assertTrue(all(
            stream["branch"] and stream["familyNames"]
            for stream in geography.get_json()["gateways"]["familyStreams"]
        ))
        self.assertIn("highlights", geography.get_json()["gateways"])
        self.assertEqual(geography.get_json()["gateways"]["highlights"], [])
        self.assertEqual(client.get("/concepts").status_code, 404)

    def test_web_fundamentals_are_public_and_privacy_aware(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom),
                          "SITE_URL": "https://family.example"})
        client = app.test_client()

        homepage = client.get("/")
        self.assertIn(b'<link rel="canonical" href="https://family.example/">', homepage.data)
        self.assertIn(b'property="og:image"', homepage.data)
        self.assertIn(b'application/ld+json', homepage.data)

        favicon = client.get("/favicon.ico")
        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon.mimetype, "image/vnd.microsoft.icon")
        favicon.close()

        manifest = client.get("/site.webmanifest").get_json()
        self.assertEqual(manifest["name"], profile.SITE["name"])

        robots = client.get("/robots.txt")
        self.assertIn(b"Disallow: /api/", robots.data)
        self.assertIn(b"https://family.example/sitemap.xml", robots.data)

        sitemap = client.get("/sitemap.xml")
        self.assertEqual(sitemap.status_code, 200)
        self.assertIn(b"https://family.example/people/P1", sitemap.data)
        self.assertIn(b"https://family.example/places/voss-norway", sitemap.data)

        missing = client.get("/missing-page")
        self.assertIn(b'<meta name="robots" content="noindex, follow">', missing.data)

    def test_person_and_place_pages(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom)})
        client = app.test_client()
        person = client.get("/people/P1")
        self.assertEqual(person.status_code, 200)
        self.assertIn(b"Voss Parish Register", person.data)
        places = client.get("/places")
        self.assertEqual(places.status_code, 200)
        self.assertIn(b"Three chapters of place", places.data)
        place = client.get("/places/voss-norway")
        self.assertEqual(place.status_code, 200)
        self.assertIn(b"Ada Halvorsen", place.data)

    def test_person_page_overlays_safe_editorial_claims(self):
        database = Path(self.temp_dir.name) / "editorial.sqlite3"
        store = EditorialStore(database)
        person_id = store.ensure_person(
            "Ada Halvorsen", "public", {"gedcom_xref": "P1"}
        )
        store.add_claim(
            person_id, "birth_date", "1840-01-01", status="preferred",
            summary="Reviewed independently.",
        )
        app = create_app({
            "TESTING": True,
            "GEDCOM_PATH": str(self.gedcom),
            "EDITORIAL_DB_PATH": str(database),
        })
        response = app.test_client().get("/people/P1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"What the reviewed evidence says", response.data)
        self.assertIn(b"1840-01-01", response.data)
        self.assertIn(b"Provisional evidence", response.data)
        self.assertNotIn(b"research_archive", response.data)

    def test_place_hierarchy_preserves_every_mapped_community(self):
        repo = GedcomRepository(self.gedcom)
        hierarchy = repo.place_hierarchy()
        nested_count = sum(region["communityCount"] for geography in hierarchy for region in geography["regions"])
        self.assertEqual(nested_count, len(repo.places()))
        self.assertTrue(all(geography["preface"] for geography in hierarchy))
        self.assertTrue(all(geography["familySummary"] for geography in hierarchy))
        self.assertTrue(all(region["familySummary"] for geography in hierarchy for region in geography["regions"]))
        self.assertTrue(all(region["familyNames"] for geography in hierarchy for region in geography["regions"]))

    def test_branch_context_uses_family_graph_not_target_surname(self):
        path = Path(self.temp_dir.name) / "branches.ged"
        path.write_text("""0 @P90@ INDI
1 NAME Reference /Halvorsen/
1 FAMC @F21@
0 @P89@ INDI
1 NAME Parent /Halvorsen/
0 @P93@ INDI
1 NAME Parent /Lindqvist/
1 FAMC @F30@
0 @P97@ INDI
1 NAME Grandparent /Lindqvist/
0 @P96@ INDI
1 NAME Rut /Fraser/
1 FAMC @F31@
0 @P508@ INDI
1 NAME John /Ross/
1 DEAT
2 DATE 1860
0 @F21@ FAM
1 HUSB @P89@
1 WIFE @P93@
1 CHIL @P90@
0 @F30@ FAM
1 HUSB @P97@
1 WIFE @P96@
1 CHIL @P93@
0 @F31@ FAM
1 HUSB @P508@
1 CHIL @P96@
0 TRLR
""", encoding="utf-8")
        with mock.patch.object(profile, "REFERENCE_PERSON_ID", "P90"):
            context = GedcomRepository(path).branch_context("P508")
            self.assertEqual(context["label"], "Fraser branch")
            self.assertEqual(context["trail"], "Fraser → Ross")
            self.assertEqual(
                GedcomRepository(path).anchor_relationship("P508"),
                "Rut Fraser's parent",
            )

    def test_homepage_guides_people_into_tree_and_full_timeline(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom)})
        response = app.test_client().get("/")
        self.assertIn(b"Search a name, a nickname or a surname", response.data)
        self.assertIn(b"Browse all", response.data)
        self.assertNotIn(b'class="home-welcome"', response.data)
        self.assertIn(b'id="family-map"', response.data)
        self.assertIn(b'action="/search" method="get"', response.data)
        self.assertIn(b'name="q"', response.data)
        self.assertIn(b'<noscript>', response.data)
        self.assertNotIn(b'Loading family geography', response.data)
        self.assertEqual(response.data.count(b'<h1 '), 1)
        self.assertIn(b'id="stage-anecdote"', response.data)
        self.assertIn(b"The streams cross", response.data)
        self.assertIn(b"Main family streams", response.data)
        self.assertNotIn(b"Immigration paths", response.data)
        self.assertNotIn(b"home-entry-rail", response.data)
        self.assertIn(b'href="/records"', response.data)
        self.assertNotIn(b"CHOOSE YOUR WAY IN", response.data)
        self.assertIn(b"The earliest named generation", response.data)
        self.assertNotIn(b"A CONVERGENCE", response.data)
        html = response.get_data(as_text=True)
        self.assertLess(html.index('id="heritage-map-canvas"'), html.index('class="home-story-panel"'))
        self.assertLess(html.index('id="heritage-map-canvas"'), html.index('class="home-stats"'))
        panel_start = html.index('class="home-story-panel"')
        panel_end = html.index("</aside>", panel_start)
        controls = html.index('class="home-map-controls"')
        self.assertLess(panel_start, controls)
        self.assertLess(controls, panel_end)
        self.assertLess(html.index('data-stage="origins"'), html.index('data-stage="gateways"'))
        self.assertLess(html.index('data-stage="gateways"'), html.index('data-stage="homesteads"'))

    def test_import_display_corrections_preserve_raw_places(self):
        repo = GedcomRepository(self.gedcom)
        event = repo.people['P1'].event('BIRT')
        event.place = 'Voss, Norge'
        detail = repo.person_detail('P1')
        self.assertEqual(detail['birthPlace'], 'Voss, Norway')
        self.assertEqual(detail['events'][0]['place'], 'Voss, Norway')
        self.assertEqual(event.place, 'Voss, Norge')
        self.assertEqual(display_place('St. Paul, Minnesota, USA'), 'Saint Paul, Minnesota, USA')
        with mock.patch.object(profile, "NAME_CORRECTIONS", ((r"\bHalvorson\b", "Halvorsen"),)):
            self.assertEqual(tidy_name('Ole Halvorson'), 'Ole Halvorsen')

    def test_movement_requires_two_known_countries(self):
        repo = GedcomRepository(self.gedcom)
        repo.people['P1'].event('BIRT').place = 'Unknown village'
        repo.people['P1'].event('DEAT').place = 'Minnesota, USA'
        self.assertEqual(repo.branch_character_cards(minimum_people=1)[0]['movementPercent'], 0)
        repo.people['P1'].event('BIRT').place = 'Cork, Ireland'
        repo.people['P1'].event('DEAT').place = 'Dunedin, New Zealand'
        self.assertEqual(country_for('Dunedin, New Zealand'), 'New Zealand')
        self.assertEqual(repo.branch_character_cards(minimum_people=1)[0]['movementPercent'], 50)

    def test_tree_explorer_uses_plain_language_controls(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom)})
        response = app.test_client().get("/explore")
        self.assertIn(b"Family direction", response.data)
        self.assertIn(b"<strong>Earlier</strong>", response.data)
        self.assertIn(b"<strong>Later</strong>", response.data)
        self.assertIn(b"Close family", response.data)
        self.assertIn(b"Whole branch", response.data)
        self.assertIn(b"Starting with", response.data)
        self.assertNotIn(b'type="range"', response.data)
        self.assertIn(b'id="tree-depth"', response.data)
        self.assertNotIn(b"data-depth", response.data)
        self.assertIn(b'id="branch-start"', response.data)
        self.assertIn(b"Fitted overview", response.data)
        self.assertIn(b"Back in the tree", response.data)
        self.assertIn(b"tree-continuation", response.data)
        self.assertIn(b'id="mobile-control-toggle"', response.data)
        self.assertIn(b'id="tree-controls-body"', response.data)

    def test_tokens_and_shared_components_wrap_page_styles(self):
        app = create_app({"TESTING": True, "GEDCOM_PATH": str(self.gedcom)})
        html = app.test_client().get("/explore").get_data(as_text=True)
        self.assertLess(html.index("css/tokens.css"), html.index("css/explore.css"))
        self.assertLess(html.index("css/components.css"), html.index("css/explore.css"))


class ExampleProfileTests(unittest.TestCase):
    """The bundled fictional tree and profile work together out of the box."""

    def test_default_gedcom_falls_back_to_the_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(default_gedcom_path(Path(directory)),
                             Path(directory) / "samples" / "example-family.ged")

    def test_sample_tree_tells_the_two_stream_story(self):
        repo = GedcomRepository(EXAMPLE_GEDCOM)
        self.assertEqual(repo.default_root().clean_name, "Arne Halvorsen")
        self.assertEqual(len(repo.starting_branches()), len(profile.BRANCH_ANCHORS))
        merge = repo.convergence()
        self.assertEqual(len(merge["marriages"]), 3)
        self.assertGreater(merge["descendants"], 0)
        self.assertTrue(repo.research_review("I50"))
        self.assertTrue(all(not repo.visible(repo.people[pid]) for pid in ("I41", "I42", "I43", "I90")))
        geography = repo.geography_stages()
        self.assertTrue(geography["origins"]["items"])
        self.assertTrue(geography["homesteads"]["items"])
        self.assertTrue(geography["gateways"]["familyStreams"])
        self.assertEqual(
            [item["title"] for item in repo.outlier_feed()],
            ["The sibling whose life ended in New Zealand"],
        )

    def test_every_page_renders_against_the_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            client = create_app({
                "TESTING": True, "GEDCOM_PATH": str(EXAMPLE_GEDCOM),
                "EDITORIAL_DB_PATH": str(Path(directory) / "editorial.sqlite3"),
            }).test_client()
            for path in ("/", "/explore", "/people", "/places", "/stories", "/timeline",
                         "/records", "/surnames", "/about", "/people/I36",
                         "/places/duluth-minnesota", "/story/fraser-moe-duluth-1880"):
                self.assertEqual(client.get(path).status_code, 200, path)
            homepage = client.get("/").get_data(as_text=True)
            self.assertIn("3 weddings between 1880 and 1915", homepage)
            self.assertIn('class="stream-slot-1">Halvorsen<', homepage)
            self.assertNotIn("Nora Halvorsen", client.get("/people").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
