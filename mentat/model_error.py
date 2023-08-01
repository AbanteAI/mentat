# Raised when model output doesn't adhere to the specified format for changes
class ModelError(Exception):
    def __init__(self, message, unfinished_change):
        super().__init__(message)
        self.unfinished_change = unfinished_change
