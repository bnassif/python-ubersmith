import copy

from six import string_types
import json

from ubersmith.api import (
    METHODS,
    BaseResponse,
    DictResponse,
    IntResponse,
    FileResponse,
    get_default_request_handler,
)
from ubersmith.exceptions import ValidationError
from ubersmith.index import MethodIndex, get_default_index

__all__ = [
    # abstract call classes
    'BaseCall',
    # generate generic calls
    'generate_generic_calls',
]


class BaseCall(object):
    """Abstract class to implement a call with validation/cleaning/etc."""

    method = ''  # ubersmith method name, should be defined on child classes
    required_fields = []  # field names that should be present in request_data
    cleaner = None  # function to clean response (see ubersmith.clean)

    def __init__(self, request_data=None, request_handler=None):
        """Setup call with provided request data and handler."""
        self.request_data = request_data or {}  # data for the request
        self.request_handler = request_handler or \
            get_default_request_handler()  # handler to fullfil the request
        self.response = None  # response is stored here

    def render(self):
        """Validate, process, clean and return the result of the call."""
        if not self.validate():
            raise ValidationError

        self.process_request()
        # self.clean()

        return self.response

    def validate(self):
        """Validate request data before sending it out. Return True/False."""
        # check if required_fields aren't present
        for field in set(self.required_fields) - set(self.request_data):
            if not isinstance(field, string_types):
                # field was a collection, iterate over it and check by OR
                return bool(set(field) & set(self.request_data))
            return False
        return True

    def process_request(self):
        """Processing the call and set response_data."""
        self.response = self.request_handler.process_request(
            self.method, self.request_data)

    def clean(self):
        """Clean response."""
        if self.response._type == 'application/json':
            cleaned = copy.deepcopy(self.response._data)
            if self.cleaner is not None:
                cleaned = self.cleaner(cleaned)

            typed_response = {
                dict: DictResponse,
                int: IntResponse,
            }.get(type(cleaned), BaseResponse)
            self.response = typed_response._from_cleaned(self.response, cleaned)
        else:
            self.response = FileResponse(self.response._response)


def _get_defined_calls(module):
    """Return all the defined call classes."""
    module_members = (getattr(module, x) for x in dir(module) if not x.startswith('_'))
    return [x for x in module_members if type(x) is type and issubclass(x, BaseCall)]

def _get_call_class(method):
    """Find the call class for method if it exists else create one."""
    call_base, call_name = method.split('.', 1)

    class GenericBaseCall(BaseCall):
        method = '.'.join((call_base, call_name))
    return GenericBaseCall


class GenericCall(object):
    def __init__(self, call_class, request_handler=None):
        self.call_class = call_class
        self.request_handler = request_handler

    def handler(self, request_handler):
        """Return new GenericCall that is bound to a request handler."""
        return GenericCall(self.call_class, request_handler)

    def __call__(self, **kwargs):

        return self.call_class(kwargs, self.request_handler).render()


def generate_generic_calls(base, ns, index: MethodIndex = None):
    # Load the Index object
    index = index or get_default_index()

    # Get all methods for the base module (client, device, etc)
    methods = index.get_methods(base)

    for method, method_data in methods.items():
        module, call_name = method.split('.')
        # find the appropriate class
        call_class = _get_call_class(method_data['method'])
        # create a call function and stick it in the namespace
        generic_call = GenericCall(call_class)
        generic_call.__name__ = str(call_name)
        generic_call.__doc__ = method_data.get('description', '')
        # this may or may not be a good idea, see:
        # http://stackoverflow.com/questions/10113892/semantics-of-module
        # generic_call.__module__ = 'ubersmith.{0}'.format(base)
        ns[call_name] = generic_call
        # add call to __all__ if needed
        if '__all__' in ns and call_name not in ns['__all__']:
            ns['__all__'].append(call_name)