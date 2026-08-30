"""
app_poc.py
----------
Throwaway Flask dev server for the free ("opendata") parcel provider — POC ONLY.

This file never moves to gaudi-api. It exists so the site repo's debug UI can
call the Python provider the same way it calls the Express backends: the Vite
dev proxy maps /api/opendata/* to this process (root package.json dev:opendata,
port 3004).

What gaudi-api's application.py does for real, this fakes minimally: it binds a
per-request ``g.fx_logger`` shim with the same ``.log(message, channel_name=)``
signature, so routes/parcel_edges.py and the *_client modules run unmodified in
both worlds. No auth, no DB, no CORS (the Vite proxy keeps the browser
same-origin).
"""
import logging
import os

from flask import Flask, g, jsonify

from routes.parcel_edges import parcel_edges_bp

_ENV_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.env'))


def _load_dotenv() -> None:
  """Minimal .env loader (site repo root), matching what dotenv does for the
  Express backends: KEY=VALUE lines, no override of real environment. POC only —
  gaudi-api centralizes env in config.py and never reads .env at runtime."""
  try:
    with open(_ENV_FILE, encoding='utf-8') as handle:
      for line in handle:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
          continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
  except OSError:
    pass


class _PlainFxLogger:
  """fx_logger-shaped shim over the stdlib logger."""

  def __init__(self, logger: logging.Logger) -> None:
    self._logger = logger

  def log(self, message: str, channel_name: str = 'default') -> None:
    level = logging.ERROR if channel_name == 'error' else logging.WARNING if channel_name == 'warning' else logging.INFO
    self._logger.log(level, '[%s] %s', channel_name, message)


def create_app() -> Flask:
  app = Flask(__name__)
  app.register_blueprint(parcel_edges_bp)

  @app.before_request
  def _bind_context() -> None:
    g.fx_logger = _PlainFxLogger(app.logger)

  @app.route('/health', methods=['GET'])
  def health():
    return jsonify({'ok': True, 'provider': 'opendata'}), 200

  return app


if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
  _load_dotenv()
  port = int(os.environ.get('PORT', '3004'))
  logging.info('opendata provider on :%s (google geocode: %s)', port, 'on' if os.environ.get('GOOGLE_API_KEY') else 'off — census fallback')
  create_app().run(host='127.0.0.1', port=port)
