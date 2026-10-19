"""Precise, non-sensitive failure contracts for the bridge."""


class BridgeError(Exception):
    """A validation or capability error that must stop resolution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
