from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class CartConflict(APIException):
    """Typed 409 conflict for cart operations.

    The response body is rendered at top level as:
        {"code": "...", "detail": "...", ...extra}
    """

    status_code = 409
    default_detail = 'Conflict.'
    default_code = 'conflict'

    def __init__(self, code=None, detail=None, **extra):
        self.code = code or self.default_code
        self.extra = extra
        super().__init__(detail)


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response
    if isinstance(exc, CartConflict):
        response.data = {
            'code': exc.code,
            'detail': exc.detail or CartConflict.default_detail,
        }
        response.data.update(exc.extra)
    return response
