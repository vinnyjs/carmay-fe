# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError as UserError
import random
from dateutil.parser import parse
from datetime import timedelta, datetime
from odoo.tools.translate import _
import re
from odoo import models, fields, api
import requests
import logging

_logger = logging.getLogger(__name__)


class Partner(models.Model):
    _inherit = 'res.partner'

    exonerations_ids = fields.One2many('customer.exoneration', 'partner_id', 'Exoneraciones')
    exonerated = fields.Boolean('Exonerado', compute='_compute_exonerated')

    @api.depends('exonerations_ids')
    def _compute_exonerated(self):
        for partner in self:
            partner.exonerated = any(exon.active for exon in partner.exonerations_ids)



class SaleOrder(models.Model):
    _inherit = 'sale.order'

    exoneration_id = fields.Many2one('customer.exoneration', 'Exoneración')
    checked_exoneration = fields.Boolean('Exoneración verificada', related='exoneration_id.check_exoneration', store=True)

    @api.onchange('exoneration_id')
    def _onchange_exoneration_id(self):
        if self.exoneration_id:
            self.fiscal_position_id = self.exoneration_id.fiscal_position_id
        else:
            self.fiscal_position_id = False

    def check_cabys(self):
        if self.exoneration_id and not self.exoneration_id.skip_cabys_check:
            no_valid_cabys = []
            valid_cabys = (self.exoneration_id.exonerated_codes or "").split(',')
            for idx, line in enumerate(self.order_line):
                if line.codigo_cabys:
                    if line.codigo_cabys not in valid_cabys:
                        no_valid_cabys.append([idx, line.name])

            if no_valid_cabys:
                msg = 'Los siguientes productos no son válidos para la exoneración seleccionada: \n' + '\n'.join(['Linea %s: %s' % (idx+1, name) for idx, name in no_valid_cabys])
                raise UserError(msg)

    def action_confirm(self):
        self.check_cabys()
        return super(SaleOrder, self).action_confirm()

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res['exoneration_id'] = self.exoneration_id.id
        res['tipo_documento_pf'] = self.exoneration_id.ttype
        res['numero_documento_pf'] = self.exoneration_id.name
        res['nombre_institucion_pf'] = self.exoneration_id.institution
        res['fecha_emision_pf'] = self.exoneration_id.date
        return res

class SaleLine(models.Model):
    _inherit = 'sale.order.line'

    check_exoneration = fields.Boolean('Verificar exoneración', related='order_id.checked_exoneration', store=True)
    codigo_cabys = fields.Char('Código CABYS')
    cabys_valid = fields.Boolean('CABYS válido', compute='_compute_cabys_valid')

    @api.depends('codigo_cabys')
    def _compute_cabys_valid(self):
        for line in self:
            if line.order_id.exoneration_id:
                if line.codigo_cabys:
                    line.cabys_valid = line.codigo_cabys in (line.order_id.exoneration_id.exonerated_codes or "").split(',')
                else:
                    line.cabys_valid = False
            else:
                if len(str(line.codigo_cabys).strip()) < 13:
                    line.cabys_valid = False
                else:
                    line.cabys_valid = True

    @api.onchange('product_id')
    def _onchange_product_id_exoneration(self):
        if self.product_id and self.product_id.codigo_cabys:
            self.codigo_cabys = self.product_id.codigo_cabys
        else:
            self.codigo_cabys = False
        if self.order_id.exoneration_id and not self.order_id.exoneration_id.skip_cabys_check and self.codigo_cabys:
            if self.order_id.exoneration_id and not self.order_id.exoneration_id.skip_cabys_check and not (self.codigo_cabys in (self.order_id.exoneration_id.exonerated_codes or "").split(',')):
                msg = 'El producto seleccionado no es válido para la exoneración seleccionada.'
                return {
                    'warning': {
                        'title': 'Advertencia',
                        'message': msg
                    }
                }

    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleLine, self)._prepare_invoice_line(**optional_values)
        res['codigo_cabys'] = self.codigo_cabys
        return res

class InvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    check_exoneration = fields.Boolean('Verificar exoneración', related='invoice_id.checked_exoneration', store=True)
    codigo_cabys = fields.Char('Código CABYS')

    @api.onchange('product_id')
    def _onchange_product_id_exoneration(self):

        if self.product_id and self.product_id.codigo_cabys:
            self.codigo_cabys = self.product_id.codigo_cabys
            if self.invoice_id.exoneration_id and not self.invoice_id.exoneration_id.skip_cabys_check and not (self.codigo_cabys in (self.invoice_id.exoneration_id.exonerated_codes or "").split(',')):
                msg = 'El producto seleccionado no es válido para la exoneración seleccionada.'
                return {
                    'warning': {
                        'title': 'Advertencia',
                        'message': msg
                    }
                }

    @api.model
    def create(self, vals):
        if 'codigo_cabys' not in vals and 'product_id' in vals:
            product = self.env['product.product'].browse(vals['product_id'])
            if product.codigo_cabys:
                vals['codigo_cabys'] = product.codigo_cabys
        return super(InvoiceLine, self).create(vals)

