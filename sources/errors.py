class SourceError(Exception):
    """Raised by a source when a reading fails for a known reason. The core turns
    it into the standard error shape: {"code": code, "message": message}.

    Codes: permission_denied, unavailable, unsupported_platform, internal.
    (timeout is set by the core, never by a source.)
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
