from mentat.user_session import user_session

__all__ = [
    "user_session",
]


def __dir__():
    return __all__


# Make sure to bump this on Release x.y.z PR's!
__version__ = "1.0.7"


# the very first thing we need to do is load_config so we don't have an empty object while booting.
from mentat.config import load_config  # noqa: E402

load_config()
