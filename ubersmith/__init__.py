from ubersmith.api import RequestHandler, set_default_request_handler
from ubersmith.index import MethodIndex, get_default_index, set_default_index
from ubersmith import (
    api,
    exceptions,
    utils,
    calls,
)

__all__ = [
    # package modules
    'api',
    'exceptions',
    'utils',
    # call classes
    'calls',
    # init function
    'init',
]


def init(base_url, username=None, password=None, verify=True):
    """Initialize ubersmith API module with HTTP request handler."""
    handler = RequestHandler(base_url, username, password, verify)
    set_default_request_handler(handler)
    set_default_index(MethodIndex(handler))
    from ubersmith import (
        client,
        device,
        order,
        sales,
        support,
        uber,
    )
    __all__.append(
        ['client', 'device', 'order', 'sales', 'support', 'uber']
    )
    return handler
