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
from odoo.addons.base.res.res_currency import CurrencyRate, Currency
from odoo.addons.base.res.res_partner import Partner
from odoo.addons.base.res.res_company import Company
from odoo.addons.mail.models.mail_template import MailTemplate

"""
agrega campos a Usuarios para lo que es la sucursal y punto de venta
"""
class ResUsers(models.Model):
    _inherit = 'res.users'

    sucursal = fields.Selection([('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'), ('05', '05')],
                                string='Sucursal')
    punto_de_venta = fields.Selection([('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'), ('05', '05')],
                                      string='Punto de Venta')
ResUsers()

"""
Actualiza el rate de la moneda para que aguante más decimales
"""
class ResCurrencyRate(CurrencyRate):
    _inherit = 'res.currency.rate'

    CurrencyRate.rate = fields.Float(digits=(16, 18), help='The rate of the currency to the currency of rate 1')

ResCurrencyRate()


class ResCurrency(Currency):
    _inherit = 'res.currency'

    Currency.rate = fields.Float(compute='_compute_current_rate', string='Current Rate', digits=(16, 18),
                                 help='The rate of the currency to the currency of rate 1.')
ResCurrency()

"""
Metodo utilizado para ser consumido en las vistas con el fin de brindar el tipo de cambio 
actual de las monedas utilizadas en el siste
"""
class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def get_tipo_cambio(self):
        cr = self.env.cr
        query = """select distinct on (rc.id) rc.id, rcr.name as date, rcr.rate as rate, rc.name as name from res_currency rc\
                    inner join res_currency_rate rcr on rcr.currency_id=rc.id \
                    order by rc.id, rcr.name desc;"""
        cr.execute(query)
        result = cr.dictfetchall()
        if not len(result):
            return False
        return result

ResCurrency()

"""
Herencia a las plantillas de correo para poner enviar más de un archivo adjunto
"""
class MailTemplateInherit(MailTemplate):
    _inherit = "mail.template"

    def generate_email_inherit(self, res_ids, fields=None):
        result = super(MailTemplateInherit, self).generate_email(res_ids, fields)
        another_attachment = self.env.context.get('another_attachment')
        if another_attachment:
            for r in result.copy():
                result[r]['attachments'].append(another_attachment)
        return result

    generate_email = generate_email_inherit

MailTemplateInherit()




def validar_numeros(num, max=20):
    numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    msj = False
    if num:
        if len(num) > max:
            return {
                'title': 'Atención',
                'message': "Número no puede ser mayor a 20 digitos"
            }

        for p in str(num):
            if p not in numbers:
                return {
                    'title': 'Atención',
                    'message': 'Favor no introducir letras, espacios ni guiones en los números telefónicos.'
                }
    return False


class ValidationData(models.Model):
    _register = False

    @api.onchange('phone')
    def _onchange_phone(self):
        msj = validar_numeros(self.phone)
        if msj:
            return {'value': {'phone': ''}, 'warning': msj}

    @api.onchange('mobile')
    def _onchange_mobile(self):
        msj = validar_numeros(self.mobile)
        if msj:
            return {'value': {'mobile': ''}, 'warning': msj}

    @api.onchange('phone_code')
    def _onchange_phone_code(self):
        msj = validar_numeros(self.phone_code)
        if msj:
            return {'value': {'phone_code': ''}, 'warning': msj}

    @api.onchange('fax_code')
    def _onchange_fax_code(self):
        msj = validar_numeros(self.fax_code)
        if msj:
            return {'value': {'fax_code': ''}, 'warning': msj}

    @api.onchange('fax')
    def _onchange_fax(self):
        msj = validar_numeros(self.fax)
        if msj:
            return {'value': {'fax': ''}, 'warning': msj}


    @api.onchange('vat', 'identification_id', 'ref')
    def _onchange_vat(self):
        if self.identification_id:
            code = self.identification_id.code
            ced = self.vat or self.ref
            if not ced:
                return
            if code == '01':
                if len(ced) != 9:
                    raise UserError(
                        'La identificación tipo Cédula física debe de contener 9 dígitos, sin cero al inicio y sin guiones.')
            if code == '02':
                if len(ced) != 10:
                    raise UserError(
                        'La identificación tipo Cédula jurídica debe contener 10 dígitos, sin cero al inicio y sin guiones.')
            if code == '03':
                if len(ced) < 11 or len(ced) > 12:
                    raise UserError(
                        'La identificación tipo DIMEX debe contener 11 o 12 dígitos, sin ceros al inicio y sin guiones.')
            if code == '04':
                if len(ced) != 9:
                    raise UserError(
                        'La identificación tipo NITE debe contener 10 dígitos, sin ceros al inicio y sin guiones.')
            if code == '05':
                if len(ced) < 10 or len(ced) > 20:
                    raise UserError('La identificación tipo Extrangero debe ser de 10 dígitos.')
        if self.vat and not self.ref:
            return {'value': {'ref': self.vat}}

        elif self.ref and not self.vat:
            return {'value': {'vat': self.vat}}