class Invoice(models.Model):
    _inherit = 'account.invoice'

    exoneration_id = fields.Many2one('customer.exoneration', 'Exoneración')
    checked_exoneration = fields.Boolean('Exoneración verificada', related='exoneration_id.check_exoneration', store=True)

    @api.onchange('exoneration_id')
    def _onchange_exoneration_id(self):
        if self.exoneration_id:
            self.fiscal_position_id = self.exoneration_id.fiscal_position_id
        else:
            self.fiscal_position_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id_exoneration(self):
        if self.partner_id:
            exon = self.partner_id.exonerations_ids.filtered(lambda exon: exon.active)
            if exon:
                self.exoneration_id = exon[0]
            else:
                self.exoneration_id = False

    @api.onchange('exoneration_id')
    def _onchange_exoneration_id(self):
        if self.exoneration_id:
            self.fiscal_position_id = self.exoneration_id.fiscal_position_id
            self.tipo_documento_pf = self.exoneration_id.ttype
            self.numero_documento_pf = self.exoneration_id.name
            self.nombre_institucion_pf = self.exoneration_id.institution
            self.fecha_emision_pf = self.exoneration_id.date


class ExonerationsInstitutionName(models.Model):
    _name = 'exoneration.institution'
    _description = 'Exoneration Institution Name'

    name = fields.Char('Nombre de la institución', required=True)
    code = fields.Char('Código de la institución', required=True, help='Código único para identificar la institución de exoneración')
    other = fields.Boolean('Otra institución', default=False, help='Indica si es una institución no listada en el catálogo oficial de instituciones de exoneración')

