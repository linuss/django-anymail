# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from datetime import date, datetime
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.utils.timezone import get_fixed_timezone, override as override_current_timezone

from anymail.exceptions import AnymailAPIError, AnymailUnsupportedFeature
from anymail.message import attach_inline_image_file

from .mock_requests_backend import RequestsBackendMockAPITestCase, SessionSharingTestCasesMixin
from .utils import sample_image_content, sample_image_path, SAMPLE_IMAGE_FILENAME, AnymailTestMixin


@override_settings(EMAIL_BACKEND='anymail.backends.mailgun.MailgunBackend',
                   ANYMAIL={'MAILGUN_API_KEY': 'test_api_key'})
class MailgunBackendMockAPITestCase(RequestsBackendMockAPITestCase):
    DEFAULT_RAW_RESPONSE = b"""{
        "id": "<20160306015544.116301.25145@example.com>",
        "message": "Queued. Thank you."
    }"""

    def setUp(self):
        super(MailgunBackendMockAPITestCase, self).setUp()
        # Simple message useful for many tests
        self.message = mail.EmailMultiAlternatives('Subject', 'Text Body', 'from@example.com', ['to@example.com'])


class MailgunBackendStandardEmailTests(MailgunBackendMockAPITestCase):
    """Test backend support for Django standard email features"""

    def test_send_mail(self):
        """Test basic API for simple send"""
        mail.send_mail('Subject here', 'Here is the message.',
                       'from@example.com', ['to@example.com'], fail_silently=False)
        self.assert_esp_called('/example.com/messages')
        auth = self.get_api_call_auth()
        self.assertEqual(auth, ('api', 'test_api_key'))
        data = self.get_api_call_data()
        self.assertEqual(data['subject'], "Subject here")
        self.assertEqual(data['text'], "Here is the message.")
        self.assertEqual(data['from'], "from@example.com")
        self.assertEqual(data['to'], ["to@example.com"])

    def test_name_addr(self):
        """Make sure RFC2822 name-addr format (with display-name) is allowed

        (Test both sender and recipient addresses)
        """
        msg = mail.EmailMessage(
            'Subject', 'Message', 'From Name <from@example.com>',
            ['Recipient #1 <to1@example.com>', 'to2@example.com'],
            cc=['Carbon Copy <cc1@example.com>', 'cc2@example.com'],
            bcc=['Blind Copy <bcc1@example.com>', 'bcc2@example.com'])
        msg.send()
        data = self.get_api_call_data()
        self.assertEqual(data['from'], "From Name <from@example.com>")
        self.assertEqual(data['to'], ['Recipient #1 <to1@example.com>', 'to2@example.com'])
        self.assertEqual(data['cc'], ['Carbon Copy <cc1@example.com>', 'cc2@example.com'])
        self.assertEqual(data['bcc'], ['Blind Copy <bcc1@example.com>', 'bcc2@example.com'])

    def test_email_message(self):
        email = mail.EmailMessage(
            'Subject', 'Body goes here', 'from@example.com',
            ['to1@example.com', 'Also To <to2@example.com>'],
            bcc=['bcc1@example.com', 'Also BCC <bcc2@example.com>'],
            cc=['cc1@example.com', 'Also CC <cc2@example.com>'],
            headers={'Reply-To': 'another@example.com',
                     'X-MyHeader': 'my value',
                     'Message-ID': 'mycustommsgid@example.com'})
        email.send()
        data = self.get_api_call_data()
        self.assertEqual(data['subject'], "Subject")
        self.assertEqual(data['text'], "Body goes here")
        self.assertEqual(data['from'], "from@example.com")
        self.assertEqual(data['to'], ['to1@example.com', 'Also To <to2@example.com>'])
        self.assertEqual(data['bcc'], ['bcc1@example.com', 'Also BCC <bcc2@example.com>'])
        self.assertEqual(data['cc'], ['cc1@example.com', 'Also CC <cc2@example.com>'])
        self.assertEqual(data['h:Reply-To'], "another@example.com")
        self.assertEqual(data['h:X-MyHeader'], 'my value')
        self.assertEqual(data['h:Message-ID'], 'mycustommsgid@example.com')

    def test_html_message(self):
        text_content = 'This is an important message.'
        html_content = '<p>This is an <strong>important</strong> message.</p>'
        email = mail.EmailMultiAlternatives('Subject', text_content,
                                            'from@example.com', ['to@example.com'])
        email.attach_alternative(html_content, "text/html")
        email.send()
        data = self.get_api_call_data()
        self.assertEqual(data['text'], text_content)
        self.assertEqual(data['html'], html_content)
        # Don't accidentally send the html part as an attachment:
        files = self.get_api_call_files(required=False)
        self.assertIsNone(files)

    def test_html_only_message(self):
        html_content = '<p>This is an <strong>important</strong> message.</p>'
        email = mail.EmailMessage('Subject', html_content, 'from@example.com', ['to@example.com'])
        email.content_subtype = "html"  # Main content is now text/html
        email.send()
        data = self.get_api_call_data()
        self.assertNotIn('text', data)
        self.assertEqual(data['html'], html_content)

    def test_reply_to(self):
        email = mail.EmailMessage('Subject', 'Body goes here', 'from@example.com', ['to1@example.com'],
                                  reply_to=['reply@example.com', 'Other <reply2@example.com>'],
                                  headers={'X-Other': 'Keep'})
        email.send()
        data = self.get_api_call_data()
        self.assertEqual(data['h:Reply-To'], 'reply@example.com, Other <reply2@example.com>')
        self.assertEqual(data['h:X-Other'], 'Keep')  # don't lose other headers

    def test_attachments(self):
        text_content = "* Item one\n* Item two\n* Item three"
        self.message.attach(filename="test.txt", content=text_content, mimetype="text/plain")

        # Should guess mimetype if not provided...
        png_content = b"PNG\xb4 pretend this is the contents of a png file"
        self.message.attach(filename="test.png", content=png_content)

        # Should work with a MIMEBase object (also tests no filename)...
        pdf_content = b"PDF\xb4 pretend this is valid pdf data"
        mimeattachment = MIMEBase('application', 'pdf')
        mimeattachment.set_payload(pdf_content)
        self.message.attach(mimeattachment)

        self.message.send()
        files = self.get_api_call_files()
        attachments = [value for (field, value) in files if field == 'attachment']
        self.assertEqual(len(attachments), 3)
        self.assertEqual(attachments[0], ('test.txt', text_content, 'text/plain'))
        self.assertEqual(attachments[1], ('test.png', png_content, 'image/png'))  # type inferred from filename
        self.assertEqual(attachments[2], (None, pdf_content, 'application/pdf'))  # no filename
        # Make sure the image attachment is not treated as embedded:
        inlines = [value for (field, value) in files if field == 'inline']
        self.assertEqual(len(inlines), 0)

    def test_unicode_attachment_correctly_decoded(self):
        # Slight modification from the Django unicode docs:
        # http://django.readthedocs.org/en/latest/ref/unicode.html#email
        self.message.attach("Une pièce jointe.html", '<p>\u2019</p>', mimetype='text/html')
        self.message.send()
        files = self.get_api_call_files()
        attachments = [value for (field, value) in files if field == 'attachment']
        self.assertEqual(len(attachments), 1)

    def test_embedded_images(self):
        image_filename = SAMPLE_IMAGE_FILENAME
        image_path = sample_image_path(image_filename)
        image_data = sample_image_content(image_filename)

        cid = attach_inline_image_file(self.message, image_path)
        html_content = '<p>This has an <img src="cid:%s" alt="inline" /> image.</p>' % cid
        self.message.attach_alternative(html_content, "text/html")

        self.message.send()
        data = self.get_api_call_data()
        self.assertEqual(data['html'], html_content)

        files = self.get_api_call_files()
        inlines = [value for (field, value) in files if field == 'inline']
        self.assertEqual(len(inlines), 1)
        self.assertEqual(inlines[0], (cid, image_data, "image/png"))  # filename is cid; type is guessed
        # Make sure neither the html nor the inline image is treated as an attachment:
        attachments = [value for (field, value) in files if field == 'attachment']
        self.assertEqual(len(attachments), 0)

    def test_attached_images(self):
        image_filename = SAMPLE_IMAGE_FILENAME
        image_path = sample_image_path(image_filename)
        image_data = sample_image_content(image_filename)

        self.message.attach_file(image_path)  # option 1: attach as a file

        image = MIMEImage(image_data)  # option 2: construct the MIMEImage and attach it directly
        self.message.attach(image)

        self.message.send()
        files = self.get_api_call_files()
        attachments = [value for (field, value) in files if field == 'attachment']
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0], (image_filename, image_data, 'image/png'))
        self.assertEqual(attachments[1], (None, image_data, 'image/png'))  # name unknown -- not attached as file
        # Make sure the image attachments are not treated as inline:
        inlines = [value for (field, value) in files if field == 'inline']
        self.assertEqual(len(inlines), 0)

    def test_multiple_html_alternatives(self):
        # Multiple alternatives not allowed
        self.message.attach_alternative("<p>First html is OK</p>", "text/html")
        self.message.attach_alternative("<p>But not second html</p>", "text/html")
        with self.assertRaises(AnymailUnsupportedFeature):
            self.message.send()

    def test_html_alternative(self):
        # Only html alternatives allowed
        self.message.attach_alternative("{'not': 'allowed'}", "application/json")
        with self.assertRaises(AnymailUnsupportedFeature):
            self.message.send()

    def test_alternatives_fail_silently(self):
        # Make sure fail_silently is respected
        self.message.attach_alternative("{'not': 'allowed'}", "application/json")
        sent = self.message.send(fail_silently=True)
        self.assert_esp_not_called("API should not be called when send fails silently")
        self.assertEqual(sent, 0)

    def test_suppress_empty_address_lists(self):
        """Empty to, cc, bcc, and reply_to shouldn't generate empty headers"""
        self.message.send()
        data = self.get_api_call_data()
        self.assertNotIn('cc', data)
        self.assertNotIn('bcc', data)
        self.assertNotIn('h:Reply-To', data)

        # Test empty `to` -- but send requires at least one recipient somewhere (like cc)
        self.message.to = []
        self.message.cc = ['cc@example.com']
        self.message.send()
        data = self.get_api_call_data()
        self.assertNotIn('to', data)

    def test_api_failure(self):
        self.set_mock_response(status_code=400)
        with self.assertRaises(AnymailAPIError):
            sent = mail.send_mail('Subject', 'Body', 'from@example.com', ['to@example.com'])
            self.assertEqual(sent, 0)

        # Make sure fail_silently is respected
        self.set_mock_response(status_code=400)
        sent = mail.send_mail('Subject', 'Body', 'from@example.com', ['to@example.com'], fail_silently=True)
        self.assertEqual(sent, 0)

    def test_api_error_includes_details(self):
        """AnymailAPIError should include ESP's error message"""
        # JSON error response:
        error_response = b"""{"message": "Helpful explanation from your ESP"}"""
        self.set_mock_response(status_code=400, raw=error_response)
        with self.assertRaisesMessage(AnymailAPIError, "Helpful explanation from your ESP"):
            self.message.send()

        # Non-JSON error response:
        self.set_mock_response(status_code=500, raw=b"Invalid API key")
        with self.assertRaisesMessage(AnymailAPIError, "Invalid API key"):
            self.message.send()

        # No content in the error response:
        self.set_mock_response(status_code=502, raw=None)
        with self.assertRaises(AnymailAPIError):
            self.message.send()


