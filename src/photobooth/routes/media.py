"""HTTP adapter blueprint for future media routes."""

from flask import Blueprint

media_blueprint = Blueprint("media", __name__, url_prefix="/media")