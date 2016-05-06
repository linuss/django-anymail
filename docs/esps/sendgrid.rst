.. _sendgrid-backend:

SendGrid
========

Anymail integrates with the `SendGrid`_ email service,
using their `Web API v2`_. (Their v3 API does not support sending mail,
but the v3 API calls *do* get information about mail sent through v2.)

.. _SendGrid: https://sendgrid.com/
.. _Web API v2: https://sendgrid.com/docs/API_Reference/Web_API/mail.html


Settings
--------


.. rubric:: EMAIL_BACKEND

To use Anymail's SendGrid backend, set:

  .. code-block:: python

      EMAIL_BACKEND = "anymail.backends.sendgrid.SendGridBackend"

in your settings.py. (Watch your capitalization: SendGrid spells
their name with an uppercase "G", so Anymail does too.)


.. setting:: ANYMAIL_SENDGRID_API_KEY

.. rubric:: SENDGRID_API_KEY

A SendGrid API key with "Mail Send" permission.
(Manage API keys in your `SendGrid API key settings`_.)
Either an API key or both :setting:`SENDGRID_USERNAME <ANYMAIL_SENDGRID_USERNAME>`
and :setting:`SENDGRID_PASSWORD <ANYMAIL_SENDGRID_PASSWORD>` are required.

  .. code-block:: python

      ANYMAIL = {
          ...
          "SENDGRID_API_KEY": "<your API key>",
      }

Anymail will also look for ``SENDGRID_API_KEY`` at the
root of the settings file if neither ``ANYMAIL["SENDGRID_API_KEY"]``
nor ``ANYMAIL_SENDGRID_API_KEY`` is set.

.. _SendGrid API key settings: https://app.sendgrid.com/settings/api_keys


.. setting:: ANYMAIL_SENDGRID_USERNAME
.. setting:: ANYMAIL_SENDGRID_PASSWORD

.. rubric:: SENDGRID_USERNAME and SENDGRID_PASSWORD

SendGrid credentials with the "Mail" permission. You should **not**
use the username/password that you use to log into SendGrid's
dashboard. Create credentials specifically for sending mail in the
`SendGrid credentials settings`_.

  .. code-block:: python

      ANYMAIL = {
          ...
          "SENDGRID_USERNAME": "<sendgrid credential with Mail permission>",
          "SENDGRID_PASSWORD": "<password for that credential>",
      }

Either username/password or :setting:`SENDGRID_API_KEY <ANYMAIL_SENDGRID_API_KEY>`
are required (but not both).

Anymail will also look for ``SENDGRID_USERNAME`` and ``SENDGRID_PASSWORD`` at the
root of the settings file if neither ``ANYMAIL["SENDGRID_USERNAME"]``
nor ``ANYMAIL_SENDGRID_USERNAME`` is set.

.. _SendGrid credentials settings: https://app.sendgrid.com/settings/credentials


.. setting:: ANYMAIL_SENDGRID_GENERATE_MESSAGE_ID

.. rubric:: SENDGRID_GENERATE_MESSAGE_ID

Whether Anymail should generate a Message-ID for messages sent
through SendGrid, to facilitate event tracking.

Default ``True``. You can set to ``False`` to disable this behavior.
See :ref:`Message-ID quirks <sendgrid-message-id>` below.


.. setting:: ANYMAIL_SENDGRID_TEMPLATE_VAR_FORMAT

.. rubric:: SENDGRID_TEMPLATE_VAR_FORMAT

If you use :ref:`merge-data`, set this to a :meth:`str.format`
formatting string that indicates how merge variables are delimited
in your SendGrid templates, with `{}` becoming the variable name.

For example, if your templates use the ``-name-`` hyphen delimiters
suggested in some SendGrid docs, you would set:

  .. code-block:: python

      ANYMAIL = {
          ...
          "SENDGRID_TEMPLATE_VAR_FORMAT": "-{}-",
      }

