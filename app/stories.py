"""Curated, public narrative objects built from the currently published tree.

These are deliberately separate from GED parsing: the tree supplies facts while
the editorial layer supplies interpretation, caveats, and discovery links. The
stories themselves belong to the family, so they live in the site profile.
"""

from .site_profile import profile

STORIES = tuple(profile.STORIES)

STORY_PERSON_IDS = frozenset(
    person_id for story in STORIES if story.get("featured", False) for person_id in story["people"]
)

# A destination contrast needs an editorial decision, not merely an unusual value.
SHOWCASE_PERSON_IDS = frozenset(profile.SHOWCASE_PERSON_IDS)


def story_by_slug(slug):
    return next((story for story in STORIES if story["slug"] == slug), None)


def stories_for(*, person_id=None, place_slug=None, surname_slug=None):
    return [story for story in STORIES if (
        (person_id and person_id in story["people"])
        or (place_slug and place_slug in story["places"])
        or (surname_slug and surname_slug in story["surnames"])
    )]
