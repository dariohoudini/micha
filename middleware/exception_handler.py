import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger("micha")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", "-") if request else "-"

    if response is not None:
        error_data = {"request_id": request_id}
        if response.status_code == 400:
            field_errors = {}
            detail_msgs = []
            if isinstance(response.data, dict):
                for key, val in response.data.items():
                    if key in ("detail", "non_field_errors"):
                        detail_msgs.append(str(val) if not isinstance(val, list) else " ".join(str(v) for v in val))
                    else:
                        field_errors[key] = val if isinstance(val, list) else [val]
            error_data["error"] = "validation_error"
            error_data["detail"] = " ".join(detail_msgs) or "Validation failed."
            if field_errors:
                error_data["field_errors"] = field_errors
        elif response.status_code == 401:
            error_data["error"] = "authentication_required"
            error_data["detail"] = "Authentication credentials were not provided or are invalid."
        elif response.status_code == 403:
            error_data["error"] = "permission_denied"
            error_data["detail"] = str(response.data.get("detail", "Permission denied."))
        elif response.status_code == 404:
            error_data["error"] = "not_found"
            error_data["detail"] = "The requested resource was not found."
        elif response.status_code == 429:
            error_data["error"] = "rate_limited"
            error_data["detail"] = "Too many requests. Please slow down."
        elif response.status_code >= 500:
            error_data["error"] = "server_error"
            error_data["detail"] = "An internal error occurred."
            logger.error(f"500 error [request_id={request_id}]: {exc}", exc_info=True)
        else:
            error_data["error"] = "error"
            error_data["detail"] = str(response.data.get("detail", "An error occurred."))
        response.data = error_data
    else:
        logger.exception(f"Unhandled exception [request_id={request_id}]: {exc}")
        return Response(
            {"error": "server_error", "detail": "An internal error occurred.", "request_id": request_id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
