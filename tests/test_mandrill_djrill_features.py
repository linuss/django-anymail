from datetime import date
from django.core import mail
from django.test import override_settings

from anymail.exceptions import AnymailAPIError, AnymailSerializationError

from .test_mandrill_backend import MandrillBackendMockAPITestCase


class MandrillBackendDjrillFeatureTests(MandrillBackendMockAPITestCase):
    """Test backend support for features leftover from Djrill"""

    # Most of these features should be moved to esp_extra.
    # The template and merge_ta

    def test_djrill_message_options(self):
        self.message.url_strip_qs = True
        self.message.important = True
        self.message.auto_text = True
        self.message.auto_html = True
        self.message.inline_css = True
        self.message.preserve_recipients = True
        self.message.view_content_link = False
        self.message.tracking_domain = "click.example.com"
        self.message.signing_domain = "example.com"
        self.message.return_path_domain = "support.example.com"
        self.message.subaccount = "marketing-dept"
        self.message.async = True
        self.message.ip_pool = "Bulk Pool"
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['url_strip_qs'], True)
        self.assertEqual(data['message']['important'], True)
        self.assertEqual(data['message']['auto_text'], True)
        self.assertEqual(data['message']['auto_html'], True)
        self.assertEqual(data['message']['inline_css'], True)
        self.assertEqual(data['message']['preserve_recipients'], True)
        self.assertEqual(data['message']['view_content_link'], False)
        self.assertEqual(data['message']['tracking_domain'], "click.example.com")
        self.assertEqual(data['message']['signing_domain'], "example.com")
        self.assertEqual(data['message']['return_path_domain'], "support.example.com")
        self.assertEqual(data['message']['subaccount'], "marketing-dept")
        self.assertEqual(data['async'], True)
        self.assertEqual(data['ip_pool'], "Bulk Pool")

    def test_google_analytics(self):
        self.message.google_analytics_domains = ["example.com"]
        self.message.google_analytics_campaign = "Email Receipts"
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['google_analytics_domains'], ["example.com"])
        self.assertEqual(data['message']['google_analytics_campaign'], "Email Receipts")

    def test_recipient_metadata(self):
        self.message.recipient_metadata = {
            # Anymail expands simple python dicts into the more-verbose
            # rcpt/values structures the Mandrill API uses
            "customer@example.com": {'cust_id': "67890", 'order_id': "54321"},
            "guest@example.com": {'cust_id': "94107", 'order_id': "43215"}
        }
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['recipient_metadata'],
                         [{'rcpt': "customer@example.com",
                           'values': {'cust_id': "67890", 'order_id': "54321"}},
                          {'rcpt': "guest@example.com",
                           'values': {'cust_id': "94107", 'order_id': "43215"}}
                          ])

    def test_no_subaccount_by_default(self):
        mail.send_mail('Subject', 'Body', 'from@example.com', ['to@example.com'])
        data = self.get_api_call_json()
        self.assertFalse('subaccount' in data['message'])

    @override_settings(ANYMAIL_MANDRILL_SEND_DEFAULTS={'subaccount': 'test_subaccount'})
    def test_subaccount_setting(self):
        mail.send_mail('Subject', 'Body', 'from@example.com', ['to@example.com'])
        data = self.get_api_call_json()
        self.assertEqual(data['message']['subaccount'], "test_subaccount")

    @override_settings(ANYMAIL_MANDRILL_SEND_DEFAULTS={'subaccount': 'global_setting_subaccount'})
    def test_subaccount_message_overrides_setting(self):
        message = mail.EmailMessage('Subject', 'Body', 'from@example.com', ['to@example.com'])
        message.subaccount = "individual_message_subaccount"  # should override global setting
        message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['subaccount'], "individual_message_subaccount")

    def test_default_omits_options(self):
        """Make sure by default we don't send any Mandrill-specific options.

        Options not specified by the caller should be omitted entirely from
        the Mandrill API call (*not* sent as False or empty). This ensures
        that your Mandrill account settings apply by default.
        """
        self.message.send()
        self.assert_esp_called("/messages/send.json")
        data = self.get_api_call_json()
        self.assertFalse('from_name' in data['message'])
        self.assertFalse('bcc_address' in data['message'])
        self.assertFalse('important' in data['message'])
        self.assertFalse('auto_text' in data['message'])
        self.assertFalse('auto_html' in data['message'])
        self.assertFalse('inline_css' in data['message'])
        self.assertFalse('url_strip_qs' in data['message'])
        self.assertFalse('preserve_recipients' in data['message'])
        self.assertFalse('view_content_link' in data['message'])
        self.assertFalse('tracking_domain' in data['message'])
        self.assertFalse('signing_domain' in data['message'])
        self.assertFalse('return_path_domain' in data['message'])
        self.assertFalse('subaccount' in data['message'])
        self.assertFalse('google_analytics_domains' in data['message'])
        self.assertFalse('google_analytics_campaign' in data['message'])
        self.assertFalse('merge_language' in data['message'])
        self.assertFalse('global_merge_vars' in data['message'])
        self.assertFalse('merge_vars' in data['message'])
        self.assertFalse('recipient_metadata' in data['message'])
        # Options at top level of api params (not in message dict):
        self.assertFalse('async' in data)
        self.assertFalse('ip_pool' in data)

    def test_dates_not_serialized(self):
        """Old versions of predecessor package Djrill accidentally serialized dates to ISO"""
        self.message.metadata = {'SHIP_DATE': date(2015, 12, 2)}
        with self.assertRaises(AnymailSerializationError):
            self.message.send()