class Exonerations(models.Model):
    _name = 'customer.exoneration'

    ttype = fields.Selection([
        ('01', '01 - Compras autorizadas por la Dirección General de Tributación'),
        ('02', '02 - Ventas exentas a diplomáticos'),
        ('03', '03 - Autorizado por Ley Especial'),
        ('04', '04 - Exenciones Dirección General de Hacienda Autorización Local Genérica'),
        ('05', '05 - Exenciones Dirección General de Hacienda Transitorio V (servicios de ingeniería, arquitectura, topografía obra civil)'),
        ('06', '06 - Servicios turísticos inscritos ante el Instituto Costarricense de Turismo (ICT)'),
        ('07', '07 - Transitorio XVII (Recolección, Clasificación, almacenamiento de Reciclaje y reutilizable)'),
        ('08', '08 - Exoneración a Zona Franca'),
        ('09', '09 - Exoneración de servicios complementarios para la exportación articulo 11 RLIVA'),
        ('10', '10 - Órgano de las corporaciones municipales'),
        ('11', '11 - Exenciones Dirección General de Hacienda Autorización de Impuesto Local Concreta'),
        ('99', '99 - Otros')
    ], 'Tipo', required=True)
    name = fields.Char('Número de documento', required=True)
    percentage = fields.Float('Porcentaje')
    institution = fields.Char('Institución') # deprecated
    institution_id = fields.Many2one('exoneration.institution', 'Institución', required=True)
    article = fields.Integer('Artículo', help='Artículo de la ley o norma que autoriza la exoneración')
    subsection = fields.Integer('Inciso', help='Inciso de la ley o norma que autoriza la exoneración')
    date = fields.Date('Fecha de emisión')
    expiration_date = fields.Date('Fecha de vencimiento')
    fiscal_position_id = fields.Many2one('account.fiscal.position', 'Posición fiscal', required=True)
    active = fields.Boolean('Activo', default=True)
    date_notification = fields.Date('Fecha de notificación')
    partner_id = fields.Many2one('res.partner', 'Cliente', required=True)
    exonerated_codes = fields.Char('Códigos de exoneración')
    display_exonerated_codes = fields.Html('Códigos de exoneración', compute='_compute_display_exonerated_codes')
    check_exoneration = fields.Boolean('Verificar exoneración', default=False)
    codigo_proyecto_cfia = fields.Char('Código de proyecto CFIA')
    autorization_number = fields.Char('Autorización')
    document = fields.Binary('Documento')
    fname_document = fields.Char('Nombre del documento')
    skip_cabys_check = fields.Boolean('Saltar verificación de CABYS', default=False, copy=False)
    cliente_exento = fields.Boolean('Cliente exento?', default=False)
    no_sujeto = fields.Boolean('No sujeto?', default=False)
    ley_zona_franca = fields.Boolean('LEY 7210?(Zona Franca)', default=False)

    @api.onchange('cliente_exento')
    def _onchange_cliente_exento(self):
        if self.cliente_exento:
            self.skip_cabys_check = True
            self.name = 'EXENTO'
            self.check_exoneration = True
            self.ttype = '03'
            self.article = 9
            self.subsection = 2
            self.institution = 'Ministerio de Hacienda'
            self.institution_id = self.env['exoneration.institution'].search([('code', '=', '03')], limit=1)
            if not self.institution_id:
                raise UserError('No se encontró la institución de exoneración para el código 03. Por favor, verifique la configuración.')
            self.date = '2018-12-04'
        else:
            self.skip_cabys_check = False
            self.name = False
            self.check_exoneration = False

    @api.onchange('ley_zona_franca')
    def _onchange_ley_zona_franca(self):
        if self.ley_zona_franca:
            self.skip_cabys_check = True
            self.name = 'LEY 7210'
            self.check_exoneration = True
            self.article = 20
            self.subsection = 5
            self.ttype = '03'
            self.institution = 'Ministerio de Hacienda'
            self.institution_id = self.env['exoneration.institution'].search([('code', '=', '03')], limit=1)
            if not self.institution_id:
                raise UserError('No se encontró la institución de exoneración para el código 03. Por favor, verifique la configuración.')
            self.date = '1990-12-14'
        else:
            self.skip_cabys_check = False
            self.name = False
            self.check_exoneration = False

    @api.depends('exonerated_codes')
    def _compute_display_exonerated_codes(self):
        table = '<table>'
        for exon in self:
            codes = (exon.exonerated_codes or "").split(',')
            for code in codes:
                table += '<tr><td>' + code + '</td></tr>'
            table += '</table>'
            exon.display_exonerated_codes = table

    def request_exoneration(self, exoneration_url):
        import requests


        payload = {}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Cookie': '_ga_D2MYCJNBPJ=GS1.1.1723662840.2.0.1723662846.0.0.0; _ga=GA1.1.1162156796.1714419101; Sesion03d94531=0320156b28df689370ad2fbea3de75162103f74c8222f7768d6f90942e388f3081910a888cf51a1f5e2844ff10f8ea961ae30f7af8; Sesione7271855212=086e354e41ab200058931af20b54833dc86fa2b02b03159033c58cb6fe4ab1205b0a432ef7ac1cab08b0f2644911300042c13a13ca1ccbe05bd17b7856ca6b7920ffd75ad36421f6635400967f77015bf735b25c8da9124b5d5084688d6a5ed7; Sesion03d94531=0320156b28e3e280b11d770bc864004f549ad85d1dcd673ddb29e520859922816214c8c1d5a02acd3d0026fb13fff800aaa3ad10d7; Sesione7271855212=086e354e41ab200080acc37af47875d8b71636712f8310a795bc3c92ec9849a287ed4738d6d78465085ef52d40113000742c634cadfbb9cdc5512982b3605d94618eba807bcb59aa2871203013e63c4bad36c692eebafb99c9b69ff973df676d',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Priority': 'u=0, i',
            'TE': 'trailers'
        }

        response = requests.request("GET", exoneration_url, headers=headers, data=payload)

        return response

    def check_customer_exoneration(self, name):
        if '9635' in self.name or '7210' in self.name:
            ley_num = '7210' if '7210' in name else '9635'
            return {
                'active': True,
                'check_exoneration': True,
                'percentage': 13,
                'name': 'LEY %s' % ley_num,
                'institution': 'Dirección General de Hacienda',
                'date': '2018-12-04T00:00:00',
                'ttype': '03',
                'skip_cabys_check': True,
            }
        url = 'https://api.hacienda.go.cr/fe/ex?autorizacion='
        exoneration_url = url + name
        try:
            exonation_response = self.request_exoneration(exoneration_url).json()
        except Exception as e:
            _logger.error('Error al verificar la exoneración: %s', e)
            return {}
        if 'numeroDocumento' in exonation_response:
            result = {
                'active': True,
                'check_exoneration': True,
                'percentage': exonation_response['porcentajeExoneracion'],
                'institution': exonation_response['nombreInstitucion'],
                'date': exonation_response['fechaEmision'],
                'expiration_date': exonation_response['fechaVencimiento'],
                'exonerated_codes': ','.join(exonation_response['cabys']),
                'codigo_proyecto_cfia': exonation_response['codigoProyectoCFIA'],
                'autorization_number': exonation_response['autorizacion'],
                'ttype': exonation_response['tipoDocumento']['codigo'],
            }
            return result
        else:
            return {}

    def check_expired_exoneration(self):
        for exon in self.search([('active', '=', True), ('check_exoneration', '=', False)]):
            result = self.check_customer_exoneration(exon.name)
            if result:
                exon.write(result)
            else:
                exon.write({'active': True, 'check_exoneration': False})

    @api.onchange('name')
    def _onchange_name(self):
        if self.name:
            values = self.check_customer_exoneration(self.name)
            if values:
                self.update(values)