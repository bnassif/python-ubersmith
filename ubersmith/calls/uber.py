# uber calls implemented as documented in api docs go here

from ubersmith.api import VALID_METHODS
from ubersmith.exceptions import (
    ResponseError,
    ValidationError,
    ValidationErrorDefault,
)
from ubersmith.calls.base import BaseCall, api_call
from ubersmith.utils import prepend_base

__all__ = [
    'api_export',
    'check_login',
    'method_get',
]

_METHOD_BASE = "uber"
prepend_base = prepend_base.init(_METHOD_BASE)


class _ApiExportCall(BaseCall):
    method = prepend_base('api_export')

    def __init__(self, request_handler, table, gzip=False, order_by=None):
        super(_ApiExportCall, self).__init__(request_handler)
        self.table = table
        self.gzip = gzip
        self.order_by = order_by

    def validate(self):
        if self.table:
            return True

    def build_request_data(self):
        self.request_data = {}
        self.request_data['table'] = self.table
        if self.gzip:
            self.request_data['gzip'] = 1
        if self.order_by:
            self.request_data['order_by'] = self.order_by


class _CheckLoginCall(BaseCall):
    method = prepend_base('check_login')

    def __init__(self, request_handler, username, password):
        super(_CheckLoginCall, self).__init__(request_handler)
        self.username = username
        self.password = password

    def validate(self):
        if self.username and self.password:
            return True
        else:
            raise ValidationErrorDefault(False)

    def build_request_data(self):
        self.request_data = {
            'login': self.username,
            'pass': self.password,
        }

    def request(self):
        try:
            super(_CheckLoginCall, self).request()
        except ResponseError, exc:
            if exc.error_code == 3 and \
                            exc.error_message == 'Invalid login or password.':
                self.response_data = False
            else:
                raise  # re-raises the last exception

    def clean(self):
        self.cleaned = bool(self.response_data)


class _MethodGetCall(BaseCall):
    method = prepend_base('method_get')

    def __init__(self, request_handler, method_name):
        super(_MethodGetCall, self).__init__(request_handler)
        self.method_name = method_name

    def validate(self):
        if self.method_name not in VALID_METHODS:
            raise ValidationError("Invalid method_name.")
        return True

    def build_request_data(self):
        self.request_data = {
            'method_name': self.method_name,
        }


class _MethodListCall(BaseCall):
    method = prepend_base('method_list')


# call functions with proper signatures and docstrings

@api_call
def api_export(table, gzip=False, order_by=None, request_handler=None):
    """Export table data in CSV format."""
    return _ApiExportCall(request_handler, table, gzip, order_by).render()


@api_call
def check_login(username='', password='', request_handler=None):
    """Check the specified username and password."""
    return _CheckLoginCall(request_handler, username, password).render()


@api_call
def method_get(method_name, request_handler=None):
    """Get the details of an API method."""
    return _MethodGetCall(request_handler, method_name).render()


@api_call
def method_list(request_handler=None):
    """Get a list of all available API methods."""
    return _MethodListCall(request_handler).render()
