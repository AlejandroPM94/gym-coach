class CoachError(Exception):
    """Base error safe to show at the application boundary."""


class CoachConfigurationError(CoachError):
    """The coach provider or athlete profile is not configured."""


class CoachEvidenceError(CoachError):
    """The model referenced evidence that was not supplied by deterministic code."""


class CoachPersistenceError(CoachError):
    """Coach state could not be persisted safely."""
