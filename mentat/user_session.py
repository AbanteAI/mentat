from typing import Dict, Any

user_session_store: Dict[str, Any] = {}

class UserSession:
    """
    Developer facing user session class.
    Useful for the developer to store user specific data between calls.
    """

    def get(self, key: str, default: Any=None) -> Any:
        return user_session_store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        user_session_store[key] = value


user_session = UserSession()
