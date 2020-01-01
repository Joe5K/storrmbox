import os
from flask import Flask

from . import config
from .api import api_blueprint
from .extensions import db, migrate


def create_app(config_object=config.Config):
    """Construct the core application."""
    app = Flask(__name__)
    app.app_context().push()

    # Application Configuration
    app.config.from_object(config_object)

    # Initialize extensions and blueprints
    register_extensions(app)
    register_blueprints(app)

    # Set up CORS handling
    app.after_request(after_request)

    # New db app if no database.
    db.app = app

    # Create all database tables.
    db.create_all()

    return app


def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Origin,X-Requested-With,Content-Type,Accept,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response


def register_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)


def register_blueprints(app):
    app.register_blueprint(api_blueprint)
