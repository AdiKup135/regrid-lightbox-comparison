"""Shared test transport for the parcel_data clients: a requests-shaped fake.

Every client takes an injectable ``session`` and only calls ``session.get``,
so one fake covers the whole package. Route by URL substring; a handler may be
a payload (returned as JSON), an Exception instance (raised), or a callable
receiving (url, params).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

Handler = Union[Dict[str, Any], List[Any], Exception, Callable[[str, Dict[str, Any]], Any]]


class FakeResponse:
  def __init__(self, payload: Any, status_code: int = 200) -> None:
    self._payload = payload
    self.status_code = status_code
    self.ok = 200 <= status_code < 300

  def json(self) -> Any:
    if isinstance(self._payload, Exception):
      raise self._payload
    return self._payload


class FakeSession:
  """Routes session.get(url, params=...) to the first matching handler."""

  def __init__(self, routes: List[Tuple[str, Handler]]) -> None:
    self._routes = routes
    self.requests: List[Tuple[str, Dict[str, Any]]] = []

  def get(self, url: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> FakeResponse:
    params = params or {}
    self.requests.append((url, params))
    for fragment, handler in self._routes:
      if fragment in url:
        if isinstance(handler, Exception):
          raise handler
        if callable(handler):
          result = handler(url, params)
          return result if isinstance(result, FakeResponse) else FakeResponse(result)
        return FakeResponse(handler)
    raise AssertionError('FakeSession: unrouted URL %s' % url)
