.. _mailgun-backend:

Mailgun
=======

Anymail integrates with the `Mailgun <https://mailgun.com>`_
transactional email service from Rackspace, using their
REST API.


Settings
--------

.. rubric:: EMAIL_BACKEND

To use Anymail's Mailgun backend, set:

  .. code-block:: python

      EMAIL_BACKEND = "anymail.backends.mailgun.MailgunBackend"

in your settings.py. (Watch your capitalization: Mailgun spells their name with a
lowercase "g", so Anymail does too.)


.. setting:: ANYMAIL_MAILGUN_API_KEY

.. rubric:: MAILGUN_API_KEY

Required. Your Mailgun API key:

  .. code-block:: python

      ANYMAIL = {
          ...
          "MAILGUN_API_KEY": "<your API key>",
      }

Anymail will also look for ``MAILGUN_API_KEY`` at the
root of the settings file if neither ``ANYMAIL["MAILGUN_API_KEY"]``
nor ``ANYMAIL_MAILGUN_API_KEY`` is set.


.. setting:: ANYMAIL_MAILGUN_API_URL

.. rubric:: MAILGUN_API_URL

The base url for calling the Mailgun API. It does not include
the sender domain. (Anymail :ref:`figures this out <mailgun-sender-domain>`
for you.)

The default is ``MAILGUN_API_URL = "https://api.mailgun.net/v3"``
(It's unlikely you would need to change this.)


.. _mailgun-sender-domain:

Email sender domain
-------------------

Mailgun's API requires a sender domain `in the API url <base-url>`_.
By default, Anymail will use the domain of each email's from address
as the domain for the Mailgun API.

If you need to override this default, you can use Anymail's
:attr:`esp_extra` dict, either on an individual message:

    .. code-block:: python

        message = EmailMessage(from_email="sales@europe.example.com", ...)
        message.esp_extra = {"sender_domain": "example.com"}


... or as a global :ref:`send default <send-defaults>` setting that applies
to all messages:

    .. code-block:: python

        ANYMAIL = {
            ...
            "MAILGUN_SEND_DEFAULTS": {
                "esp_extra": {"sender_domain": "example.com"}
            }
        }

.. _base-url: https://documentation.mailgun.com/api-intro.html#base-url


.. _mailgun-esp-extra:

exp_extra support
-----------------

Anymail's Mailgun backend will pass all :attr:`~anymail.message.AnymailMessage.esp_extra`
values directly to Mailgun. You can use any of the (non-file) parameters listed in the
`Mailgun sending docs`_. Example:

  .. code-block:: python

      message = AnymailMessage(...)
      message.esp_extra = {
          'o:testmode': 'yes',  # use Mailgun's test mode
      }

.. _Mailgun sending docs: https://documentation.mailgun.com/api-sending.html#sending


.. _mailgun-templates:

Batch sending/merge and ESP templates
-------------------------------------

Mailgun does not offer :ref:`ESP stored templates <esp-stored-templates>`,
so Anymail's :attr:`~anymail.message.AnymailMessage.template_id` message
attribute is not supported with the Mailgun backend.

Mailgun *does* support :ref:`batch sending <batch-send>` with per-recipient
merge data. You can refer to Mailgun "recipient variables" in your
message subject and body, and supply the values with Anymail's
normalized :attr:`~anymail.message.AnymailMessage.merge_data`
and :attr:`~anymail.message.AnymailMessage.merge_global_data`
message attributes:

  .. code-block:: python

      message = EmailMessage(
          ...
          subject="Your order %recipient.order_no% has shipped",
          body="""Hi %recipient.name%,
                  We shipped your order %recipient.order_no%
                  on %recipient.ship_date%.""",
          to=["alice@example.com", "Bob <bob@example.com>"]
      )
      # (you'd probably also set a similar html body with %recipient.___% variables)
      message.merge_data = {
          'alice@example.com': {'name': "Alice", 'order_no': "12345"},
          'bob@example.com': {'name': "Bob", 'order_no': "54321"},
      }
      message.merge_global_data = {
          'ship_date': "May 15"  # Anymail maps globals to all recipients
      }

Mailgun does not natively support global merge data. Anymail emulates
the capability by copying any `merge_global_data` values to each
recipient's section in Mailgun's "recipient-variables" API parameter.

See the `Mailgun batch sending`_ docs for more information.

.. _Mailgun batch sending:
    https://documentation.mailgun.com/user_manual.html#batch-sending


.. _mailgun-webhooks:

Status tracking webhooks
------------------------

If you are using Anymail's normalized :ref:`status tracking <event-tracking>`, enter
the url in your `Mailgun dashboard`_ on the "Webhooks" tab. Mailgun allows you to enter
a different URL for each event type: just enter this same Anymail tracking URL
for all events you want to receive:

   :samp:`https://{random}:{random}@{yoursite.example.com}/anymail/mailgun/tracking/`

     * *random:random* is an :setting:`ANYMAIL_WEBHOOK_AUTHORIZATION` shared secret
     * *yoursite.example.com* is your Django site

If you use multiple Mailgun sending domains, you'll need to enter the webhook
URLs for each of them, using the selector on the left side of Mailgun's dashboard.

Mailgun implements a limited form of webhook signing, and Anymail will verify
these signatures (based on your :setting:`MAILGUN_API_KEY <ANYMAIL_MAILGUN_API_KEY>`
Anymail setting).

Mailgun will report these Anymail :attr:`~anymail.signals.AnymailTrackingEvent.event_type`\s:
delivered, rejected, bounced, complained, unsubscribed, opened, clicked.

The event's :attr:`~anymail.signals.AnymailTrackingEvent.esp_event` field will be
a Django :class:`~django.http.QueryDict` object of `Mailgun event fields`_.

.. _Mailgun dashboard: https://mailgun.com/app/dashboard
.. _Mailgun event fields: https://documentation.mailgun.com/user_manual.html#webhooks
