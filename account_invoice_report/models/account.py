# -*- coding: utf-8 -*-
from odoo import models, api, fields
import time
from dateutil.parser import parse
from odoo.tools.misc import formatLang
import logging
_logger = logging.getLogger(__name__)

class AccountInvoice(models.Model):
    _inherit ='account.invoice'

    @api.one
    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'currency_id', 'company_id', 'date_invoice', 'type')
    def _compute_amount_inherit(self):
        super(AccountInvoice, self)._compute_amount()
        amount_total_discount = sum((line.price_unit - line.price_with_discount) * line.quantity for line in self.invoice_line_ids)
        #amount_total_discount = sum((line.price_unit - line.price_with_discount) for line in self.invoice_line_ids)
        self.amount_total_discount = amount_total_discount
        _logger.info(amount_total_discount)
        return {'amount_total_discount': amount_total_discount}

    @api.multi
    def fillLines(self):
        lines = []
        for l in self.invoice_line_ids:
            lines.append({"l": l})
        return lines

    @api.multi
    def compute_discount(self):
        for inv in self:
            inv.amount_total_discount = sum((line.price_unit - line.price_with_discount) * line.quantity for line in inv.invoice_line_ids)


    @api.multi
    def espaces(self):
        lines = 0
        if self.lineas_extra:
            return map(lambda x: {"blank": True}, range(int(self.lineas_extra)))
        for l in self.invoice_line_ids:
            length = len(l.name)
            result = (length > 29 and (len(l.name[:45]) / 29.0) or 1.0)
            if int(str(result).split('.')[1]) > 0:
                result = int(result) + 1
            lines += result
        #lines = len(self.invoice_line_ids)
        res = 25 - lines
        return map(lambda x: {"blank": True}, range(int(res)))

    _compute_amount = _compute_amount_inherit

    amount_total_discount = fields.Monetary(string='Descuento Total',
                                   store=True, readonly=True, compute='_compute_amount')

    nombre_facturar = fields.Char('Nombre a facturar')
    lineas_extra = fields.Float('Lineas extras en plantilla de impresión', help='Añade la cantidad de lineas asignadas a la plantilla del informe en caso que este se muestre distorcionado')


    def convertPartnerName(self, partner_name):
        if '--' in partner_name:
            return partner_name[:partner_name.index('--')]
        if self.partner_id.ref:
            partner_name += " " + self.partner_id.ref
        return partner_name

    def getPartnerCode(self, partner_name):
        if '--' in partner_name:
            return partner_name[partner_name.index('--'):].replace('--', '')
        return partner_name

    @api.multi
    def format(self, numero):
        return formatLang(self.with_context(lang=self.partner_id.lang).env, numero)

    @api.multi
    def invoice_print_inherit(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        self.sent = True
        #return self.env['report'].get_action(self, 'account_invoice_report.report_account_invoice_derkoch')
        return self.env['report'].get_action(self, 'account_invoice_report.report_account_invoice_facturaelectronica')

    invoice_print = invoice_print_inherit

    project_id = fields.Many2one('account.analytic.account', 'Proyecto')


AccountInvoice()

class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    price_with_discount = fields.Float('Precio con descuento', compute='_compute_price', store=True)
    tax_amount = fields.Float('Monto Impuesto', compute='_compute_price', store=True)

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
        'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id', 'invoice_id.company_id',
        'invoice_id.date_invoice')
    def _compute_price_inherit(self):
        super(AccountInvoiceLine, self)._compute_price()
        price_with_discount = self.price_unit - (self.price_unit*self.discount/100.0)
        self.price_with_discount = price_with_discount
        tax_result = 0
        if self.invoice_line_tax_ids:
            tax_result = self.invoice_line_tax_ids.compute_all(price_with_discount, self.currency_id, self.quantity, False,
                                              self.partner_id)['taxes'][0].get('amount', 0)
        self.tax_amount = tax_result

    _compute_price = _compute_price_inherit

AccountInvoiceLine()
