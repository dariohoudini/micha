"""
Custom Exception Handler
Ensures every error response has the same format:
{
    "error": "short_code",
    "detail": "Human readable message",
    "request_id": "abc12345",
    "field_errors": {}   // only for validation errors
}
This fixes the inconsistent error format gap identified in the audit.
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('micha')


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get('request')
    request_id = getattr(request, 'request_id', '-') if request else '-'

    if response is not None:
        error_data = {
            'request_id': request_id,
        }

        # Validation errors (400) — field-level
        if response.status_code == 400:
            if isinstance(response.data, dict):
                # Separate field errors from non-field errors
                field_errors = {}
                detail_msgs = []
                for key, val in response.data.items():
                    if key == 'detail':
                        detail_msgs.append(str(val))
                    elif key == 'non_field_errors':
                        if isinstance(val, list):
                            detail_msgs.extend([str(v) for v in val])
                        else:
                            detail_msgs.append(str(val))
                    else:
                        field_errors[key] = val if isinstance(val, list) else [val]

                error_data['error'] = 'validation_error'
                error_data['detail'] = ' '.join(detail_msgs) or 'Validation failed.'
                if field_errors:
                    error_data['field_errors'] = field_errors
            else:
                error_data['error'] = 'bad_request'
                error_data['detail'] = str(response.data)

        elif response.status_code == 401:
            error_data['error'] = 'authentication_required'
            error_data['detail'] = 'Authentication credentials were not provided or are invalid.'

        elif response.status_code == 403:
            error_data['error'] = 'permission_denied'
            error_data['detail'] = str(response.data.get('detail', 'You do not have permission to perform this action.'))

        elif response.status_code == 404:
            error_data['error'] = 'not_found'
            error_data['detail'] = str(response.data.get('detail', 'The requested resource was not found.'))

        elif response.status_code == 429:
            error_data['error'] = 'rate_limited'
            error_data['detail'] = 'Too many requests. Please slow down and try again later.'

        elif response.status_code >= 500:
            error_data['error'] = 'server_error'
            # SECURITY: Don't expose internal error details to clients
            error_data['detail'] = 'An internal error occurred. Our team has been notified.'
            logger.error(f"500 error [request_id={request_id}]: {exc}", exc_info=True)

        else:
            error_data['error'] = 'error'
            error_data['detail'] = str(response.data.get('detail', 'An error occurred.'))

        response.data = error_data

    else:
        # Unhandled exception — return 500 without leaking details
        logger.exception(f"Unhandled exception [request_id={request_id}]: {exc}")
        return Response(
            {
                'error': 'server_error',
                'detail': 'An internal error occurred. Our team has been notified.',
                'request_id': request_id,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response
