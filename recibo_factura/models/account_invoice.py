
# -*- coding: utf-8 -*-
from odoo import models, api, fields

class AccountInvoice(models.Model):
    _inherit ='account.invoice'

    @api.multi
    def get_payment_ref(self):
        pagos = self.payment_move_line_ids
        if not len(pagos):
                return ""
        return pagos[0].move_id.name

AccountInvoice()



class AccountPayment(models.Model):
    _inherit ='account.payment'

    invoice_id = fields.Many2one('account.invoice', string="Factura")

    def myself(self):
        self.ensure_one()
        self.name = "Registro de pago"
        if not len(self.invoice_ids):
            return False
        invoice_id = self.invoice_ids[0].id
        self.invoice_id = invoice_id
        view_id = self.env.ref('account.view_account_payment_invoice_form', False)
        return {
            'context': {'active_id': invoice_id, 'active_ids': [invoice_id], 'docs': [invoice_id]},
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'view_id': view_id and view_id.id or False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


    @api.multi
    def post(self):
        result = super(AccountPayment, self).post()
        return self.myself()

    @api.multi
    def cancel(self):
        super(AccountPayment, self).cancel()
        for rec in self:
            rec.move_name = False

AccountPayment()
