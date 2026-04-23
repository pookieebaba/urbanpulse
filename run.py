import os
from app import create_app, socketio

app = create_app(os.getenv("FLASK_ENV", "production"))

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False,
        allow_unsafe_werkzeug=True,
    )