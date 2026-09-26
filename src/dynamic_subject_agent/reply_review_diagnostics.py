"""Closed local failure categories; never carry provider text or response fields."""
HTTP_DIAGNOSTIC_STATUSES = frozenset((400, 401, 403, 408, 429, 500, 502, 503, 504))
REVIEW_DIAGNOSTIC_CODES = frozenset((
    "transport-timeout", "transport-network", "transport-delivery-ambiguous", "transport-failure", "http-other",
    "response-envelope", "response-model", "response-reasoning", "response-usage",
    "response-truncated", "response-overbudget", "response-content-json", "response-tools",
    "response-incomplete", "response-size", "review-schema", "review-quote", "review-label",
)) | frozenset(f"http-{status}" for status in HTTP_DIAGNOSTIC_STATUSES)


class ReviewValidationFailure(ValueError):
    def __init__(self, diagnostic_code):
        if diagnostic_code not in ("review-schema", "review-quote", "review-label"):
            raise ValueError("invalid review failure category")
        super().__init__(diagnostic_code)
        self.diagnostic_code = diagnostic_code
