import warnings

from django.core.mail import make_msgid
from requests.structures import CaseInsensitiveDict

from ..exceptions import AnymailConfigurationError, AnymailRequestsAPIError, AnymailWarning
from ..message import AnymailRecipientStatus
from ..utils import get_anymail_setting, timestamp

from .base_requests import AnymailRequestsBackend, RequestsPayload


class SendGridBackend(AnymailRequestsBackend):
    """
    SendGrid API Email Backend
    """

    def __init__(self, **kwargs):
        """Init options from Django settings"""
        # Auth requires *either* SENDGRID_API_KEY or SENDGRID_USERNAME+SENDGRID_PASSWORD
        esp_name = self.esp_name
        self.api_key = get_anymail_setting('api_key', esp_name=esp_name, kwargs=kwargs,
                                           default=None, allow_bare=True)
        self.username = get_anymail_setting('username', esp_name=esp_name, kwargs=kwargs,
                                            default=None, allow_bare=True)
        self.password = get_anymail_setting('password', esp_name=esp_name, kwargs=kwargs,
                                            default=None, allow_bare=True)
        if self.api_key is None and (self.username is None or self.password is None):
            raise AnymailConfigurationError(
                "You must set either SENDGRID_API_KEY or both SENDGRID_USERNAME and "
                "SENDGRID_PASSWORD in your Django ANYMAIL settings."
            )

        self.generate_message_id = get_anymail_setting('generate_message_id', esp_name=esp_name,
                                                       kwargs=kwargs, default=True)
        self.template_var_format = get_anymail_setting('template_var_format', esp_name=esp_name,
                                                       kwargs=kwargs, default=None)

        # This is SendGrid's Web API v2 (because the Web API v3 doesn't support sending)
        api_url = get_anymail_setting('api_url', esp_name=esp_name, kwargs=kwargs,
                                      default="https://api.sendgrid.com/api/")
        if not api_url.endswith("/"):
            api_url += "/"
        super(SendGridBackend, self).__init__(api_url, **kwargs)

    def build_message_payload(self, message, defaults):
        return SendGridPayload(message, defaults, self)

    def parse_recipient_status(self, response, payload, message):
        parsed_response = self.deserialize_json_response(response, payload, message)
        try:
            sendgrid_message = parsed_response["message"]
        except (KeyError, TypeError):
            raise AnymailRequestsAPIError("Invalid SendGrid API response format",
                                          email_message=message, payload=payload, response=response)
        if sendgrid_message != "success":
            errors = parsed_response.get("errors", [])
            raise AnymailRequestsAPIError("SendGrid send failed: '%s'" % "; ".join(errors),
                                          email_message=message, payload=payload, response=response)
        # Simulate a per-recipient status of "queued":
        status = AnymailRecipientStatus(message_id=payload.message_id, status="queued")
        return {recipient.email: status for recipient in payload.all_recipients}


