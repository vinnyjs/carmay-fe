# -*- coding: utf-8 -*-
from odoo import models, api, fields

class AccountInvoice(models.Model):
    _inherit ='account.invoice'

    cod_presupuestario = fields.Integer('Código presupuestario')
    mes_cobro = fields.Char('Mes de Cobro')
    num_dias_servicio = fields.Integer('Num de días que se brindó el servicio')
    num_estudiantes = fields.Integer('Num de estudiantes transportados en el mes')
    tarifa_autorizada = fields.Monetary('Tarifa autorizada para la ruta')
    monto_factura = fields.Monetary('Monto de factura por el mes')

AccountInvoice()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