ValidationData()


class PartnerElectronic(ValidationData, models.Model):
    _inherit = "res.partner"

    commercial_name = fields.Char(string="Nombre comercial", required=False, )
    phone_code = fields.Char(string="Código de teléfono", required=False, default="506")
    fax_code = fields.Char(string="Código de Fax", required=False, default="506")
    state_id = fields.Many2one(comodel_name="res.country.state", string="Provincia", required=False, )
    district_id = fields.Many2one(comodel_name="res.country.district", string="Distrito", required=False, )
    county_id = fields.Many2one(comodel_name="res.country.county", string="Cantón", required=False, )
    neighborhood_id = fields.Many2one(comodel_name="res.country.neighborhood", string="Barrios", required=False, )
    identification_id = fields.Many2one(comodel_name="identification.type", string="Tipo de identificacion",
                                        required=True)
    payment_methods_id = fields.Many2one(comodel_name="payment.methods", string="Métodos de Pago" )

    _sql_constraints = [
        ('vat_uniq', 'unique (vat)', "La cédula debe ser única"),
    ]

    @api.onchange('email')
    def _onchange_email(self):
        if self.email:
            if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", self.email.lower()):
                vals = {'email': False}
                alerta = {
                    'title': 'Atención',
                    'message': 'El correo electrónico no cumple con una estructura válida. ' + str(self.email)
                }
                return {'value': vals, 'warning': alerta}


class ResPartner(Partner):
    _inherit = 'res.partner'

    Partner.ref = fields.Char(string='Cédula', index=True, required=True)

ResPartner()


class ResCompany(Company):
    _inherit = 'res.company'

    country_id = fields.Many2one('res.country', compute='_compute_address', inverse='_inverse_country',
                                 string="País", required=True)
    state_id = fields.Many2one('res.country.state', compute='_compute_address', inverse='_inverse_state',
                               string="Provincia", required=True)
    street = fields.Char(compute='_compute_address', inverse='_inverse_street', required=True, string='Otras Señas')

ResCompany()


class CompanyElectronic(ValidationData, models.Model):
    _name = 'res.company'
    _inherit = ['res.company', 'mail.thread', 'ir.needaction_mixin']

    commercial_name = fields.Char(related='partner_id.commercial_name', string="Nombre comercial", required=False, )
    phone_code = fields.Char(related='partner_id.phone_code', string="Código de teléfono", required=False, size=3,
                             default="506")
    fax_code = fields.Char(related='partner_id.fax_code', string="Código de Fax", required=False, )

    identification_id = fields.Many2one(related='partner_id.identification_id', string="Tipo de identificacion",
                                        required=True, )
    district_id = fields.Many2one(related='partner_id.district_id', string="Distrito", required=True, )
    county_id = fields.Many2one(related='partner_id.county_id', string="Cantón", required=True, )
    neighborhood_id = fields.Many2one(related='partner_id.neighborhood_id', string="Barrios", required=True)
    ref = fields.Char(related='partner_id.ref', string='Cédula', index=True, required=True)


CompanyElectronic()
