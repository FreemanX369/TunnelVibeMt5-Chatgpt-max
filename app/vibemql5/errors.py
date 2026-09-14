class VibeMQL5Error(Exception):
    """Base project error."""

class ConfigError(VibeMQL5Error):
    pass

class PathViolation(VibeMQL5Error):
    pass

class TerminalNotFound(VibeMQL5Error):
    pass

class ResourceLimitError(VibeMQL5Error):
    pass

class InvalidStateTransition(VibeMQL5Error):
    pass
