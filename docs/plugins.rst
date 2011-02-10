================
Plugins
================

Django Shop defines 3 types of different plugins for the time being:
1. Cart modifiers
2. Shipping modules
3. Payment modules

Cart modifiers
===============

Cart modifiers are plugins that modify the cart's contents.
Rough categories could be discount modules or tax modules: rules for theses modules
are invariant, and should be "stacked".
Example: "CDs are buy two get one free this month", "orders over 500$ get a 10% 
discount"

How they work
--------------
Cart modifiers should extend the shop.cart.cart_modifiers_base.BaseCartModifier
class.

Users must register theses filters in the settings.SHOP_PRICE_MODIFIERS settings 
entry. Modifiers will be iterated and function in the same fashion as django 
middleware classes.

BaseCartModifier defines a set of methods that implementations should override, and that
are called for each cart item/cart when the cart's update() method is called.
 
Example implementations
------------------------
You can refer to shop.cart.modifiers.* package to see some example implementations


Shipping backends
==================

Shipping backends differ from price modifiers in that there must be only one
shipping backend selected per Order (the shopper must choose which delivery method
to use)

Shipping costs should be calculated on an Order Object, not on a Cart object (Orders
are fully serialized in the database for archiving purposes).


Payment backends
=================

Payment backends must also be selected by the end user (the shopper).
Theses modules take care of the actual payment processing.