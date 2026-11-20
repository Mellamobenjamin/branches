from pathlib import Path
import os

from flask import Flask


def default_gedcom_path(project_dir):
    """Your private export if present, otherwise the fictional sample tree."""
    private = project_dir / "data" / "family-tree.ged"
    return private if private.is_file() else project_dir / "samples" / "example-family.ged"


def create_app(test_config=None):
    app = Flask(__name__)
    project_dir = Path(__file__).resolve().parent.parent

    from .site_profile import profile

    app.config.from_mapping(
        GEDCOM_PATH=os.environ.get("BRANCHES_GEDCOM_PATH", str(default_gedcom_path(project_dir))),
        EDITORIAL_DB_PATH=os.environ.get(
            "BRANCHES_EDITORIAL_DB_PATH", str(project_dir / "data" / "editorial.sqlite3")
        ),
        SITE_URL=os.environ.get("BRANCHES_SITE_URL", profile.SITE["url"]),
        SHOW_LIVING=os.environ.get("BRANCHES_SHOW_LIVING", "0") == "1",
        SECRET_KEY=os.environ.get("SECRET_KEY", "development-only"),
    )
    if test_config:
        app.config.update(test_config)

    @app.context_processor
    def site_profile():
        return {"site": profile.SITE, "home_copy": profile.HOME}

    from .routes import bp

    app.register_blueprint(bp)
    return app
