"""Example site profile: a fictional family for demonstration and tests.

Every person, story and record in this profile and in
``samples/example-family.ged`` is invented. The places are real so the maps
have somewhere to land.

To build a site for a real family, copy this file to ``app/profiles/<name>.py``
(it will be ignored by Git), edit the values, and start the app with
``BRANCHES_PROFILE=<name>``.
"""

# ---------------------------------------------------------------------------
# Site identity and page copy
# ---------------------------------------------------------------------------

SITE = {
    "name": "Halvorsen Branches",
    # The brand mark renders the second word in italics.
    "brand_first": "Halvorsen",
    "brand_second": "Branches",
    "tagline": "A family history project",
    "url": "https://example.org",
    "description": "Explore Halvorsen Branches, a privacy-aware family history connecting relatives, places, records, and family lines across generations.",
    "home_title": "Halvorsen Branches: a family tree and migration atlas",
    "home_description": "Explore the Halvorsen family tree through an interactive atlas of family streams, origins, American footholds, Minnesota communities, people, and records.",
    "share_alt": "Halvorsen Branches, a living family atlas",
    "family_label": "the Halvorsen family",
    "about": (
        "Halvorsen Branches is a family atlas built from a family tree its maintainers keep in a genealogy service, with independent records added as they are found. It is public so that relatives from every branch can find their own people; living relatives are kept off the public site by default.",
        "Two streams of family crossed the Atlantic generations apart. Irish and Scottish lines reached Pennsylvania in the 1700s; Norwegian and Swedish lines came to the Upper Midwest in the 1800s. They ran side by side until {weddings} weddings between {first_year} and {last_year} joined them, and {descendants} relatives now descend from both.",
    ),
    "stories_lede": "Close readings of the public tree: the first wedding between the two streams, a brother who left for New Zealand, and a date that deserves doubt.",
    "places_description": "Browse the places connected to the Halvorsen family, from European origins and American footholds to generations of Minnesota communities.",
    "explore_map_heading": "Many origins. A Minnesota center of gravity.",
}

HOME = {
    "positioning": "Two streams of family crossed the Atlantic generations apart and did not meet until {weddings} weddings between {first_year} and {last_year}. This atlas follows them.",
    "positioning_fallback": "Two streams of family crossed the Atlantic generations apart. This atlas follows them.",
    "intro_summary": "Explore the family connections across the Atlantic, from northern Europe and the British Isles to Minnesota.",
    "anecdote": "Two families left Europe generations apart: one from Scandinavia, one from Ireland and Scotland. Their descendants did not meet until {first_year}.",
    "anecdote_fallback": "Every place on this map opens a different part of the family story.",
    "convergence_body": "For more than a century the Scandinavian and Irish-Scottish lines in this tree run in parallel and never touch: different countries, different centuries, no shared descendants. Between {first_year} and {last_year}, {weddings} marriages join them, and {descendants} relatives now descend from both sides. Each row names the two lines that met, how far back each is traced, and the branch it becomes today.",
}

# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

# The people each public branch is named after, usually the four grandparents of
# the present generation. Names are matched against the GEDCOM name (including
# any quoted nickname), so they survive an export that renumbers every ID.
BRANCH_ANCHORS = (
    "Arne Halvorsen",
    'Margaret "Peggy" Brennan',
    "Walter Lindqvist",
    "Ruth Fraser",
)

# The branch listed first and used as the default starting point.
PRIMARY_SURNAME = "Halvorsen"

# Optional: the GEDCOM ID of the person the anchors are grandparents of. Used
# only as a fallback when none of the named anchors are found.
REFERENCE_PERSON_ID = "I90"

# Where each branch's tributaries gather before crossing the ocean on the home
# map, as [lat, lng], in the same order as BRANCH_ANCHORS.
BRANCH_MAP_JUNCTIONS = ([55, -22], [51, -24], [58, -18], [48, -20])

# ---------------------------------------------------------------------------
# Migration streams
# ---------------------------------------------------------------------------

