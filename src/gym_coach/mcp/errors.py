class GymCoachMCPError(RuntimeError):
    """A safe error that may be shown to an MCP client."""


class ResourceNotFoundError(GymCoachMCPError):
    pass


class BackendUnavailableError(GymCoachMCPError):
    pass


class InternalToolError(GymCoachMCPError):
    def __init__(self) -> None:
        super().__init__("gym-coach could not complete the request safely")
