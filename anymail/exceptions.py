import json

from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from requests import HTTPError


class AnymailError(Exception):
    """Base class for exceptions raised by Anymail

    Overrides __str__ to provide additional information about
    the ESP API call and response.
    """

    def __init__(self, *args, **kwargs):
        """
        Optional kwargs:
          email_message: the original EmailMessage being sent
          status_code: HTTP status code of response to ESP send call
          payload: data arg (*not* json-stringified) for the ESP send call
          response: requests.Response from the send call
        """
        self.backend = kwargs.pop('backend', None)
        self.email_message = kwargs.pop('email_message', None)
        self.payload = kwargs.pop('payload', None)
        self.status_code = kwargs.pop('status_code', None)
        if isinstance(self, HTTPError):
            # must leave response in kwargs for HTTPError
            self.response = kwargs.get('response', None)
        else:
            self.response = kwargs.pop('response', None)
        super(AnymailError, self).__init__(*args, **kwargs)

    def __str__(self):
        parts = [
            " ".join([str(arg) for arg in self.args]),
            self.describe_send(),
            self.describe_response(),
        ]
        return "\n".join(filter(None, parts))

    def describe_send(self):
        """Return a string describing the ESP send in self.email_message, or None"""
        if self.email_message is None:
            return None
        description = "Sending a message"
        try:
            description += " to %s" % ','.join(self.email_message.to)
        except AttributeError:
            pass
        try:
            description += " from %s" % self.email_message.from_email
        except AttributeError:
            pass
        return description

    def describe_response(self):
        """Return a formatted string of self.status_code and response, or None"""
        if self.status_code is None:
            return None
        description = "ESP API response %d:" % self.status_code
        try:
            json_response = self.response.json()
            description += "\n" + json.dumps(json_response, indent=2)
        except (AttributeError, KeyError, ValueError):  # not JSON = ValueError
            try:
                description += " " + self.response.text
            except AttributeError:
                pass
        return description


class AnymailAPIError(AnymailError):
    """Exception for unsuccessful response from ESP's API."""


class AnymailRequestsAPIError(AnymailAPIError, HTTPError):
    """Exception for unsuccessful response from a requests API."""

    def __init__(self, *args, **kwargs):
        super(AnymailRequestsAPIError, self).__init__(*args, **kwargs)
        if self.response is not None:
            self.status_code = self.response.status_code


class AnymailRecipientsRefused(AnymailError):
    """Exception for send where all recipients are invalid or rejected."""

    def __init__(self, message=None, *args, **kwargs):
        if message is None:
            message = "All message recipients were rejected or invalid"
        super(AnymailRecipientsRefused, self).__init__(message, *args, **kwargs)


class AnymailUnsupportedFeature(AnymailError, ValueError):
    """Exception for Anymail features that the ESP doesn't support.

    This is typically raised when attempting to send a Django EmailMessage that
    uses options or values you might expect to work, but that are silently
    ignored by or can't be communicated to the ESP's API.

    It's generally *not* raised for ESP-specific limitations, like the number
    of tags allowed on a message. (Anymail expects
    the ESP to return an API error for these where appropriate, and tries to
    avoid duplicating each ESP's validation logic locally.)

    """


class AnymailSerializationError(AnymailError, TypeError):
    """Exception for data that Anymail can't serialize for the ESP's API.

    This typically results from including something like a date or Decimal
    in your merge_vars.

    """
    # inherits from TypeError for compatibility with JSON serialization error

    def __init__(self, message=None, orig_err=None, *args, **kwargs):
        if message is None:
            esp_name = kwargs["backend"].esp_name if "backend" in kwargs else "the ESP"
            message = "Don't know how to send this data to %s. " \
                      "Try converting it to a string or number first." % esp_name
        if orig_err is not None:
            message += "\n%s" % str(orig_err)
        super(AnymailSerializationError, self).__init__(message, *args, **kwargs)


class AnymailWebhookValidationFailure(AnymailError, SuspiciousOperation):
    """Exception when a webhook cannot be validated.

    Django's SuspiciousOperation turns into
    an HTTP 400 error in production.
    """


class AnymailConfigurationError(ImproperlyConfigured):
    """Exception for Anymail configuration or installation issues"""
    # This deliberately doesn't inherit from AnymailError,
    # because we don't want it to be swallowed by backend fail_silently


class AnymailImproperlyInstalled(AnymailConfigurationError, ImportError):
    """Exception for Anymail missing package dependencies"""

    def __init__(self, missing_package, backend="<backend>"):
        message = "The %s package is required to use this backend, but isn't installed.\n" \
                  "(Be sure to use `pip install django-anymail[%s]` " \
                  "with your desired backends)" % (missing_package, backend)
        super(AnymailImproperlyInstalled, self).__init__(message)


# Warnings

class AnymailWarning(Warning):
    """Base warning for Anymail"""


class AnymailInsecureWebhookWarning(AnymailWarning):
    """Warns when webhook configured without any validation"""
