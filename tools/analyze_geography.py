"""Print the place evidence you need when writing a site profile.

Lists immigration events, the first home-country record of every overseas-born
person, the most common home-region places, and any places the profile
gazetteer cannot locate yet.

    python tools/analyze_geography.py data/family-tree.ged
"""

from collections import Counter, defaultdict
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import default_gedcom_path  # noqa: E402
from app.genealogy import GedcomRepository, country_for, locate  # noqa: E402
from app.site_profile import profile  # noqa: E402


path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_gedcom_path(PROJECT_ROOT)
repo = GedcomRepository(path)
people = [person for person in repo.people.values() if repo.visible(person)]
home_country = profile.HOME_COUNTRY
home_term = profile.HOME_REGION["term"]

print("EVENT TAGS", Counter(event.kind for person in people for event in person.events))
print("IMMIGRATION EVENTS")
for person in people:
    for event in person.events:
        if event.kind in ("IMMI", "EMIG"):
            print(" ", person.clean_name, event.date, event.place)

gateways = Counter()
gateway_people = defaultdict(set)
home = Counter()
home_people = defaultdict(set)
unlocated = Counter()
foreign_born = 0
for person in people:
    birth = person.event("BIRT")
    if birth and birth.place and country_for(birth.place) not in (home_country, "Unknown"):
        foreign_born += 1
        candidates = [
            event for event in person.events
            if event.place and country_for(event.place) == home_country and event.year
        ]
        if candidates:
            first = min(candidates, key=lambda event: event.year)
            gateways[first.place] += 1
            gateway_people[first.place].add(person.id)
    for event in person.events:
        if not event.place:
            continue
        if home_term in event.place.casefold():
            home[event.place] += 1
            home_people[event.place].add(person.id)
        if not locate(event.place):
            unlocated[event.place] += 1

print("BORN OUTSIDE", home_country, foreign_born)
print(f"FIRST {home_country.upper()} RECORDS")
for place, count in gateways.most_common(40):
    print(" ", count, len(gateway_people[place]), place)
print(f"{profile.HOME_REGION['label'].upper()} RECORDS")
for place, count in home.most_common(50):
    print(" ", count, len(home_people[place]), place)
print("PLACES THE GAZETTEER CANNOT LOCATE")
for place, count in unlocated.most_common(50):
    print(" ", count, place)