# Two ancestral streams, identified by birth country. The site looks for the
# marriages where the streams first join and counts who descends from both.
STREAMS = (
    {"key": "nordic", "label": "Scandinavian", "countries": ("Norway", "Sweden")},
    {"key": "gaelic", "label": "Irish and Scottish", "countries": ("Ireland", "Scotland")},
)

# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------

HOME_COUNTRY = "United States"

# The region the family settled in. ``term`` is matched against raw place text;
# ``label`` must equal the GAZETTEER label for a statewide-only entry, which is
# counted but never pinned to a town. ``outline`` is an optional GeoJSON URL
# drawn on the home map; tools/extract_region_geojson.py can make one from
# Natural Earth's admin-1 data (e.g. "/static/data/home-region.geojson").
HOME_REGION = {"term": "minnesota", "label": "Minnesota", "center": (45.6, -93.6), "outline": None}

# Display-only corrections for recurring spellings in the export. Raw place text
# is preserved on records.
NAME_CORRECTIONS = ()
PLACE_CORRECTIONS = (
    (r"\bNorge\b", "Norway"),
    (r"\bSverige\b", "Sweden"),
    (r"\bSt\.? Paul\b", "Saint Paul"),
)

COUNTRIES = (
    (("norway", "norge"), "Norway"),
    (("sweden", "sverige"), "Sweden"),
    (("ireland",), "Ireland"),
    (("scotland",), "Scotland"),
    (("england",), "England"),
    (("new zealand",), "New Zealand"),
    (("canada",), "Canada"),
    (("usa", "united states", "minnesota", "iowa", "illinois", "pennsylvania", "new york"), "United States"),
)

# A deliberately small offline gazetteer: (aliases, lat, lng, label). The first
# alias found in the place text wins, so list towns before their states.
GAZETTEER = (
    (("minneapolis", "hennepin"), 44.978, -93.265, "Minneapolis, Minnesota"),
    (("saint paul", "st. paul", "st paul", "ramsey"), 44.954, -93.090, "Saint Paul, Minnesota"),
    (("stillwater",), 45.056, -92.806, "Stillwater, Minnesota"),
    (("northfield",), 44.458, -93.161, "Northfield, Minnesota"),
    (("duluth",), 46.787, -92.100, "Duluth, Minnesota"),
    (("moorhead",), 46.874, -96.767, "Moorhead, Minnesota"),
    (("decorah",), 43.303, -91.786, "Decorah, Iowa"),
    (("chicago",), 41.878, -87.630, "Chicago, Illinois"),
    (("pittsburgh",), 40.441, -79.996, "Pittsburgh, Pennsylvania"),
    (("philadelphia",), 39.952, -75.165, "Philadelphia, Pennsylvania"),
    (("new york",), 40.713, -74.006, "New York, New York"),
    (("voss",), 60.628, 6.414, "Voss, Norway"),
    (("bergen",), 60.391, 5.322, "Bergen, Norway"),
    (("stavanger",), 58.970, 5.733, "Stavanger, Norway"),
    (("gothenburg", "göteborg"), 57.709, 11.975, "Gothenburg, Sweden"),
    (("cork",), 51.898, -8.471, "Cork, Ireland"),
    (("castlebar", "mayo"), 53.855, -9.288, "Castlebar, Ireland"),
    (("glasgow",), 55.864, -4.252, "Glasgow, Scotland"),
    (("inverness",), 57.478, -4.225, "Inverness, Scotland"),
    (("dunedin",), -45.879, 170.503, "Dunedin, New Zealand"),
    (("minnesota",), 46.0, -94.5, "Minnesota"),
    (("iowa",), 42.0, -93.5, "Iowa"),
    (("illinois",), 40.0, -89.2, "Illinois"),
    (("pennsylvania",), 40.88, -77.80, "Pennsylvania"),
    (("norway", "norge"), 61.5, 8.5, "Norway"),
    (("sweden", "sverige"), 60.1, 15.0, "Sweden"),
    (("ireland",), 53.35, -7.70, "Ireland"),
    (("scotland",), 56.49, -4.20, "Scotland"),
    (("new zealand",), -41.0, 174.0, "New Zealand"),
)

