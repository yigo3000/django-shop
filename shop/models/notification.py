# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db import models
from django.db.models import Q
from django.http.request import HttpRequest
from django.template import Context, engines
from django.utils.translation import ugettext_lazy as _, override as translation_override
from django.utils.six.moves.urllib.parse import urlparse

from post_office import mail
from post_office.models import Email as OriginalEmail, EmailTemplate

from filer.fields.file import FilerFileField

from shop import app_settings
from .customer import CustomerModel


class Email(OriginalEmail):
    """
    Patch class `post_office.models.Email` which fixes https://github.com/ui/django-post_office/issues/116
    and additionally converts HTML messages into plain text messages.
    """
    class Meta:
        proxy = True

    def email_message(self, connection=None):
        if self.template is not None:
            render_language = self.context.get('render_language', settings.LANGUAGE_CODE)
            context = Context(self.context)
            with translation_override(render_language):
                subject = engines['django'].from_string(self.template.subject).render(context)
                message = engines['django'].from_string(self.template.content).render(context)
                html_message = engines['django'].from_string(self.template.html_content).render(context)
        else:
            subject = self.subject
            message = self.message
            html_message = self.html_message

        if html_message:
            if not message:
                message = BeautifulSoup(html_message).text
            mailmsg = EmailMultiAlternatives(
                subject=subject, body=message, from_email=self.from_email,
                to=self.to, bcc=self.bcc, cc=self.cc,
                connection=connection, headers=self.headers)
            mailmsg.attach_alternative(html_message, 'text/html')
        else:
            mailmsg = EmailMessage(
                subject=subject, body=message, from_email=self.from_email,
                to=self.to, bcc=self.bcc, cc=self.cc,
                connection=connection, headers=self.headers)

        for attachment in self.attachments.all():
            mailmsg.attach(attachment.name, attachment.file.read())
        return mailmsg


class EmailManager(models.Manager):
    def get_queryset(self):
        return Email.objects.get_queryset()

OriginalEmail.add_to_class('objects', EmailManager())


class Notification(models.Model):
    """
    A task executed on receiving a signal.
    """
    name = models.CharField(max_length=50, verbose_name=_("Name"))
    transition_target = models.CharField(max_length=50, verbose_name=_("Event"))
    mail_to = models.PositiveIntegerField(verbose_name=_("Mail to"), null=True,
                                          blank=True, default=None)
    mail_template = models.ForeignKey(EmailTemplate, verbose_name=_("Template"),
                                      limit_choices_to=Q(language__isnull=True) | Q(language=''))

    class Meta:
        app_label = 'shop'
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ('transition_target', 'mail_to')

    def get_recipient(self, order):
        if self.mail_to is None:
            return
        if self.mail_to == 0:
            return order.customer.email
        return CustomerModel.objects.get(pk=self.mail_to).email


class NotificationAttachment(models.Model):
    notification = models.ForeignKey(Notification)
    attachment = FilerFileField(null=True, blank=True, related_name='email_attachment')

    class Meta:
        app_label = 'shop'


class EmulateHttpRequest(HttpRequest):
    """
    Use this class to emulate a HttpRequest object, when templates must be rendered
    asynchronously, for instance when an email must be generated out of an Order object.
    """
    def __init__(self, customer, stored_request):
        super(EmulateHttpRequest, self).__init__()
        parsedurl = urlparse(stored_request.get('absolute_base_uri'))
        self.path = self.path_info = parsedurl.path
        self.environ = {}
        self.META['PATH_INFO'] = parsedurl.path
        self.META['SCRIPT_NAME'] = ''
        self.META['HTTP_HOST'] = parsedurl.netloc
        self.META['HTTP_X_FORWARDED_PROTO'] = parsedurl.scheme
        self.META['QUERY_STRING'] = parsedurl.query
        self.META['HTTP_USER_AGENT'] = stored_request.get('user_agent')
        self.META['REMOTE_ADDR'] = stored_request.get('remote_ip')
        self.method = 'GET'
        self.LANGUAGE_CODE = self.COOKIES['django_language'] = stored_request.get('language')
        self.customer = customer
        self.user = customer.is_anonymous() and AnonymousUser or customer.user
        self.current_page = None


def order_event_notification(sender, instance=None, target=None, **kwargs):
    from shop.models.order import OrderModel
    from shop.serializers.order import OrderDetailSerializer

    if not isinstance(instance, OrderModel):
        return
    for notification in Notification.objects.filter(transition_target=target):
        recipient = notification.get_recipient(instance)
        if recipient is None:
            continue

        # emulate a request object which behaves similar to that one, when the customer submitted its order
        emulated_request = EmulateHttpRequest(instance.customer, instance.stored_request)
        customer_serializer = app_settings.CUSTOMER_SERIALIZER(instance.customer)
        order_serializer = OrderDetailSerializer(instance, context={'request': emulated_request})
        language = instance.stored_request.get('language')
        context = {
            'customer': customer_serializer.data,
            'data': order_serializer.data,
            'ABSOLUTE_BASE_URI': emulated_request.build_absolute_uri().rstrip('/'),
            'render_language': language,
        }
        try:
            template = notification.mail_template.translated_templates.get(language=language)
        except EmailTemplate.DoesNotExist:
            template = notification.mail_template
        attachments = {}
        for notiatt in notification.notificationattachment_set.all():
            attachments[notiatt.attachment.original_filename] = notiatt.attachment.file.file
        mail.send(recipient, template=notification.mail_template, context=context,
                  attachments=attachments, render_on_delivery=True)
