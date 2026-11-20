"""Load the active site profile.

Everything that belongs to one particular family -- the site name, branch
anchors, map regions, gazetteer, migration streams, homepage copy and curated
stories -- lives in a profile module under ``app/profiles``. The engine reads
those values and never names a family itself.

Choose a profile with the ``BRANCHES_PROFILE`` environment variable (the module
name, without ``.py``). The default is the fictional ``example`` profile, which
pairs with ``samples/example-family.ged``.
"""

import importlib
import os

PROFILE_NAME = os.environ.get("BRANCHES_PROFILE", "example")
profile = importlib.import_module(f"app.profiles.{PROFILE_NAME}")
