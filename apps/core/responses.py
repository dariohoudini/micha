from rest_framework.response import Response

def error_response(message: str, code: int = 400, extra: dict = None) -> Response:
    body = {'error': message}
    if extra:
        body.update(extra)
    return Response(body, status=code)

def success_response(data=None, message: str = None, code: int = 200) -> Response:
    body = {}
    if data is not None:
        body['data'] = data
    if message:
        body['message'] = message
    return Response(body, status=code)

def not_found(message: str = 'Não encontrado') -> Response:
    return error_response(message, 404)

def forbidden(message: str = 'Acesso negado') -> Response:
    return error_response(message, 403)

def validation_error(message: str, errors: dict = None) -> Response:
    body = {'error': message}
    if errors:
        body['errors'] = errors
    return Response(body, status=400)
