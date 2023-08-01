# Raised when model output doesn't adhere to the specified format for changes
class ModelError(Exception):
    def __init__(self, message, already_added_to_changelist):
        super().__init__(message)
        self.already_added_to_changelist = already_added_to_changelist
