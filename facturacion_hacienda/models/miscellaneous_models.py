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
import logging
import odoo
from odoo import models, fields, api, _, SUPERUSER_ID, registry
from odoo.exceptions import UserError

class CodeTypeProduct(models.Model):
    _name = "code.type.product"

    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )

    _sql_constraints = [
        ('code_uniq', 'unique (code)', "El código ya ha sido asignado!"),
    ]


class ProductElectronic(models.Model):
    _inherit = "product.template"

    @api.model
    def _default_code_type_id(self):
        code_type_id = self.env['code.type.product'].search([('code', '=', '04')], limit=1)
        return code_type_id or False

    commercial_measurement = fields.Char(string="Unidad de Medida Comercial", required=False, )
    code_type_id = fields.Many2one(comodel_name="code.type.product", string="Tipo de código", required=False,
                                   default=_default_code_type_id)

    @api.model
    def create(self, vals):
        if not vals.get('company_id', False):
            vals.update({'company_id': self.env.user.company_id.id})
        return super(ProductElectronic, self).create(vals)

    @api.multi
    def write(self, vals):
        if not vals.get('company_id', False):
            vals.update({'company_id': self.env.user.company_id.id})
        return super(ProductElectronic, self).write(vals)

ProductElectronic()

class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def create(self, vals):
        if not vals.get('company_id', False):
            vals.update({'company_id': self.env.user.company_id.id})
        return super(ProductProduct, self).create(vals)

    @api.multi
    def write(self, vals):
        if not vals.get('company_id', False):
            vals.update({'company_id': self.env.user.company_id.id})
        return super(ProductProduct, self).write(vals)

ProductProduct()

class ElectronicTaxCode(models.Model):
    _name = "account.tax.cr.code"

    name = fields.Char(string="Descripción", required=True)
    code = fields.Char(string="Código de impuesto", required=True)
    active = fields.Boolean('Activo', default=True)

    _sql_constraints = [
        ('code_uniq', 'unique (code)', "El código ya ha sido asignado!"),
    ]


class  FiscalPositionTax(models.Model):
    _inherit = "account.fiscal.position.tax"

    porc_auth = fields.Integer(string="Porcentaje de la compra exonerado", required=True)


class InvoiceTaxElectronic(models.Model):
    _inherit = "account.tax"

    tax_code = fields.Many2one("account.tax.cr.code", string="Código de impuesto", required=False)
    cod_tarifa = fields.Selection([('01', 'Tarifa 0% (Exento)'),
                                   ('02', 'Tarifa Reducida 1%'),
                                   ('03', 'Tarifa reducida 2%'),
                                   ('04', 'Tarifa reducida 4%'),
                                   ('05', 'Transitorio 0%'),
                                   ('06', 'Transitorio 4%'),
                                   ('07', 'Transitorio 8%'),
                                   ('08', 'Tarifa General 13%')
                                   ],
                                  "Código de la tarifa del impuesto.")


# class Exoneration(models.Model):
# 	_name = "exoneration"
#
# 	code = fields.Char(string="Código", required=False, )
# 	type = fields.Char(string="Tipo", required=False, )
# 	exoneration_number = fields.Char(string="Número de exoneración", required=False, )
# 	name_institution = fields.Char(string="Nombre de institución", required=False, )
# 	date = fields.Date(string="Fecha", required=False, )
# 	percentage_exoneration = fields.Float(string="Porcentaje de exoneración", required=False, )


class PaymentMethods(models.Model):
    _name = "payment.methods"

    active = fields.Boolean(string="Activo", required=False, default=True)
    sequence = fields.Char(string="Secuencia", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )


class SaleConditions(models.Model):
    _name = "sale.conditions"

    active = fields.Boolean(string="Activo", required=False, default=True)
    sequence = fields.Char(string="Secuencia", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"
    sale_conditions_id = fields.Many2one(comodel_name="sale.conditions", string="Condiciones de venta")


class ReferenceDocument(models.Model):
    _name = "reference.document"

    active = fields.Boolean(string="Activo", required=False, default=True)
    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )

ReferenceDocument()

class ReferenceCode(models.Model):
    _name = "reference.code"

    active = fields.Boolean(string="Activo", required=False, default=True)
    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )

ReferenceCode()

class Resolution(models.Model):
    _name = "resolution"

    active = fields.Boolean(string="Activo", required=False, default=True)
    name = fields.Char(string="Nombre", required=False, )
    date_resolution = fields.Datetime(string="Fecha de resolución", required=False, )

Resolution()

class ProductUom(models.Model):
    _inherit = "product.uom"

    commercial_measurement_id = fields.Many2one("unit.measure.code", string="Unidad de Medida Comercial" )
    code = fields.Char(string="Código", required=False, store=True, related="commercial_measurement_id.code")

ProductUom()

class AccountJournal(models.Model):
    _inherit = "account.journal"
    nd = fields.Boolean(string="Nota de Débito", required=False, )

    sucursal = fields.Selection([('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'), ('05', '05')],
                                string='Sucursal', default="01")
    terminal = fields.Selection([('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'), ('05', '05')],
                                      string='Punto de Venta', default="01")

    impuesto_servicio = fields.Boolean('Impuesto de servicio', help="Aplica automaticamente el impuesto de servicio a la factura")

    exportacion = fields.Boolean('Diario para facturas de exportación?')

    def _create_sequence_inherit(self, vals, refund=False):
        """ Create new no_gap entry sequence for every new Journal"""
        seq = {
            'name': refund and vals['name'] + _(': Reembolso') or vals['name'],
            'implementation': 'no_gap',
            'prefix': '',
            'padding': 8,
            'number_increment': 1,
            'use_date_range': False,
        }
        if 'company_id' in vals:
            seq['company_id'] = vals['company_id']
        return self.env['ir.sequence'].create(seq)

    _create_sequence = _create_sequence_inherit


class IdentificationType(models.Model):
    _name = "identification.type"

    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )

class MailTemplate(models.Model):
    _inherit = "mail.template"

    @api.multi
    def write(self, vals):
        if self.id == self.env.ref('account.email_template_edi_invoice', False).id and self.env.user.id != 1:
            raise UserError('No puede modificar esta plantilla')
        return super(MailTemplate, self).write(vals)

class UnitMeasureCode(models.Model):
    _name = 'unit.measure.code'

    code = fields.Char("Código")
    name = fields.Char("Nombre")