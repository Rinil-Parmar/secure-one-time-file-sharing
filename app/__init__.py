from flask import Flask, render_template

from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    return app
