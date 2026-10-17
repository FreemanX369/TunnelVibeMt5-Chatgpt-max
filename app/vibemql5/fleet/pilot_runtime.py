"""Bounded control-only pilot recovery; no authority or journal resets."""
from .wire import WireError

RETRYABLE_CONTROL_ERRORS = frozenset({
    'HTTPS_UNAVAILABLE', 'HTTP_DEADLINE_EXCEEDED', 'CONTROL_TIME_INVALID',
    'NODE_SESSION_REQUIRED',
})

class PilotRoundGuard:
    """Fence a failing node while leaving the separately owned gateway alive.

    Used only by the explicit unqualified control pilot. A successful round
    resets consecutive failures. Authority/integrity failures never retry.
    """
    def __init__(self, maximum_failures=3):
        if type(maximum_failures) is not int or not 1 <= maximum_failures <= 10:
            raise ValueError('PILOT_RETRY_POLICY_INVALID')
        self.maximum_failures = maximum_failures
        self.failures = 0
        self.fenced = False
        self.last_code = None

    def run(self, step):
        if self.fenced:
            return {'status':'NODE_FENCED', 'reason_code':self.last_code, 'retry_after_seconds':0}
        try:
            step()
        except Exception as error:
            self.failures += 1
            self.last_code = error.code if isinstance(error, WireError) and error.code in RETRYABLE_CONTROL_ERRORS else 'NODE_REQUIRES_OPERATOR'
            retryable = isinstance(error, WireError) and error.code in RETRYABLE_CONTROL_ERRORS
            self.fenced = not retryable or self.failures >= self.maximum_failures
            return {'status':'NODE_FENCED' if self.fenced else 'CONTROL_RETRY',
                    'reason_code':self.last_code, 'consecutive_failures':self.failures,
                    'retry_after_seconds':0 if self.fenced else min(4, 2 ** (self.failures-1))}
        self.failures = 0
        self.last_code = None
        return {'status':'RUNNING', 'reason_code':None, 'retry_after_seconds':0}
