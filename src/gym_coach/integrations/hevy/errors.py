class HevyError(Exception):
    """Base error for the Hevy boundary."""


class HevyConfigurationError(HevyError):
    """The local Hevy configuration is incomplete."""


class HevyTimeoutError(HevyError):
    """Hevy did not answer within the configured timeout."""


class HevyTransportError(HevyError):
    """A network-level error prevented communication with Hevy."""


class HevyHTTPError(HevyError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class HevyInvalidResponseError(HevyError):
    """Hevy returned malformed JSON or a response outside the expected contract."""
