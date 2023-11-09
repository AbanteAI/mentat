# Raised when model output doesn't adhere to the specified format for changes
class ModelError(Exception):
    pass


# Used to indicate a KeyboardInterupt thrown by a remote client
class RemoteKeyboardInterrupt(Exception):
    pass


# These 2 errors will have their message displayed in red, but no stacktrace thrown


# TODO: Combine MentatError and UserError into just MentatError
class MentatError(Exception):
    pass


class UserError(Exception):
    pass


# This will exit the session without showing any sign of error
class SessionExit(Exception):
    pass
