"""Lower level API, configuration, and HTTP stuff."""
import six
import time
from ubersmith.compat import total_ordering, file_type

import requests

from ubersmith.exceptions import (
    RequestError,
    ResponseError,
    UpdatingTokenResponse,
    MaintenanceResponse,
)
from ubersmith.utils import (
    append_qs,
    to_nested_php_args,
    get_filename,
    ObjDict,
)

__all__ = [
    'METHODS',
    'RequestHandler',
    'get_default_request_handler',
    'set_default_request_handler',
]

_DEFAULT_REQUEST_HANDLER = None

"""A dict of all methods returned by uber.method_list()"""
METHODS = {}


class _ProxyModule(object):
    def __init__(self, handler, module):
        self.handler = handler
        self.module = module

    def __getattr__(self, name):
        """Return the call with request_handler prefilled."""
        call_func = getattr(self.module, name)
        if callable(call_func):
            call_p = call_func.handler(self.handler)
            # store partial on proxy so it doesn't have to be created again
            setattr(self, name, call_p)
            return call_p
        raise AttributeError("'{0}' object has no attribute '{1}'".format(
            type(self).__name__, name))


class RequestHandler(object):
    """Handles HTTP requests and authentication."""

    def __init__(self, base_url, username=None, password=None, verify=True,
                 session=None):
        """Initialize HTTP request handler with optional authentication.

            base_url: URL to send API requests
            username: Username for API access
            password: Password for API access
            verify: Verify HTTPS certificate
            session: requests.Session to send requests with

        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify = verify

        if not isinstance(session, requests.Session):
            session = requests.session()
        self._session = session

        # Fetch list of methods, and store to self
        self.METHODS = {'uber.method_list': 'List Available API Methods'}
        self.METHODS.update(self.process_request('uber.method_list')._data)

        # Store target Ubersmith version to self
        try:
            system_info = self.process_request('uber.system_info')._data
        except ResponseError:
            system_info = dict()
        self.version = system_info.get('version', 'Unknown')
        self._latest_version = system_info.get('latest_version', 'Unknown')

    @property
    def session(self):
        return self._session

    def process_request(self, method, data=None):
        """Process request over HTTP to ubersmith instance.

            method: Ubersmith API method string
            data: dict of method arguments

        """
        # make sure requested method is valid
        self._validate_request_method(method)

        # attempt the request multiple times
        attempts = 3
        for i in range(attempts):
            response = self._send_request(method, data)

            # handle case where ubersmith is 'updating token'
            # see: https://github.com/jasonkeene/python-ubersmith/issues/1
            if self._is_token_response(response):
                if i < attempts - 1:
                    # wait 2 secs before retrying request
                    time.sleep(2)
                    continue
                else:
                    raise UpdatingTokenResponse
            break

        resp = BaseResponse(response)

        # test for error in json response
        if response.headers.get('content-type') == 'application/json':
            if not resp._json.get('status'):
                if all([
                    resp._json.get('error_code') == 1,
                    resp._json.get('error_message') == u"We are currently "
                        "undergoing maintenance, please check back shortly.",
                ]):
                    raise MaintenanceResponse(response=resp._json)
                else:
                    raise ResponseError(response=resp._json)
        return resp

    @staticmethod
    def _is_token_response(response):
        return ('text/html' in response.headers.get('content-type', '') and
                'Updating Token' in response.content)

    def _send_request(self, method, data):
        url = append_qs(self.base_url, {'method': method})
        data, files, headers = self._encode_data(data)
        return self.session.post(url, data=data, files=files, headers=headers,
                                 auth=(self.username, self.password),
                                 verify=self.verify)

    def _validate_request_method(self, method):
        """Make sure requested method is valid."""
        if method not in self.METHODS:
            raise RequestError("Requested method is not valid.")

    @staticmethod
    def _encode_data(data):
        """URL encode data."""
        data = data if data is not None else {}
        data = to_nested_php_args(data)
        files = dict([
            (key, value) for key, value in
            data.items() if isinstance(value, file_type)])
        for fname in files:
            del data[fname]
        return data, files or None, None

    def __getattr__(self, name):
        """If attribute accessed is a call module, return a proxy."""
        if name in set(m.split('.')[0] for m in self.METHODS):
            module_name = 'ubersmith.{0}'.format(name)
            module = __import__(module_name, fromlist=[''])
            proxy = _ProxyModule(self, module)
            # store proxy on handler so it doesn't have to be created again
            setattr(self, name, proxy)
            return proxy
        raise AttributeError("'{0}' object has no attribute '{1}'".format(
            type(self).__name__, name))


class BaseResponse(object):
    """Wraps response object and emulates different types."""
    def __init__(self, response):
        self._response = response  # requests' response object

    @classmethod
    def _from_cleaned(cls, response, cleaned):
        resp = cls(response._response)
        resp._cleaned = cleaned
        return resp

    @property
    def _json(self):
        return self._response.json()

    @property
    def _data(self):
        if hasattr(self, "_cleaned"):
            data = self._cleaned
        else:
            data = self._json['data']
        return ObjDict(data)

    @property
    def _type(self):
        return self._response.headers.get('content-type')

    def __str__(self):
        return str(self._data)

    def __repr__(self):
        return repr(self._data)

    def __nonzero__(self):
        return bool(self._data)

    def __json__(self):
        """This method returns the JSON-serializable representation of the
        Response. To utilize this, create a JSONEncoder which calls the
        __json__ methods of supporting objects. e.g.::

            import json
            class MyJSONEncoder(json.JSONEncoder):
                def default(self, o):
                    if hasattr(obj, '__json__') and callable(obj.__json__):
                        return obj.__json__()
                    else:
                        return super(MyJSONEncoder, self).default(o)

            json.dumps(my_response, cls=MyJSONEncoder)
        """
        return self._data

    def __getattr__(self, attr):
        if attr.startswith('_'):
            return super().__getattribute__(attr)
        return getattr(self._data, attr)

    def __getitem__(self, item):
        return self._data[item]


@total_ordering
class DictResponse(BaseResponse):
    __marker = object()

    def keys(self):
        return self._data.keys()

    def iterkeys(self):
        return six.iterkeys(self._data)

    def values(self):
        return self._data.values()

    def itervalues(self):
        return six.itervalues(self._data)

    def items(self):
        return self._data.items()

    def iteritems(self):
        return six.iteritems(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def update(self, d):
        self._data.update(d)

    def setdefault(self, key, value):
        self._data.setdefault(key, value)

    def pop(self, key, default=__marker):
        if default is self.__marker:
            return self._data.pop(key)
        else:
            return self._data.pop(key, default)

    def popitem(self):
        return self._data.popitem()

    def clear(self):
        self._data.clear()

    def __setitem__(self, key, value):
        self._data[key] = value

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __eq__(self, other):
        return self._data == other

    def __lt__(self, other):
        return self._data < other

    def __contains__(self, item):
        return item in self._data


@total_ordering
class IntResponse(BaseResponse):
    @property
    def numerator(self):
        return self._data

    @property
    def denominator(self):
        return 1

    @property
    def real(self):
        return self._data

    @property
    def imag(self):
        return 0

    def bit_length(self):
        if hasattr(self._data, 'bit_length'):
            return self._data.bit_length()
        else:
            return len(bin(abs(self._data))) - 2

    def conjugate(self):
        return self._data

    def __int__(self):
        return self._data
    __index__ = __long__ = __trunc__ = __int__

    def __float__(self):
        return float(self._data)

    def __oct__(self):
        return oct(self._data)

    def __hex__(self):
        return hex(self._data)

    def __eq__(self, other):
        return self._data == other

    def __lt__(self, other):
        return self._data < other

    def __add__(self, other):
        return int(self) + other
    __radd__ = __add__

    def __sub__(self, other):
        return int(self) - other

    def __rsub__(self, other):
        return other - int(self)

    def __mul__(self, other):
        return int(self) * other
    __rmul__ = __mul__

    def __div__(self, other):
        return int(self) / other

    def __rdiv__(self, other):
        return other / int(self)

    def __floordiv__(self, other):
        return int(self) // other

    def __rfloordiv__(self, other):
        return other // int(self)

    def __truediv__(self, other):
        return float(self) / other

    def __rtruediv__(self, other):
        return other / float(self)

    def __mod__(self, other):
        return int(self) % other

    def __rmod__(self, other):
        return other % int(self)

    def __pow__(self, other):
        return int(self) ** other

    def __rpow__(self, other):
        return other ** int(self)

    def __abs__(self):
        return abs(self._data)

    def __neg__(self):
        return -self._data

    def __pos__(self):
        return self._data

    def __divmod__(self, other):
        return self // other, self % other

    def __rdivmod__(self, other):
        return other // self, other % self

    def __and__(self, other):
        return self._data & other
    __rand__ = __and__

    def __or__(self, other):
        return self._data | other
    __ror__ = __or__

    def __xor__(self, other):
        return self._data ^ other
    __rxor__ = __xor__

    def __lshift__(self, other):
        return self._data << other

    def __rlshift__(self, other):
        return other << self._data

    def __rshift__(self, other):
        return self._data >> other

    def __rrshift__(self, other):
        return other >> self._data

    def __invert__(self):
        return ~self._data

    def __nonzero__(self):
        return bool(self._data)


class FileResponse(BaseResponse):
    @property
    def _json(self):
        raise NotImplementedError

    @property
    def _data(self):
        return self._response.content

    @property
    def filename(self):
        disposition = self._response.headers.get('content-disposition')
        return get_filename(disposition)


def get_default_request_handler():
    """Return the default request handler."""
    if not _DEFAULT_REQUEST_HANDLER:
        raise Exception("Request handler required but no default was found.")
    return _DEFAULT_REQUEST_HANDLER


def set_default_request_handler(request_handler):
    """Set the default request handler."""
    if not isinstance(request_handler, RequestHandler):
        raise TypeError(
            "Attempted to set an invalid request handler as default.")
    global _DEFAULT_REQUEST_HANDLER
    _DEFAULT_REQUEST_HANDLER = request_handler
