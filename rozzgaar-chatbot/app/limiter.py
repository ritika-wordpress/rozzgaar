from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared Limiter instance. Lives in its own module (not main.py) so routers
# can import it without creating a circular import with main.py, which in
# turn imports the routers.
limiter = Limiter(key_func=get_remote_address)
