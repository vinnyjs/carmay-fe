# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
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
#
##############################################################################

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_open(self):
        for inv in self:
            if inv.xml_supplier_approval and not inv.state_invoice_partner:
                raise UserError('Debe seleccionar una respuesta antes de validar la factura.')

        return super(AccountInvoice, self).action_invoice_open()

    @api.multi
    def generar_compra(self):
        productos = self.invoice_line_ids.mapped('product_id.id')
        if productos:
            if not all(productos):
                raise UserError('Para crear una compra todas las lineas deben tener un producto asignado')
        else:
            raise UserError('Para crear una compra todas las lineas deben tener un producto asignado')
        #'partner_id', 'partner_ref', 'date_order', 'payment_term_id'
        invoice_body = self.read(['partner_id', 'reference',  'currency_id', 'date_invoice', 'payment_term_id'])[0]
        invoice_lines = self.invoice_line_ids.read(['product_id', 'quantity', 'uom_id', 'price_unit', 'discount', 'invoice_line_tax_ids', 'name', 'id'])

        purchase_body = dict.copy(invoice_body)
        purchase_body['partner_id'] = purchase_body['partner_id'][0]
        purchase_body['currency_id'] = purchase_body['currency_id'][0]
        purchase_body['partner_ref'] = purchase_body['reference']
        purchase_body['date_order'] = purchase_body['date_invoice']
        payment_term = purchase_body.get('payment_term_id', False)
        purchase_body['payment_term_id'] = payment_term and payment_term[0] or False
        del purchase_body['reference']
        del purchase_body['date_invoice']

        new_purchase = self.env['purchase.order'].create(purchase_body)
        if new_purchase:
            self.write({'purchase_id': new_purchase.id})
        else:
            return False
        purchase_id = new_purchase.id
        purchase_order_line_env = self.env['purchase.order.line']
        account_invoice_line_env = self.env['account.invoice.line']
        for l in invoice_lines:
            line_vals = {
                'product_id': l['product_id'][0],
                'name': l['name'],
                'product_qty': l['quantity'],
                'product_uom': l.get('uom_id', False) and l['uom_id'][0] or 1,
                'price_unit': l['price_unit'] - (l['price_unit'] * (l['discount'] / 100)),
                'taxes_id': [(6, 0, l['invoice_line_tax_ids'])],
                'date_planned': purchase_body['date_order'],
                'order_id': purchase_id
            }
            line_id = purchase_order_line_env.create(line_vals)
            account_invoice_line_env.browse(l['id']).write({'purchase_line_id': line_id.id})

        #purchase_body.update({'order_line': purchase_lines})





AccountInvoice()