# The places page groups every mapped place into three chapters. The chapter
# IDs are fixed; their titles are yours.
PLACE_TIERS = {
    "overseas-origins": (
        "Overseas origins",
        "The towns and regions outside America where branches begin.",
        "Where connected family lines first appear abroad.",
    ),
    "footholds": (
        "American footholds",
        "Places where connected branches first appear and grow in America.",
        "The first American regions attached to arriving family lines.",
    ),
    "home-communities": (
        "Minnesota communities",
        "The regions where many branches gathered across generations.",
        "Where generations gathered and built community in Minnesota.",
    ),
}

PLACE_REGIONS = {
    "scandinavia": ("Scandinavia", "Norwegian and Swedish parishes and port towns."),
    "british-isles": ("Ireland & Scotland", "Irish counties and Scottish towns where the older lines begin."),
    "farther-afield": ("Farther afield", "Places beyond the family's main geography."),
    "eastern-seaboard": ("Pennsylvania & New York", "Ports of arrival and the first American homes of the Irish and Scottish lines."),
    "upper-midwest": ("Iowa & Illinois", "Way stations on the road to Minnesota."),
    "twin-cities": ("Twin Cities & St. Croix", "Minneapolis, Saint Paul, and Stillwater: the family's strongest cluster."),
    "southern-minnesota": ("Southern Minnesota", "Farm towns and college towns south of the cities."),
    "northern-minnesota": ("Northern Minnesota", "Duluth and the North Shore."),
    "greater-minnesota": ("Greater Minnesota", "Other Minnesota communities, including the Red River Valley."),
}

# Ordered classification rules. Each place goes to the first rule it satisfies.
# Conditions: ``all`` / ``any`` (substrings of the place label, lower-case),
# ``lng_below`` / ``lng_above``. A rule with no conditions always matches.
PLACE_RULES = (
    {"tier": "home-communities", "region": "twin-cities", "all": ("minnesota",), "any": ("minneapolis", "saint paul", "stillwater")},
    {"tier": "home-communities", "region": "southern-minnesota", "all": ("minnesota",), "any": ("northfield",)},
    {"tier": "home-communities", "region": "northern-minnesota", "all": ("minnesota",), "any": ("duluth",)},
    {"tier": "home-communities", "region": "greater-minnesota", "all": ("minnesota",)},
    {"tier": "footholds", "region": "eastern-seaboard", "lng_below": -30, "any": ("pennsylvania", "new york")},
    {"tier": "footholds", "region": "upper-midwest", "lng_below": -30},
    {"tier": "overseas-origins", "region": "scandinavia", "any": ("norway", "sweden")},
    {"tier": "overseas-origins", "region": "british-isles", "any": ("ireland", "scotland", "england")},
    {"tier": "overseas-origins", "region": "farther-afield"},
)

# Narrative regions for the first American record of each overseas-born person.
# These are not ports; they keep the stream map readable.
MIGRATION_REGIONS = (
    {"id": "twin-cities", "label": "Twin Cities", "lat": 45.0, "lng": -93.2, "any": ("minneapolis", "saint paul", "st. paul", "stillwater")},
    {"id": "greater-minnesota", "label": "Greater Minnesota", "lat": 46.0, "lng": -94.5, "any": ("minnesota",)},
    {"id": "upper-midwest", "label": "Iowa & Illinois", "lat": 42.5, "lng": -90.5, "any": ("iowa", "illinois", "wisconsin")},
    {"id": "eastern-seaboard", "label": "New York & Pennsylvania", "lat": 40.6, "lng": -76.5, "any": ("pennsylvania", "new york")},
)

# Family streams on the home map are symbolic tributaries, not itineraries. Both
# ends are coarser than the gazetteer: origin by birth country, destination by
# migration region.
CORRIDOR_ORIGINS = {
    "Norway": ("Norway", 61.0, 8.0),
    "Sweden": ("Sweden", 59.5, 14.5),
    "Ireland": ("Ireland", 53.3, -7.7),
    "Scotland": ("Scotland", 56.5, -4.2),
}
CORRIDOR_DESTINATIONS = {
    "twin-cities": ("Minnesota", 45.5, -94.0),
    "greater-minnesota": ("Minnesota", 45.5, -94.0),
    "upper-midwest": ("Iowa & Illinois", 42.5, -90.5),
    "eastern-seaboard": ("New York & Pennsylvania", 40.6, -76.5),
}

