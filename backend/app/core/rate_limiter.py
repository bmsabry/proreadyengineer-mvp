"""Shared rate limiter instance for per-endpoint decorators."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level limiter so auth.py and other routers can import and decorate routes.
# The limiter is also attached to app.state.limiter in main.py.
limiter = Limiter(key_func=get_remote_address)