class MailgunBackendAnymailFeatureTests(MailgunBackendMockAPITestCase):
    """Test backend support for Anymail added features"""

    def test_metadata(self):
        # Each metadata value is just a string; you can serialize your own JSON if you'd like.
        # (The Mailgun docs are a little confusing on this point.)
        self.message.metadata = {'user_id': "12345", 'items': '["mail","gun"]'}
        self.message.send()
        data = self.get_api_call_data()
        self.assertEqual(data['v:user_id'], '12345')
        self.assertEqual(data['v:items'], '["mail","gun"]')

    def test_send_at(self):
        utc_plus_6 = get_fixed_timezone(6 * 60)
        utc_minus_8 = get_fixed_timezone(-8 * 60)

        with override_current_timezone(utc_plus_6):
            # Timezone-aware datetime converted to UTC:
            self.message.send_at = datetime(2016, 3, 4, 5, 6, 7, tzinfo=utc_minus_8)
            self.message.send()
            data = self.get_api_call_data()
            self.assertEqual(data['o:deliverytime'], "Fri, 04 Mar 2016 13:06:07 GMT")  # 05:06 UTC-8 == 13:06 UTC

            # Timezone-naive datetime assumed to be Django current_timezone
            self.message.send_at = datetime(2022, 10, 11, 12, 13, 14, 567)
            self.message.send()
            data = self.get_api_call_data()
            self.assertEqual(data['o:deliverytime'], "Tue, 11 Oct 2022 06:13:14 GMT")  # 12:13 UTC+6 == 06:13 UTC

            # Date-only treated as midnight in current timezone
            self.message.send_at = date(2022, 10, 22)
            self.message.send()
            data = self.get_api_call_data()
            self.assertEqual(data['o:deliverytime'], "Fri, 21 Oct 2022 18:00:00 GMT")  # 00:00 UTC+6 == 18:00-1d UTC

            # POSIX timestamp
            self.message.send_at = 1651820889  # 2022-05-06 07:08:09 UTC
            self.message.send()
            data = self.get_api_call_data()
            self.assertEqual(data['o:deliverytime'], "Fri, 06 May 2022 07:08:09 GMT")

            # String passed unchanged (this is *not* portable between ESPs)
            self.message.send_at = "Thu, 13 Oct 2022 18:02:00 GMT"
            self.message.send()
            data = self.get_api_call_data()
            self.assertEqual(data['o:deliverytime'], "Thu, 13 Oct 2022 18:02:00 GMT")

    def test_tags(self):
        self.message.tags = ["receipt", "repeat-user"]
        self.message.send()
        data = self.get_api_call_data()
        self.assertEqual(data['o:tag'], ["receipt", "repeat-user"])

    def test_tracking(self):
        # Test one way...
        self.message.track_opens = True
        self.message.track_clicks = False
        self.message.send()
        data = self.get_api_call_data()
        self.assertEqual(data['o:tracking-opens'], 'yes')
        self.assertEqual(data['o:tracking-clicks'], 'no')

        # ...and the opposite way
        self.message.track_opens = False
        self.message.track_clicks = True
        self.message.send()
        data = self.get_api_call_data()
        self.assertEqual(data['o:tracking-opens'], 'no')
        self.assertEqual(data['o:tracking-clicks'], 'yes')

    # template_id: Mailgun doesn't support stored templates

    def test_merge_data(self):
        self.message.to = ['alice@example.com', 'Bob <bob@example.com>']
        self.message.body = "Hi %recipient.name%. Welcome to %recipient.group% at %recipient.site%."
        self.message.merge_data = {
            'alice@example.com': {'name': "Alice", 'group': "Developers"},
            'bob@example.com': {'name': "Bob"},  # and leave group undefined
        }
        self.message.merge_global_data = {
            'group': "Users",  # default
            'site': "ExampleCo",
        }
        self.message.send()
        data = self.get_api_call_data()
        self.assertJSONEqual(data['recipient-variables'], {
            'alice@example.com': {'name': "Alice", 'group': "Developers", 'site': "ExampleCo"},
            'bob@example.com': {'name': "Bob", 'group': "Users", 'site': "ExampleCo"},
        })
        # Make sure we didn't modify original dicts on message:
        self.assertEqual(self.message.merge_data, {
            'alice@example.com': {'name': "Alice", 'group': "Developers"},
            'bob@example.com': {'name': "Bob"},
        })
        self.assertEqual(self.message.merge_global_data, {'group': "Users", 'site': "ExampleCo"})

    def test_only_merge_global_data(self):
        # Make sure merge_global_data distributed to recipient-variables
        # even when merge_data not set
        self.message.to = ['alice@example.com', 'Bob <bob@example.com>']
        self.message.merge_global_data = {'test': "value"}
        self.message.send()
        data = self.get_api_call_data()
        self.assertJSONEqual(data['recipient-variables'], {
            'alice@example.com': {'test': "value"},
            'bob@example.com': {'test': "value"},
        })

    def test_sender_domain(self):
        """Mailgun send domain can come from from_email or esp_extra"""
        # You could also use ANYMAIL_SEND_DEFAULTS={'esp_extra': {'sender_domain': 'your-domain.com'}}
        # (The mailgun_integration_tests do that.)
        self.message.from_email = "Test From <from@from-email.example.com>"
        self.message.send()
        self.assert_esp_called('/from-email.example.com/messages')  # API url includes the sender-domain

        self.message.esp_extra = {'sender_domain': 'esp-extra.example.com'}
        self.message.send()
        self.assert_esp_called('/esp-extra.example.com/messages')  # overrides from_email

    def test_default_omits_options(self):
        """Make sure by default we don't send any ESP-specific options.

        Options not specified by the caller should be omitted entirely from
        the API call (*not* sent as False or empty). This ensures
        that your ESP account settings apply by default.
        """
        self.message.send()
        self.assert_esp_called('/example.com/messages')
        data = self.get_api_call_data()
        mailgun_fields = {key: value for key, value in data.items()
                          if key.startswith('o:') or key.startswith('v:')}
        self.assertEqual(mailgun_fields, {})

    # noinspection PyUnresolvedReferences
    def test_send_attaches_anymail_status(self):
        """ The anymail_status should be attached to the message when it is sent """
        response_content = b"""{
            "id": "<12345.67890@example.com>",
            "message": "Queued. Thank you."
        }"""
        self.set_mock_response(raw=response_content)
        msg = mail.EmailMessage('Subject', 'Message', 'from@example.com', ['to1@example.com'],)
        sent = msg.send()
        self.assertEqual(sent, 1)
        self.assertEqual(msg.anymail_status.status, {'queued'})
        self.assertEqual(msg.anymail_status.message_id, '<12345.67890@example.com>')
        self.assertEqual(msg.anymail_status.recipients['to1@example.com'].status, 'queued')
        self.assertEqual(msg.anymail_status.recipients['to1@example.com'].message_id, '<12345.67890@example.com>')
        self.assertEqual(msg.anymail_status.esp_response.content, response_content)

    # noinspection PyUnresolvedReferences
    def test_send_failed_anymail_status(self):
        """ If the send fails, anymail_status should contain initial values"""
        self.set_mock_response(status_code=500)
        sent = self.message.send(fail_silently=True)
        self.assertEqual(sent, 0)
        self.assertIsNone(self.message.anymail_status.status)
        self.assertIsNone(self.message.anymail_status.message_id)
        self.assertEqual(self.message.anymail_status.recipients, {})
        self.assertIsNone(self.message.anymail_status.esp_response)

    # noinspection PyUnresolvedReferences
    def test_send_unparsable_response(self):
        """If the send succeeds, but a non-JSON API response, should raise an API exception"""
        mock_response = self.set_mock_response(status_code=200,
                                               raw=b"yikes, this isn't a real response")
        with self.assertRaises(AnymailAPIError):
            self.message.send()
        self.assertIsNone(self.message.anymail_status.status)
        self.assertIsNone(self.message.anymail_status.message_id)
        self.assertEqual(self.message.anymail_status.recipients, {})
        self.assertEqual(self.message.anymail_status.esp_response, mock_response)

    # test_json_serialization_errors: Mailgun payload isn't JSON, so we don't test this.
    # (Anything that requests can serialize as a form field will work with Mailgun)


