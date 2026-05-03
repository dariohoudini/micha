import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger('micha')

def micha_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(response.data, dict):
            if 'detail' in response.data and 'error' not in response.data:
                response.data = {'error': str(response.data['detail'])}
        elif isinstance(response.data, list):
            response.data = {'error': response.data[0] if response.data else 'Validation error'}
        return response

    view = context.get('view')
    request = context.get('request')
    logger.error('unhandled_exception', exc_info=exc, extra={
        'view': view.__class__.__name__ if view else 'unknown',
        'path': request.path if request else 'unknown',
    })
    return Response(
        {'error': 'Erro interno do servidor. A nossa equipa foi notificada.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
