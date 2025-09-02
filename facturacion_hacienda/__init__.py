# -*- coding: utf-8 -*-
##############################################################################
#    Web PDF Report Preview & Print
#    Copyright 2014 wangbuke <wangbuke@gmail.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################

from . import models, controllers, reports
from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    plazos = env['account.payment.term']
    diarios = env['account.journal']
    contado = env.ref('cr_electronic_invoice.SaleConditions_1')
    credito = env.ref('cr_electronic_invoice.SaleConditions_2')
    for payment_term in plazos.search([]):
        dias = payment_term.line_ids[0].days
        if dias == 0:
            payment_term.sale_conditions_id = contado.id
        elif dias > 0:
            payment_term.sale_conditions_id = credito.id
    values2updpate = {'use_date_range': False, 'padding': 8, 'prefix': False,
                            'suffix': False, 'number_next_actual': 1, 'number_increment': 1, 'refund_sequence': True}

    for journal in diarios.search([('type', 'in', ('sale', 'purchase'))]):
        sequence = journal.sequence_id
        if sequence:
            sequence.write(values2updpate)
        refund_sequence = journal.refund_sequence_id
        if refund_sequence:
            refund_sequence.write(values2updpate)

    env['ir.values'].sudo().set_default(
        'sale.config.settings', 'sale_pricelist_setting', 'formula')

    template = env.ref('account.email_template_edi_invoice')
    template.write({
        'email_from': """${object.user_id.name + < object.env['res.users'].sudo().browse(1).email >}""",
        'reply_to': """${ object.user_id.email }"""
    })

    cr.commit()
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
