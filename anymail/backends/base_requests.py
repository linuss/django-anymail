import json

import requests
# noinspection PyUnresolvedReferences
from six.moves.urllib.parse import urljoin

from .base import AnymailBaseBackend, BasePayload
from ..exceptions import AnymailRequestsAPIError, AnymailSerializationError
from .._version import __version__


class AnymailRequestsBackend(AnymailBaseBackend):
    """
    Base Anymail email backend for ESPs that use an HTTP API via requests
    """

    def __init__(self, api_url, **kwargs):
        """Init options from Django settings"""
        self.api_url = api_url
        super(AnymailRequestsBackend, self).__init__(**kwargs)
        self.session = None

    def open(self):
        if self.session:
            return False  # already exists

        try:
            self.session = requests.Session()
        except requests.RequestException:
            if not self.fail_silently:
                raise
        else:
            self.session.headers["User-Agent"] = "django-anymail/{version}-{esp} {orig}".format(
                esp=self.esp_name.lower(), version=__version__,
                orig=self.session.headers.get("User-Agent", ""))
            return True

    def close(self):
        if self.session is None:
            return
        try:
            self.session.close()
        except requests.RequestException:
            if not self.fail_silently:
                raise
        finally:
            self.session = None

    def _send(self, message):
        if self.session is None:
            class_name = self.__class__.__name__
            raise RuntimeError(
                "Session has not been opened in {class_name}._send. "
                "(This is either an implementation error in {class_name}, "
                "or you are incorrectly calling _send directly.)".format(class_name=class_name))
        return super(AnymailRequestsBackend, self)._send(message)

    def post_to_esp(self, payload, message):
        """Post payload to ESP send API endpoint, and return the raw response.

        payload is the result of build_message_payload
        message is the original EmailMessage
        return should be a requests.Response

        Can raise AnymailRequestsAPIError for HTTP errors in the post
        """
        params = payload.get_request_params(self.api_url)
        response = self.session.request(**params)
        self.raise_for_status(response, payload, message)
        return response

    def raise_for_status(self, response, payload, message):
        """Raise AnymailRequestsAPIError if response is an HTTP error

        Subclasses can override for custom error checking
        (though should defer parsing/deserialization of the body to
        parse_recipient_status)
        """
        if response.status_code != 200:
            raise AnymailRequestsAPIError(email_message=message, payload=payload, response=response)

    def deserialize_json_response(self, response, payload, message):
        """Deserialize an ESP API response that's in json.

        Useful for implementing deserialize_response
        """
        try:
            return response.json()
        except ValueError:
            raise AnymailRequestsAPIError("Invalid JSON in %s API response" % self.esp_name,
                                          email_message=message, payload=payload, response=response)


class RequestsPayload(BasePayload):
    """Abstract Payload for AnymailRequestsBackend"""

    def __init__(self, message, defaults, backend,
                 method="POST", params=None, data=None,
                 headers=None, files=None, auth=None):
        self.method = method
        self.params = params
        self.data = data
        self.headers = headers
        self.files = files
        self.auth = auth
        super(RequestsPayload, self).__init__(message, defaults, backend)

    def get_request_params(self, api_url):
        """Returns a dict of requests.request params that will send payload to the ESP.

        :param api_url: the base api_url for the backend
        :return: dict
        """
        api_endpoint = self.get_api_endpoint()
        if api_endpoint is not None:
            url = urljoin(api_url, api_endpoint)
        else:
            url = api_url

        return dict(
            method=self.method,
            url=url,
            params=self.params,
            data=self.serialize_data(),
            headers=self.headers,
            files=self.files,
            auth=self.auth,
            # json= is not here, because we prefer to do our own serialization
            #       to provide extra context in error messages
        )

    def get_api_endpoint(self):
        """Returns a str that should be joined to the backend's api_url for sending this payload."""
        return None

    def serialize_data(self):
        """Performs any necessary serialization on self.data, and returns the result."""
        return self.data

    def serialize_json(self, data):
        """Returns data serialized to json, raising appropriate errors.

        Useful for implementing serialize_data in a subclass,
        """
        try:
            return json.dumps(data)
        except TypeError as err:
            # Add some context to the "not JSON serializable" message
            raise AnymailSerializationError(orig_err=err, email_message=self.message,
                                            backend=self.backend, payload=self)