class MailgunBackendRecipientsRefusedTests(MailgunBackendMockAPITestCase):
    """Should raise AnymailRecipientsRefused when *all* recipients are rejected or invalid"""

    # Mailgun doesn't check email bounce or complaint lists at time of send --
    # it always just queues the message. You'll need to listen for the "rejected"
    # and "failed" events to detect refused recipients.

    # The one exception is a completely invalid email, which will return a 400 response
    # and show up as an AnymailAPIError at send time.
    INVALID_TO_RESPONSE = b"""{
        "message": "'to' parameter is not a valid address. please check documentation"
    }"""

    def test_invalid_email(self):
        self.set_mock_response(status_code=400, raw=self.INVALID_TO_RESPONSE)
        msg = mail.EmailMessage('Subject', 'Body', 'from@example.com', to=['not a valid email'])
        with self.assertRaises(AnymailAPIError):
            msg.send()

    def test_fail_silently(self):
        self.set_mock_response(status_code=400, raw=self.INVALID_TO_RESPONSE)
        sent = mail.send_mail('Subject', 'Body', 'from@example.com', ['not a valid email'],
                              fail_silently=True)
        self.assertEqual(sent, 0)


class MailgunBackendSessionSharingTestCase(SessionSharingTestCasesMixin, MailgunBackendMockAPITestCase):
    """Requests session sharing tests"""
    pass  # tests are defined in the mixin


