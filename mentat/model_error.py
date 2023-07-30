# Raised when model messes up creating a change
class ModelError(Exception):
    def __init__(self, message, unfinished_change):
        super().__init__(message)
        self.unfinished_change = unfinished_change
