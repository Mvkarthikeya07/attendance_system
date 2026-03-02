"""WSGI entrypoint for Vercel, Render, and other platforms."""

from app import app

if __name__ == "__main__":
    app.run()