@override_settings(ANYMAIL_SEND_DEFAULTS={
    'metadata': {'global': 'globalvalue', 'other': 'othervalue'},
    'tags': ['globaltag'],
    'track_clicks': True,
    'track_opens': True,
    'esp_extra': {'o:globaloption': 'globalsetting'},
})
class MailgunBackendSendDefaultsTests(MailgunBackendMockAPITestCase):
    """Tests backend support for global SEND_DEFAULTS"""

    def test_send_defaults(self):
        """Test that global send defaults are applied"""
        self.message.send()
        data = self.get_api_call_data()
        # All these values came from ANYMAIL_SEND_DEFAULTS:
        self.assertEqual(data['v:global'], 'globalvalue')
        self.assertEqual(data['v:other'], 'othervalue')
        self.assertEqual(data['o:tag'], ['globaltag'])
        self.assertEqual(data['o:tracking-clicks'], 'yes')
        self.assertEqual(data['o:tracking-opens'], 'yes')
        self.assertEqual(data['o:globaloption'], 'globalsetting')

    def test_merge_message_with_send_defaults(self):
        """Test that individual message settings are *merged into* the global send defaults"""
        self.message.metadata = {'message': 'messagevalue', 'other': 'override'}
        self.message.tags = ['messagetag']
        self.message.track_clicks = False
        self.message.esp_extra = {'o:messageoption': 'messagesetting'}

        self.message.send()
        data = self.get_api_call_data()
        # All these values came from ANYMAIL_SEND_DEFAULTS + message.*:
        self.assertEqual(data['v:global'], 'globalvalue')
        self.assertEqual(data['v:message'], 'messagevalue')  # additional metadata
        self.assertEqual(data['v:other'], 'override')  # override global value
        self.assertEqual(data['o:tag'], ['globaltag', 'messagetag'])  # tags concatenated
        self.assertEqual(data['o:tracking-clicks'], 'no')  # message overrides
        self.assertEqual(data['o:tracking-opens'], 'yes')
        self.assertEqual(data['o:globaloption'], 'globalsetting')
        self.assertEqual(data['o:messageoption'], 'messagesetting')  # additional esp_extra

    @override_settings(ANYMAIL_MAILGUN_SEND_DEFAULTS={
        'tags': ['esptag'],
        'metadata': {'esp': 'espvalue'},
        'track_opens': False,
    })
    def test_esp_send_defaults(self):
        """Test that ESP-specific send defaults override individual global defaults"""
        self.message.send()
        data = self.get_api_call_data()
        # All these values came from ANYMAIL_SEND_DEFAULTS plus ANYMAIL_MAILGUN_SEND_DEFAULTS:
        self.assertNotIn('v:global', data)  # entire metadata overridden
        self.assertEqual(data['v:esp'], 'espvalue')
        self.assertEqual(data['o:tag'], ['esptag'])  # entire tags overridden
        self.assertEqual(data['o:tracking-clicks'], 'yes')  # we didn't override the global track_clicks
        self.assertEqual(data['o:tracking-opens'], 'no')
        self.assertEqual(data['o:globaloption'], 'globalsetting')  # we didn't override the global esp_extra


@override_settings(EMAIL_BACKEND="anymail.backends.mailgun.MailgunBackend")
class MailgunBackendImproperlyConfiguredTests(SimpleTestCase, AnymailTestMixin):
    """Test ESP backend without required settings in place"""

    def test_missing_api_key(self):
        with self.assertRaises(ImproperlyConfigured) as cm:
            mail.send_mail('Subject', 'Message', 'from@example.com', ['to@example.com'])
        errmsg = str(cm.exception)
        # Make sure the error mentions MAILGUN_API_KEY and ANYMAIL_MAILGUN_API_KEY
        self.assertRegex(errmsg, r'\bMAILGUN_API_KEY\b')
        self.assertRegex(errmsg, r'\bANYMAIL_MAILGUN_API_KEY\b')
