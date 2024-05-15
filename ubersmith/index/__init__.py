"""Method index generation and management for Ubersmith API."""

from ubersmith.api import RequestHandler, get_default_request_handler
from time import sleep
import json
import os
import warnings

_DEFAULT_INDEX = None


class MethodIndex(object):
    """Method index for Ubersmith API."""

    @staticmethod
    def _get_index_directory():
        """Return the directory of the index."""
        module_path = os.path.dirname(__file__)
        return module_path

    @staticmethod
    def _format_name(version):
        """Return the formatted index name."""
        return "%s.json" % version

    def __init__(self, handler: RequestHandler = None):
        """Initialize method index with HTTP request handler."""
        self.handler: RequestHandler = handler or get_default_request_handler()
        self._wanted_index_name: str = self._format_name(handler.version)

        self.index_name: str = self._get_index_name()
        self._index_data: dict = self._get_index_data()

    @property
    def version(self):
        """Return the version of the Ubersmith API."""
        if self.index_name:
            return self.index_name.rpartition('.')[0]
        return 'Unknown'

    @property
    def _wanted_version(self):
        """Return the version of the Ubersmith API."""
        return self.handler.version

    @classmethod
    def _get_available_indexes(cls):
        """Return a list of available indexes."""
        return [f for f in os.listdir(cls._get_index_directory()) if f.endswith('.json')]

    def _get_latest_index(self):
        """Return the index with the latest version."""
        return sorted(
            self._get_available_indexes(),
            key=lambda x: tuple(map(int, x.rpartition('.')[0].split('.'))),
            reverse=True
        )[0]

    def _get_index_name(self):
        """Return the requested index or the latest index if not available."""
        if self._wanted_index_name in self._get_available_indexes():
            return self._wanted_index_name

        warnings.warn(
            "The requested version of the API is not available. "
            "Using the latest version instead: %s" % self.version
        )
        return self._get_latest_index()

    def _get_index_data(self):
        """Read the index from the file system."""
        with open(os.path.join(self._get_index_directory(), self.index_name), 'r') as f:
            return json.load(f)

    @classmethod
    def generate(cls, handler: RequestHandler, delay: float = 0.5,
                 force: bool = False, interactive: bool = False):
        """
        Generate the index for the current version.
        """
        # Sub-script for outputting data interactively
        def print_status(left_text, right_text):
            base_left_text = "Generating index for %s: " % handler.version
            print(base_left_text, left_text, flush=True, end=right_text)

        if interactive:
            print()
            print_status("Starting...", "")

        # Check whether the requested index already exists
        if cls._format_name(handler.version) in cls._get_available_indexes():
            text = "The index for the current version already exists."
            if interactive:
                print_status(text, "")
            else:
                warnings.warn(text)
            if not force:
                return False

        index_data = dict()

        if interactive:
            print_status("Querying method list...", "")

        # Get all methods
        all_methods = handler.process_request('uber.method_list')._data

        # Get all method details
        iteration = 0
        for method, _ in all_methods.items():
            iteration += 1
            if interactive:
                print_status(
                    "Querying method %s..." % method,
                    "[%i/%i]" % (iteration, len(all_methods))
                )
            module = method.partition('.')[0]
            try:
                method_data = handler.process_request('uber.method_get', {'method_name': method})._data
                _ = method_data.pop('output')

                if module not in index_data:
                    index_data[module] = dict()

                index_data[module][method] = method_data
            except Exception as e:
                warnings.warn("Failed to get method %s: %s" % (method, e))

            sleep(delay)

        if interactive:
            print_status("Writing index to disk...", "")

        # Write the index to the file system
        with open(os.path.join(cls._get_index_directory(), cls._format_name(handler.version)), 'w') as f:
            json.dump(index_data, f)

        if interactive:
            print_status("Done!", "")

        return cls(handler)

    def get_methods(self, module: str = None, as_list: bool = False):
        """Return the methods for the given module."""
        if module:
            if as_list:
                return list(self._index_data.get(module, {}).keys())
            return self._index_data.get(module, {})
        return self._index_data

    def get_method(self, method: str):
        """Return the details for the given method."""
        module = method.partition('.')[0]
        return self._index_data.get(module, {}).get(method, {})


def get_default_index():
    """Return the default method index."""
    if not _DEFAULT_INDEX:
        raise ValueError("Default index required but no default was found.")
    return _DEFAULT_INDEX


def set_default_index(index: MethodIndex = None):
    """Set the default method index."""
    if not isinstance(index, MethodIndex):
        index = MethodIndex(get_default_request_handler())
    global _DEFAULT_INDEX
    _DEFAULT_INDEX = index
