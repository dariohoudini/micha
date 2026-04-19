import uuid
import logging
import threading

_local = threading.local()
logger = logging.getLogger("micha")


def get_current_request_id():
    return getattr(_local, "request_id", "-")


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())[:8]
        request.request_id = request_id
        _local.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_current_request_id()
        return True

logging.getLogger().addFilter(RequestIDFilter())