The default `None` requires you include the delimiters directly in your
:attr:`~anymail.message.AnymailMessage.template_data` keys.
You can also override this setting for individual messages.
See the notes on SendGrid :ref:`templates and merge <sendgrid-templates>`
below.


.. setting:: ANYMAIL_SENDGRID_API_URL

.. rubric:: SENDGRID_API_URL

The base url for calling the SendGrid v2 API.

The default is ``SENDGRID_API_URL = "https://api.sendgrid.com/api/"``
(It's unlikely you would need to change this.)


.. _sendgrid-esp-extra:

esp_extra support
-----------------

To use SendGrid features not directly supported by Anymail, you can
set a message's :attr:`~anymail.message.AnymailMessage.esp_extra` to
a `dict` of parameters for SendGrid's `mail.send API`_. Any keys in
your :attr:`esp_extra` dict will override Anymail's normal values
for that parameter, except that `'x-smtpapi'` will be merged.

Example:

    .. code-block:: python

        message.esp_extra = {
            'x-smtpapi': {
                "asm_group": 1,  # Assign SendGrid unsubscribe group for this message
                "asm_groups_to_display": [1, 2, 3],
                "filters": {
                    "subscriptiontrack": {  # Insert SendGrid subscription management links
                        "settings": {
                            "text/html": "If you would like to unsubscribe <% click here %>.",
                            "text/plain": "If you would like to unsubscribe click here: <% %>.",
                            "enable": 1
                        }
                    }
                }
            }
        }


(You can also set `"esp_extra"` in Anymail's
:ref:`global send defaults <send-defaults>` to apply it to all
messages.)


.. _mail.send API: https://sendgrid.com/docs/API_Reference/Web_API/mail.html#-send



Limitations and quirks
----------------------

**Duplicate attachment filenames**
  Anymail is not capable of communicating multiple attachments with
  the same filename to SendGrid. (This also applies to multiple attachments
  with *no* filename, though not to inline images.)

  If you are sending multiple attachments on a single message,
  make sure each one has a unique, non-empty filename.


.. _sendgrid-message-id:

**Message-ID**
  SendGrid does not return any sort of unique id from its send API call.
  Knowing a sent message's ID can be important for later queries about
  the message's status.

  To work around this, Anymail by default generates a new Message-ID for each
  outgoing message, provides it to SendGrid, and includes it in the
  :attr:`~anymail.message.AnymailMessage.anymail_status`
  attribute after you send the message.

  In later SendGrid API calls, you can match that Message-ID
  to SendGrid's ``smtp-id`` event field. (Anymail uses an additional
  workaround to ensure smtp-id is included in all SendGrid events,
  even those that aren't documented to include it.)

  Anymail will use the domain of the message's :attr:`from_email`
  to generate the Message-ID. (If this isn't desired, you can supply
  your own Message-ID in the message's :attr:`extra_headers`.)

  To disable all of these Message-ID workarounds, set
  :setting:`ANYMAIL_SENDGRID_GENERATE_MESSAGE_ID` to False in your settings.


**Invalid Addresses**
  SendGrid will accept *and send* just about anything as
  a message's :attr:`from_email`. (And email protocols are
  actually OK with that.)

  (Tested March, 2016)


.. _sendgrid-templates:

Batch sending/merge and ESP templates
-------------------------------------

SendGrid offers both :ref:`ESP stored templates <esp-stored-templates>`
and :ref:`batch sending <batch-send>` with per-recipient merge data.

You can use a SendGrid stored template by setting a message's
:attr:`~anymail.message.AnymailMessage.template_id` to the
template's unique id. Alternatively, you can refer to merge fields
directly in an EmailMessage's subject and body---the message itself
is used as an on-the-fly template.

In either case, supply the merge data values with Anymail's
normalized :attr:`~anymail.message.AnymailMessage.template_data`
and :attr:`~anymail.message.AnymailMessage.template_global_data`
message attributes.

  .. code-block:: python

      message = EmailMessage(
          ...
          subject="",  # don't add any additional subject content to the template
          body="",  # (same thing for additional body content)
          to=["alice@example.com", "Bob <bob@example.com>"]
      )
      message.template_id = "5997fcf6-2b9f-484d-acd5-7e9a99f0dc1f"  # SendGrid id
      message.template_data = {
          'alice@example.com': {'name': "Alice", 'order_no': "12345"},
          'bob@example.com': {'name': "Bob", 'order_no': "54321"},
      }
      message.template_global_data = {
          'ship_date': "May 15",
      }
      message.esp_extra = {
          # Tell Anymail this SendGrid template uses "-var-" to refer to merge variables.
          # (We could also just set SENDGRID_TEMPLATE_VAR_FORMAT in our ANYMAIL settings.)
          'template_var_format': "-{}-"
      }

SendGrid doesn't have a pre-defined template variable format, so you
must tell Anymail how merge variables will be delimited in your templates.
There are three ways you can do this:

  * Set `'template_var_format'` in the message's
    :attr:`~anymail.message.AnymailMessage.esp_extra` to a python :meth:`str.format`
    string, as shown in the example above. (This applies only to that
    particular EmailMessage.)
  * *Or* set :setting:`SENDGRID_TEMPLATE_VAR_FORMAT <ANYMAIL_SENDGRID_TEMPLATE_VAR_FORMAT>`
    in your Anymail settings. This is usually the best approach, and will apply to all messages
    sent through SendGrid. (You can still use esp_extra to override for individual messages.)
  * *Or* include the variable delimiters directly in *all* your
    :attr:`~anymail.message.AnymailMessage.template_data` and
    :attr:`~anymail.message.AnymailMessage.template_global_data` keys.
    E.g.: ``{'-name-': "Alice", '-order_no-': "12345"}``.
    (This can be error-prone, and difficult to move to other ESPs.)

When you supply per-recipient :attr:`~anymail.message.AnymailMessage.template_data`,
Anymail automatically changes how it communicates the "to" list to SendGrid, so that
so that each recipient sees only their own email address. (Anymail moves the recipients
from top-level "to" and "toname" API parameters into the "x-smtpapi" section "to" list.)

SendGrid templates allow you to mix your EmailMessage's `subject` and `body`
with the template subject and body (by using `<%subject%>` and `<%body%>` in
your SendGrid template definition where you want the message-specific versions
to appear). If you don't want to supply any additional subject or body content
from your Django ap, set those EmailMessage attributes to empty strings.

See the `SendGrid's template overview`_ and `transactional template docs`_
for more information.

.. _SendGrid's template overview:
    https://sendgrid.com/docs/User_Guide/Transactional_Templates/index.html
.. _transactional template docs:
    https://sendgrid.com/docs/API_Reference/Web_API_v3/Transactional_Templates/smtpapi.html


.. _sendgrid-webhooks:

Status tracking webhooks
------------------------

If you are using Anymail's normalized :ref:`status tracking <event-tracking>`, enter
the url in your `SendGrid mail settings`_, under "Event Notification":

   :samp:`https://{random}:{random}@{yoursite.example.com}/anymail/sendgrid/tracking/`

     * *random:random* is an :setting:`ANYMAIL_WEBHOOK_AUTHORIZATION` shared secret
     * *yoursite.example.com* is your Django site

Be sure to check the boxes in the SendGrid settings for the event types you want to receive.

SendGrid will report these Anymail :attr:`~anymail.signals.AnymailTrackingEvent.event_type`\s:
queued, rejected, bounced, deferred, delivered, opened, clicked, complained, unsubscribed,
subscribed.

The event's :attr:`~anymail.signals.AnymailTrackingEvent.esp_event` field will be
a `dict` of `Sendgrid event`_ fields, for a single event. (Although SendGrid calls
webhooks with batches of events, Anymail will invoke your signal receiver separately
for each event in the batch.)

.. _SendGrid mail settings: https://app.sendgrid.com/settings/mail_settings
.. _Sendgrid event: https://sendgrid.com/docs/API_Reference/Webhooks/event.html
