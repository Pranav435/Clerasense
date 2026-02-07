"""
Clerasense – Flask Application Factory
"""

from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import Config
from app.database import db
from app.routes.drugs import drugs_bp
from app.routes.chat import chat_bp
from app.routes.comparison import comparison_bp
from app.routes.safety import safety_bp
from app.routes.pricing import pricing_bp
from app.routes.auth import auth_bp
from app.middleware.auth_middleware import jwt_required_middleware
from app.middleware.audit_logger import audit_after_request

limiter = Limiter(key_func=get_remote_address, default_limits=[Config.RATE_LIMIT_DEFAULT])


def create_app() -> Flask:
    Config.validate()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.FLASK_SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = Config.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Extensions
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    limiter.init_app(app)
    db.init_app(app)

    # Middleware
    app.before_request(jwt_required_middleware)
    app.after_request(audit_after_request)

    # Blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(drugs_bp, url_prefix="/api/drugs")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(comparison_bp, url_prefix="/api/comparison")
    app.register_blueprint(safety_bp, url_prefix="/api/safety")
    app.register_blueprint(pricing_bp, url_prefix="/api/pricing")

    # Health check
    @app.route("/api/health")
    def health():
        return {"status": "ok", "service": "clerasense"}

    return app