class SendGridPayload(RequestsPayload):

    def __init__(self, message, defaults, backend, *args, **kwargs):
        self.all_recipients = []  # used for backend.parse_recipient_status
        self.generate_message_id = backend.generate_message_id
        self.message_id = None  # Message-ID -- assigned in serialize_data unless provided in headers
        self.smtpapi = {}  # SendGrid x-smtpapi field
        self.to_list = []  # late-bound 'to' field
        self.template_var_format = backend.template_var_format
        self.template_data = None  # late-bound per-recipient vars
        self.template_global_data = None

        http_headers = kwargs.pop('headers', {})
        query_params = kwargs.pop('params', {})
        if backend.api_key is not None:
            http_headers['Authorization'] = 'Bearer %s' % backend.api_key
        else:
            query_params['api_user'] = backend.username
            query_params['api_key'] = backend.password
        super(SendGridPayload, self).__init__(message, defaults, backend,
                                              params=query_params, headers=http_headers,
                                              *args, **kwargs)

    def get_api_endpoint(self):
        return "mail.send.json"

    def serialize_data(self):
        """Performs any necessary serialization on self.data, and returns the result."""

        if self.generate_message_id:
            self.ensure_message_id()

        self.build_template_data()
        if self.template_data is None:
            # Standard 'to' and 'toname' headers
            self.set_recipients('to', self.to_list)
        else:
            # Merge-friendly smtpapi 'to' field
            self.smtpapi['to'] = [email.address for email in self.to_list]
            self.all_recipients += self.to_list

        # Serialize x-smtpapi to json:
        if len(self.smtpapi) > 0:
            # If esp_extra was also used to set x-smtpapi, need to merge it
            if "x-smtpapi" in self.data:
                esp_extra_smtpapi = self.data["x-smtpapi"]
                for key, value in esp_extra_smtpapi.items():
                    if key == "filters":
                        # merge filters (else it's difficult to mix esp_extra with other features)
                        self.smtpapi.setdefault(key, {}).update(value)
                    else:
                        # all other keys replace any current value
                        self.smtpapi[key] = value
            self.data["x-smtpapi"] = self.serialize_json(self.smtpapi)
        elif "x-smtpapi" in self.data:
            self.data["x-smtpapi"] = self.serialize_json(self.data["x-smtpapi"])

        # Serialize extra headers to json:
        headers = self.data["headers"]
        self.data["headers"] = self.serialize_json(dict(headers.items()))

        return self.data

    def ensure_message_id(self):
        """Ensure message has a known Message-ID for later event tracking"""
        headers = self.data["headers"]
        if "Message-ID" not in headers:
            # Only make our own if caller hasn't already provided one
            headers["Message-ID"] = self.make_message_id()
        self.message_id = headers["Message-ID"]

        # Workaround for missing message ID (smtp-id) in SendGrid engagement events
        # (click and open tracking): because unique_args get merged into the raw event
        # record, we can supply the 'smtp-id' field for any events missing it.
        self.smtpapi.setdefault('unique_args', {})['smtp-id'] = self.message_id

    def make_message_id(self):
        """Returns a Message-ID that could be used for this payload

        Tries to use the from_email's domain as the Message-ID's domain
        """
        try:
            _, domain = self.data["from"].split("@")
        except (AttributeError, KeyError, TypeError, ValueError):
            domain = None
        return make_msgid(domain=domain)

    def build_template_data(self):
        """Set smtpapi['sub'] and ['section'] from template_data and to-list"""
        if self.template_data is not None:
            # Convert from {to1: {a: A1, b: B1}, to2: {a: A2}}  (template_data format)
            # to {a: [A1, A2], b: [B1, ""]}  ({var: [values in to-list order], ...})
            all_vars = set()
            for recipient_vars in self.template_data.values():
                all_vars = all_vars.union(recipient_vars.keys())
            recipients = [email.email for email in self.to_list]

            if self.template_var_format is None and all(var.isalnum() for var in all_vars):
                warnings.warn(
                    "Your SendGrid merge variables don't seem to have delimiters, "
                    "which can cause unexpected results with Anymail's template_data. "
                    "Search SENDGRID_TEMPLATE_VAR_FORMAT in the Anymail docs for more info.",
                    AnymailWarning)

            sub_var_fmt = self.template_var_format or '{}'
            sub_vars = {var: sub_var_fmt.format(var) for var in all_vars}

            self.smtpapi['sub'] = {
                # If var is missing for recipient, use (formatted) var as the substitution.
                # (This allows default to resolve from global "section" substitutions.)
                sub_vars[var]: [self.template_data.get(recipient, {}).get(var, sub_vars[var])
                                for recipient in recipients]
                for var in all_vars
            }

        if self.template_global_data is not None:
            section_var_fmt = self.template_var_format or '{}'
            self.smtpapi['section'] = {
                section_var_fmt.format(var): value
                for var, value in self.template_global_data.items()
            }

    #
    # Payload construction
    #

    def init_payload(self):
        self.data = {}  # {field: [multiple, values]}
        self.files = {}
        self.data['headers'] = CaseInsensitiveDict()  # headers keys are case-insensitive

    def set_from_email(self, email):
        self.data["from"] = email.email
        if email.name:
            self.data["fromname"] = email.name

    def set_to(self, emails):
        # late-bind in self.serialize_data, because whether it goes in smtpapi
        # depends on whether there is template_data
        self.to_list = emails

    def set_recipients(self, recipient_type, emails):
        assert recipient_type in ["to", "cc", "bcc"]
        if emails:
            self.data[recipient_type] = [email.email for email in emails]
            empty_name = " "  # SendGrid API balks on complete empty name fields
            self.data[recipient_type + "name"] = [email.name or empty_name for email in emails]
            self.all_recipients += emails  # used for backend.parse_recipient_status

    def set_subject(self, subject):
        self.data["subject"] = subject

    def set_reply_to(self, emails):
        # Note: SendGrid mangles the 'replyto' API param: it drops
        # all but the last email in a multi-address replyto, and
        # drops all the display names. [tested 2016-03-10]
        #
        # To avoid those quirks, we provide a fully-formed Reply-To
        # in the custom headers, which makes it through intact.
        if emails:
            reply_to = ", ".join([email.address for email in emails])
            self.data["headers"]["Reply-To"] = reply_to

    def set_extra_headers(self, headers):
        # SendGrid requires header values to be strings -- not integers.
        # We'll stringify ints and floats; anything else is the caller's responsibility.
        # (This field gets converted to json in self.serialize_data)
        self.data["headers"].update({
            k: str(v) if isinstance(v, (int, float)) else v
            for k, v in headers.items()
        })

    def set_text_body(self, body):
        self.data["text"] = body

    def set_html_body(self, body):
        if "html" in self.data:
            # second html body could show up through multiple alternatives, or html body + alternative
            self.unsupported_feature("multiple html parts")
        self.data["html"] = body

    def add_attachment(self, attachment):
        filename = attachment.name or ""
        if attachment.inline:
            filename = filename or attachment.cid  # must have non-empty name for the cid matching
            content_field = "content[%s]" % filename
            self.data[content_field] = attachment.cid

        files_field = "files[%s]" % filename
        if files_field in self.files:
            # It's possible SendGrid could actually handle this case (needs testing),
            # but requests doesn't seem to accept a list of tuples for a files field.
            # (See the MailgunBackend version for a different approach that might work.)
            self.unsupported_feature(
                "multiple attachments with the same filename ('%s')" % filename if filename
                else "multiple unnamed attachments")

        self.files[files_field] = (filename, attachment.content, attachment.mimetype)

    def set_metadata(self, metadata):
        self.smtpapi['unique_args'] = metadata

    def set_send_at(self, send_at):
        # Backend has converted pretty much everything to
        # a datetime by here; SendGrid expects unix timestamp
        self.smtpapi["send_at"] = int(timestamp(send_at))  # strip microseconds

    def set_tags(self, tags):
        self.smtpapi["category"] = tags

    def add_filter(self, filter_name, setting, val):
        self.smtpapi.setdefault('filters', {})\
            .setdefault(filter_name, {})\
            .setdefault('settings', {})[setting] = val

    def set_track_clicks(self, track_clicks):
        self.add_filter('clicktrack', 'enable', int(track_clicks))

    def set_track_opens(self, track_opens):
        # SendGrid's opentrack filter also supports a "replace"
        # parameter, which Anymail doesn't offer directly.
        # (You could add it through esp_extra.)
        self.add_filter('opentrack', 'enable', int(track_opens))

    def set_template_id(self, template_id):
        self.add_filter('templates', 'enable', 1)
        self.add_filter('templates', 'template_id', template_id)

    def set_template_data(self, template_data):
        # Must late-bind smtpapi['sub'] (in serialize_data) after we know the recipients
        # (Also, doesn't require the 'templates' filter; SendGrid will merge into message body.)
        self.template_data = template_data

    def set_template_global_data(self, template_global_data):
        # (Doesn't require the 'templates' filter; SendGrid will merge into message body.)
        self.template_global_data = template_global_data

    def set_esp_extra(self, extra):
        self.template_var_format = extra.pop('template_var_format',
                                             self.template_var_format)
        self.data.update(extra)