# ---------------------------------------------------------------------------
# Narrative copy for the timeline and the three home-map chapters
# ---------------------------------------------------------------------------

# Placeholders in braces are filled from the tree. ``context`` blocks are
# optional; add ``contextSource`` and ``contextUrl`` to cite them.
TIMELINE = {
    "earliest": {
        "title": "The earliest named generation",
        "text": "{name} is the earliest relative currently dated in the tree. From here, branches extend through Irish, Scottish, and Scandinavian communities.",
        "fallback_place": "Europe",
    },
    "first_foothold": {
        "title": "Branches appear in America",
        "text": "The Irish and Scottish lines reach Philadelphia and Pittsburgh in the later 1700s, two generations before any Scandinavian relative crosses.",
        "context": "Pennsylvania drew large numbers of Irish and Scottish emigrants through the eighteenth century. The dates place the family records in context; they do not establish when a particular ancestor arrived.",
    },
    "first_home": {
        "title": "Minnesota becomes a meeting place",
        "text": "Stillwater appears first, followed by Minneapolis, Northfield, Duluth, and the Red River Valley.",
        "place": "Stillwater · Minneapolis · Duluth",
        "context": "Minnesota became a state in 1858. The wider settlement history helps explain the setting, but does not establish why any one family moved there.",
    },
    "merge": {
        "title": "The two streams finally meet",
        "text": "Until now the Scandinavian and Irish-Scottish branches have run side by side without touching. Between {first_year} and {last_year} they marry into each other {weddings} times, and {descendants} relatives descend from both.",
        "text_fallback": "The Scandinavian and Irish-Scottish branches run side by side across the same regions.",
        "fallback_year": 1890,
        "fallback_place": "Minnesota",
    },
    "growth": {
        "year": 1920,
        "title": "Families grow across a shared region",
        "text": "Births, marriages, homes, and burials connect generations across Minneapolis, Northfield, Duluth, and communities beyond Minnesota.",
        "place": "Minnesota and beyond",
    },
    "present": {
        "title": "The public story reaches the present edge",
        "text": "The archive continues into recent generations. Living relatives carry these branches forward and remain private on the public site.",
        "place": "A living family archive",
    },
}

MAP_CHAPTERS = {
    "origins": {
        "title": "Two streams, generations apart",
        "eyebrow": "01 · Where they began",
        "summary": "Irish and Scottish lines left Cork, Mayo, Glasgow, and Inverness from the 1760s. Norwegian and Swedish lines left Voss, Bergen, Stavanger, and Gothenburg in the 1850s and after. Select a place to meet the people who left it.",
        "anecdote": "The Brennan line was in Philadelphia before 1770. The Halvorsen line left Voss in 1861. Nothing connected them for another century.",
        "method": "Dots group the places named across the family tree. Larger dots connect more relatives.",
    },
    "gateways": {
        "title": "Different centuries, different routes",
        "eyebrow": "02 · The streams cross",
        "summary": "The Irish and Scottish stream landed in Pennsylvania and New York. The Scandinavian stream went straight to the Upper Midwest. The coloured streams gather each side's surnames into the four branches named for the grandparents of the present generation.",
        "anecdote": "The streams ran side by side for generations. {weddings} weddings between {first_year} and {last_year} joined them, and {descendants} relatives now descend from both.",
        "anecdote_fallback": "The streams ran side by side for generations before marriage joined them.",
        "method": "These streams are a symbolic family overview based on recorded origins and first American regions. They are not exact routes, ports, or individual voyages.",
    },
    "homesteads": {
        "title": "One family in Minnesota",
        "eyebrow": "03 · Where they took root",
        "summary": "The strongest record clusters centre on Minneapolis and Stillwater, with others around Northfield, Duluth, and Moorhead.",
        "anecdote": "Within two generations of the weddings, one map: the Twin Cities, the southern farm towns, and the North Shore.",
        "method": "Every named Minnesota life event contributes to these community groups; statewide-only entries are not pinned to a town. Larger dots connect more relatives.",
    },
}

