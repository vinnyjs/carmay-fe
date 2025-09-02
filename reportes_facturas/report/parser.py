##############################################################################
#
# Copyright (c) 2008-2011 Alistek Ltd (http://www.alistek.com) All Rights Reserved.
#                    General contacts <info@alistek.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# This module is GPLv3 or newer and incompatible
# with OpenERP SA "AGPL + Private Use License"!
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import logging
logger = logging.getLogger(__name__)

from odoo.report.report_sxw import rml_parse
from dateutil.parser import parse

meses = {
    1: 'Enero',
    2: 'Febrero',
    3: 'Marzo',
    4: 'Abril',
    5: 'Mayo',
    6: 'Junio',
    7: 'Julio',
    8: 'Agosto',
    9: 'Setiembre',
    10: 'Octubre',
    11: 'Noviembre',
    12: 'Diciembre'
}
class Parser(rml_parse):
    def __init__(self, cr, uid, name, context):
        super(self.__class__, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'amount_to_text': self.amount_to_text,
            'get_fecha': self.get_fecha,
            'get_amount_untaxed': self.get_amount_untaxed,
            'get_amount_taxed': self.get_amount_taxed,
        })

    def amount_to_text(self, purchase):
        currency_name = "COLONES"
        currency = purchase.currency_id
        if currency and currency.name.lower() == "usd":
            currency_name = "DOLARES"
        return amt_text.number_to_text_es(purchase.amount_total, currency_name)

    def get_fecha(self, pfecha):
        fecha = parse(pfecha)
        return "{} de {} de {}".format(fecha.day, meses.get(fecha.month), fecha.year)

    def get_amount_untaxed(self, purchase):
        total_untaxed = 0
        for l in purchase.order_line:
            if l.price_total == l.price_subtotal:
                total_untaxed += l.price_subtotal
        return total_untaxed

    def get_amount_taxed(self, purchase):
        total_taxed = 0
        for l in purchase.order_line:
            if l.price_total != l.price_subtotal:
                total_taxed += l.price_subtotal
        return total_taxed

