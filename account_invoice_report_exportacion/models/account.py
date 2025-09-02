# -*- coding: utf-8 -*-
from odoo import models, api, fields
import time
from dateutil.parser import parse
from odoo.tools.misc import formatLang
from odoo.tools import amount_to_text_en
from dateutil.parser import parse

class AccountInvoice(models.Model):
    _inherit ='account.invoice'

    export_id = fields.Char()
    consigned_to = fields.Text('Consigned To')
    sold_to = fields.Text('Sold To')
    shipping_line = fields.Char()
    vessel = fields.Char()
    voyage = fields.Char()
    bill_of_lading = fields.Char()
    container = fields.Char()
    seal = fields.Char()
    country_of_origin = fields.Char()
    port_of_loading = fields.Char()
    country_of_destination = fields.Char()
    point_of_entry = fields.Char()
    purchase_order = fields.Char()

    def number2word(self, amount):
        return amount_to_text_en.amount_to_text(amount, 'en', 'US dollars')

    @api.multi
    def fillLines(self):
        lines = []
        new_line = self.env['account.invoice.line']
        for l in self.invoice_line_ids:
            lines.append(l)
        current_lines = len(self.invoice_line_ids)
        if current_lines < 5:
            for l in range(5-current_lines):
                lines.append(new_line.new())
        return lines

    @api.multi
    def parse_date(self, date):
        date = parse(date)
        return date.strftime('%B %d, %Y').capitalize()

    @api.multi
    def fillLinesContainer(self):
        lines = []
        for l in range(7):
            lines.append({"l": l})
        return lines

AccountInvoice()
class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    pack_type = fields.Char()
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')

AccountInvoiceLine()