# ---------------------------------------------------------------------------
# Curated stories
# ---------------------------------------------------------------------------

# Person IDs refer to the GEDCOM. Only ``featured`` stories are listed and
# linked; unfeatured ones stay reachable by URL as research notes.
STORIES = (
    {
        "slug": "fraser-moe-duluth-1880",
        "featured": True,
        "title": "The first wedding between the streams",
        "dek": "Hugh Fraser's parents left Inverness in 1848. Ingrid Moe left Stavanger in 1876. In 1880 they married in Duluth, and the tree's two streams touched for the first time.",
        "eyebrow": "Fraser and Moe families · 1880",
        "status": "Pattern derived from the family tree",
        "openQuestions": ("Does a Duluth marriage record confirm the 1880 date?",),
        "people": ("I36", "I37"),
        "places": ("duluth-minnesota",),
        "surnames": ("fraser", "moe"),
        "sections": (
            {"heading": "Two lines, two centuries", "body": "The Fraser line in this tree is Scottish, recorded in Inverness before the family reached Pittsburgh. The Moe line is Norwegian, recorded in Stavanger. Nothing in the tree connects them before 1880."},
            {"heading": "A shared city", "body": "Both families appear in Duluth by the late 1870s. The tree records the marriage there and a son, George, born in 1888."},
            {"heading": "What the record cannot say", "body": "The tree shows where two lines meet, not how two people did. Directories and parish records may say more."},
        ),
        "links": (("I36", "Meet Hugh Fraser"), ("I37", "Meet Ingrid Moe")),
    },
    {
        "slug": "francis-brennan-dunedin-1921",
        "featured": True,
        "title": "The brother who went to New Zealand",
        "dek": "Four Brennan siblings died in Minnesota. Francis died in Dunedin. The tree shows the endpoints, not the journey between them.",
        "eyebrow": "Brennan family · 1874–1921",
        "status": "Pattern derived from the family tree",
        "openQuestions": ("Which independent record traces Francis from Stillwater to Dunedin?",),
        "people": ("I13",),
        "places": (),
        "surnames": ("brennan",),
        "sections": (
            {"heading": "Children in Stillwater", "body": "Michael Brennan and Catherine Walsh's children were born in Stillwater between 1866 and 1874. Most siblings with recorded death places died in Minnesota."},
            {"heading": "One distant endpoint", "body": "Francis Brennan, born in 1874, died in Dunedin, New Zealand, in 1921. In this tree he is the only relative to end a life in the southern hemisphere."},
            {"heading": "Why the contrast matters", "body": "A single destination becomes meaningful when the family around it is visible. Independent records are still needed to trace the journey."},
        ),
        "links": (("I13", "Open Francis Brennan's record"),),
    },
    {
        "slug": "an-age-that-asks-for-doubt",
        "featured": False,
        "title": "An age that asks for doubt",
        "dek": "A recorded lifespan of 106 years is a signal for research, not a longevity record to celebrate.",
        "eyebrow": "Research notebook · unresolved",
        "status": "Needs verification",
        "openQuestions": ("Do parish and probate records separate two men of the same name?",),
        "people": ("I50",),
        "places": (),
        "surnames": ("kerr",),
        "sections": (
            {"heading": "The claim", "body": "William Kerr's recorded dates are 1728–1834, implying an age of 106."},
            {"heading": "The likelier explanation", "body": "Trees can merge two people with the same name, attach a death to the wrong birth, or inherit an old transcription error."},
            {"heading": "How this archive handles uncertainty", "body": "The dates remain visible because they are part of the received tree. The research marker keeps them from passing as settled fact."},
        ),
        "links": (("I50", "Review William Kerr"),),
    },
)

# People whose unusual destination is worth a homepage card. An editorial
# decision, not just an unusual value.
SHOWCASE_PERSON_IDS = frozenset({"I13"})
