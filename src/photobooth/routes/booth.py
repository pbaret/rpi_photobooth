"""HTTP routes for the touch-first booth experience."""

from flask import Blueprint, render_template

booth_blueprint = Blueprint("booth", __name__)


@booth_blueprint.get("/")
def index() -> str:
    """Render the initial booth screen without acquiring hardware."""
    return render_template("booth/index.html")