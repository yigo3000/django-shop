# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.translation import ugettext_lazy as _
from shop.models import order
from shop.models.cart import CartItemModel


class OrderItem(order.BaseOrderItem):
    """
    Modified OrderItem which keeps track on the delivered items. To be used in combination with
    the Order workflow :class:`shop.shipping.delivery.PartialDeliveryWorkflowMixin`.
    """
    quantity = models.IntegerField(_("Ordered quantity"))
    canceled = models.BooleanField(_("Item canceled "), default=False)

    def populate_from_cart_item(self, cart_item, request):
        from .smartphone import SmartPhoneModel
        super(OrderItem, self).populate_from_cart_item(cart_item, request)
        # the product code and price must be fetched from the product's variant
        try:
            if isinstance(cart_item.product, SmartPhoneModel):
                product = cart_item.product.get_product_variant(cart_item.extra['product_code'])
            else:
                product = cart_item.product
            self.product_code = product.product_code
            self._unit_price = Decimal(product.unit_price)
        except (KeyError, ObjectDoesNotExist) as e:
            raise CartItemModel.DoesNotExist(e)