@override_settings(ANYMAIL_SEND_DEFAULTS={
    'from_name': 'Djrill Test',
    'important': True,
    'auto_text': True,
    'auto_html': True,
    'inline_css': True,
    'url_strip_qs': True,
    'preserve_recipients': True,
    'view_content_link': True,
    'subaccount': 'example-subaccount',
    'tracking_domain': 'example.com',
    'signing_domain': 'example.com',
    'return_path_domain': 'example.com',
    'google_analytics_domains': ['example.com/test'],
    'google_analytics_campaign': ['UA-00000000-1'],
    'merge_language': 'mailchimp',
    'async': True,
    'ip_pool': 'Pool1',
    'invalid': 'invalid',
})
class MandrillBackendDjrillSendDefaultsTests(MandrillBackendMockAPITestCase):
    """Tests backend support for global SEND_DEFAULTS"""

    def test_global_options(self):
        """Test that any global settings get passed through
        """
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['from_name'], 'Djrill Test')
        self.assertTrue(data['message']['important'])
        self.assertTrue(data['message']['auto_text'])
        self.assertTrue(data['message']['auto_html'])
        self.assertTrue(data['message']['inline_css'])
        self.assertTrue(data['message']['url_strip_qs'])
        self.assertTrue(data['message']['preserve_recipients'])
        self.assertTrue(data['message']['view_content_link'])
        self.assertEqual(data['message']['subaccount'], 'example-subaccount')
        self.assertEqual(data['message']['tracking_domain'], 'example.com')
        self.assertEqual(data['message']['signing_domain'], 'example.com')
        self.assertEqual(data['message']['return_path_domain'], 'example.com')
        self.assertEqual(data['message']['google_analytics_domains'], ['example.com/test'])
        self.assertEqual(data['message']['google_analytics_campaign'], ['UA-00000000-1'])
        self.assertEqual(data['message']['merge_language'], 'mailchimp')
        self.assertFalse('recipient_metadata' in data['message'])
        # Options at top level of api params (not in message dict):
        self.assertTrue(data['async'])
        self.assertEqual(data['ip_pool'], 'Pool1')
        # Option that shouldn't be added
        self.assertFalse('invalid' in data['message'])

    def test_global_options_override(self):
        """Test that manually settings options overrides global settings
        """
        self.message.from_name = "override"
        self.message.important = False
        self.message.auto_text = False
        self.message.auto_html = False
        self.message.inline_css = False
        self.message.url_strip_qs = False
        self.message.preserve_recipients = False
        self.message.view_content_link = False
        self.message.subaccount = "override"
        self.message.tracking_domain = "override.example.com"
        self.message.signing_domain = "override.example.com"
        self.message.return_path_domain = "override.example.com"
        self.message.google_analytics_domains = ['override.example.com']
        self.message.google_analytics_campaign = ['UA-99999999-1']
        self.message.merge_language = 'handlebars'
        self.message.async = False
        self.message.ip_pool = "Bulk Pool"
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['from_name'], 'override')
        self.assertFalse(data['message']['important'])
        self.assertFalse(data['message']['auto_text'])
        self.assertFalse(data['message']['auto_html'])
        self.assertFalse(data['message']['inline_css'])
        self.assertFalse(data['message']['url_strip_qs'])
        self.assertFalse(data['message']['preserve_recipients'])
        self.assertFalse(data['message']['view_content_link'])
        self.assertEqual(data['message']['subaccount'], 'override')
        self.assertEqual(data['message']['tracking_domain'], 'override.example.com')
        self.assertEqual(data['message']['signing_domain'], 'override.example.com')
        self.assertEqual(data['message']['return_path_domain'], 'override.example.com')
        self.assertEqual(data['message']['google_analytics_domains'], ['override.example.com'])
        self.assertEqual(data['message']['google_analytics_campaign'], ['UA-99999999-1'])
        self.assertEqual(data['message']['merge_language'], 'handlebars')
        # Options at top level of api params (not in message dict):
        self.assertFalse(data['async'])
        self.assertEqual(data['ip_pool'], 'Bulk Pool')


class MandrillBackendDjrillTemplateTests(MandrillBackendMockAPITestCase):
    """Test backend support for ESP templating features"""

    # Holdovers from Djrill, until we design Anymail's normalized esp-template support

    def test_merge_language(self):
        self.message.merge_language = "mailchimp"
        self.message.send()
        data = self.get_api_call_json()
        self.assertEqual(data['message']['merge_language'], "mailchimp")

    def test_template_content(self):
        self.message.template_content = {
            'HEADLINE': "<h1>Specials Just For *|FNAME|*</h1>",
            'OFFER_BLOCK': "<p><em>Half off</em> all fruit</p>"
        }
        self.message.send()
        data = self.get_api_call_json()
        # Anymail expands simple python dicts into the more-verbose name/content
        # structures the Mandrill API uses
        self.assertEqual(data['template_content'],
                         [{'name': "HEADLINE",
                           'content': "<h1>Specials Just For *|FNAME|*</h1>"},
                          {'name': "OFFER_BLOCK",
                           'content': "<p><em>Half off</em> all fruit</p>"}])
