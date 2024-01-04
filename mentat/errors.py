class ModelError(Exception):
    """
    Raised when model output doesn't adhere to the specified format for changes.
    Handled by the parser; shouldn't be thrown outside of parsing!
    """


class RemoteKeyboardInterrupt(Exception):
    """Used to indicate a KeyboardInterupt thrown by a remote client"""


# TODO: Combine MentatError and UserError into just MentatError
class MentatError(Exception):
    """
    Will show the user the exception, but not the stacktrace. Used for known errors.
    """


class UserError(Exception):
    """
    Will show the user the exception, but not the stacktrace. Used for known errors.
    """


class HistoryError(Exception):
    """
    Raised when an execption is encountered undoing or redoing edits.
    """


class SampleError(Exception):
    """
    Raised when an exception is raised by a Sample.
    """


class SessionExit(Exception):
    """
    Stops the session without any sign of error.
    """


class PathValidationError(Exception):
    pass


class ReturnToUser(Exception):
    """
    Raised when trying to call the API with too many tokens for that model.
    Will give control back to the user after being raised.
    """
