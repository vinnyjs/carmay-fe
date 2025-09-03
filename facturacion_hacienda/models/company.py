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
import contextlib
import os
import requests
import ssl
import tempfile
import json
from odoo.exceptions import UserError

urls = {
    'PRODUCTION_BASE_URL': "https://api.comprobanteselectronicos.go.cr/recepcion/v1/",
    'PRODUCTION_AUTH_URL': "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut/protocol/openid-connect/token",
    'PRODUCTION_CLIENT_ID': "api-prod",

    'STAGING_BASE_URL': "https://api.comprobanteselectronicos.go.cr/recepcion-sandbox/v1/",
    'STAGING_AUTH_URL': "https://idp.comprobanteselectronicos.go.cr/auth/realms/rut-stag/protocol/openid-connect/token",
    'STAGING_CLIENT_ID': "api-stag"
}


def get_information_from_mh(self):
    # Consulta en el Ministerio de Hacienda
    # https://api.hacienda.go.cr/fe/ae?identificacion=<identificacion>
    values2update = {}
    for partner in self:
        if not partner.vat or len(partner.vat) < 9:
            raise UserError('Para consultar en el Ministerio de Hacienda, debe de tener número de identificación.')
        data = requests.get(
            'https://api.hacienda.go.cr/fe/ae?identificacion=%s' % (partner.vat,), timeout=5)
        # check if timeout or other error
        if data.status_code != 200:
            data = requests.get(
                'https://apis.gometa.org/cedulas/%s' % (partner.vat,), timeout=5)
            if data.status_code != 200:
                raise UserError('No se pudo obtener información del Ministerio de Hacienda, error: %s' % (data.text,))
        result = data.json()
        if 'tipoIdentificacion' in result:
            identification_type = self.env['identification.type'].search(
                [('code', '=', result['tipoIdentificacion'])], limit=1)
            if identification_type:
                values2update['identification_id'] = identification_type.id
        if 'actividades' in result:
            values2update['receiver_activity_ids'] = [(5, 0, 0)]
            for idx, act in enumerate(result.get('actividades', [])):
                if act['estado'] != 'A':
                    continue
                if act['codigo'].startswith('0'):
                    act['codigo'] = act['codigo'][1:]
                actividad = self.env['codigo.actividad'].search([('code', 'ilike', act['codigo'])], limit=1)
                if actividad:
                    values2update['receiver_activity_ids'].append((0, 0, {
                        'actividad_id': actividad.id,
                        'sequence': idx + 1
                    }))
        partner.write(values2update)


class CodigoActividadOrdenados(models.Model):
    _name = 'codigo.actividad.ordenados'
    _order = 'sequence'

    sequence = fields.Integer('Secuencia', required=True)
    actividad_id = fields.Many2one('codigo.actividad', 'Código de actividad', required=True)
    company_id = fields.Many2one('res.company', 'Compañía', required=False)
    partner_id = fields.Many2one('res.partner', 'Compañía', required=False)

    _sql_constraints = [
        ('sequence_uniq', 'unique(actividad_id, company_id)', 'La actividad ya fue asignada a la compañía'),
        ('partner_uniq', 'unique(actividad_id, partner_id)', 'La actividad ya fue asignada al cliente'),
    ]

class CodigoActividad(models.Model):
    _name = 'codigo.actividad'

    name = fields.Char('Nombre', required=True)
    code = fields.Text('Código de actividad', required=True)

    @api.multi
    def name_get(self):
        return [(act.id, "[%s] %s" % (act.code, act.name)) for act in self]
    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        if not args:
            args = []

        if name:
            args.append(('code', operator, name))
            args.append(('name', operator, name))
            args.insert(0, '|')
        actividades = self.search(args, limit=limit)
        return actividades.name_get()

class ResCompany(models.Model):

    _inherit = 'res.company'

    token_hacienda = fields.Char('Token', readonly=1)

    llave_hacienda = fields.Binary('Llave')
    fname_llave_hacienda = fields.Char('Nombre Archivo')
    clave_llave = fields.Char('Contraseña de token')

    usuario_hacienda = fields.Char('Usuario hacienda')
    clave_hacienda = fields.Char('Clave hacienda')

    test = fields.Boolean('Test?', help='Marque esta opción en caso que necesite solamente hacer pruebas')
    tipo_url = fields.Char(string='Tipo URL', compute='_compute_tipo_url', store=True)
    codigo_ids = fields.One2many('codigo.actividad.ordenados', 'company_id', 'Códigos de actividad')
    cod_proveedor_fe = fields.Char('Código proveedor FE', help='Código de proveedor para Factura Electrónica')

    def get_information_from_mh(self):
        return get_information_from_mh(self)

    @api.depends('test')
    def _compute_tipo_url(self):
        for company in self:
            if company.test:
                company.tipo_url = 'STAGING_'
            else:
                company.tipo_url = 'PRODUCTION_'

    def get_url(self, url):
        tipo_url = self.tipo_url
        if not tipo_url:
            self._compute_tipo_url()
        return urls[self.tipo_url + url]

    def get_token(self):
        data = {
            "client_id": self.get_url('CLIENT_ID'),
            "username": self.usuario_hacienda,
            "password": self.clave_hacienda,
            "client_secret": self.get_url('CLIENT_ID'),
            "grant_type": "password"
        }
        headers = {'Content-type': 'application/x-www-form-urlencoded'}
        response = requests.post(self.get_url('AUTH_URL'), data=data, headers=headers, timeout=70)
        if (int(response.status_code) == 200):
            result = response.json()
            token = "bearer "+result.get('access_token')
            self.sudo().write(dict(token_hacienda=token))
            return token
        else:
            pass #raise UserError("Hubo un error al obtener el token ")

ResCompany()

class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_information_from_mh(self):
        return get_information_from_mh(self)

