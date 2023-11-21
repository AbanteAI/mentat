import os
import platform
from uuid import UUID, uuid4

import sentry_sdk

from mentat import __version__
from mentat.app_conf import IS_DEV
from mentat.utils import mentat_dir_path

user_id_path = mentat_dir_path / ".user"


def _new_user() -> UUID:
    user = uuid4()
    with user_id_path.open("w") as uuid_file:
        uuid_file.write(str(user))
    return user


def _get_user() -> UUID:
    if user_id_path.exists():
        with user_id_path.open("r") as uuid_file:
            try:
                user = UUID(uuid_file.read())
            except ValueError:
                user = _new_user()
    else:
        user = _new_user()
    return user


def sentry_init():
    # Check if in dev or testing (although we should never be in testing in prod)
    if IS_DEV or "PYTEST_CURRENT_TEST" in os.environ:
        return

    sentry_sdk.init(
        dsn="https://fa4d2b80dab0938c38c89384dc317f1b@o4506146491006976.ingest.sentry.io/4506187066245120",
        profiles_sample_rate=1.0,
        enable_tracing=True,
        traces_sample_rate=1.0,
    )
    sentry_sdk.set_tag("version", __version__)
    sentry_sdk.set_user({"id": _get_user()})
    uname = platform.uname()
    sentry_sdk.set_context(
        "os",
        {
            "raw_description": " ".join(uname),
            "name": uname.system,
            "version": uname.release,
        },
    )
