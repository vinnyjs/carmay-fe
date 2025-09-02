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
import psycopg2
from odoo import models, fields, api, _, SUPERUSER_ID, registry
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import subprocess
import tempfile
import base64
import contextlib
import os
import requests
import simplejson
import threading
from odoo.tools.safe_eval import safe_eval
import pytz
import re
#import xml.etree.ElementTree as ET
from lxml import etree as ET
from dateutil.parser import parse
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from documento_xml import DocumentoXml
import time
import shutil
from odoo.addons.account_report_tools.tools import tools_amount_to_text as amt_text

_logger = logging.getLogger(__name__)
BASE_VERSION = odoo.modules.load_information_from_description_file('base')['version']

import smtplib
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.text import MIMEText

class AccountInvoiceTaxInherit(models.Model):
    _inherit = "account.invoice"

    @api.multi
    def get_taxes_values_inherit(self):
        tax_grouped = {}
        round_curr = self.currency_id.round
        for line in self.invoice_line_ids:
            if int(line.discount) == 100:
                price_unit = line.price_unit
            else:
                price_unit = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.invoice_line_tax_ids.compute_all(price_unit, self.currency_id, line.quantity, line.product_id, self.partner_id)['taxes']
            for tax in taxes:
                val = self._prepare_tax_line_vals(line, tax)
                key = self.env['account.tax'].browse(tax['id']).get_grouping_key(val)

                if key not in tax_grouped:
                    tax_grouped[key] = val
                    tax_grouped[key]['base'] = round_curr(val['base'])
                else:
                    tax_grouped[key]['amount'] += val['amount']
                    tax_grouped[key]['base'] += round_curr(val['base'])
        return tax_grouped
    get_taxes_values = get_taxes_values_inherit

class InvoiceElectronic(models.Model):
    _inherit = 'account.invoice'

    @api.depends('xml_supplier_approval')
    def _compute_amounts_fe(self):
        for i in self:
            if not i.xml_supplier_approval:
                return False
            new_context = i.env.context.copy()
            if 'bin_size' in new_context:
                del new_context['bin_size']
            archivo = base64.b64decode(i.with_context(new_context).xml_supplier_approval)
            try:
                parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
                root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', archivo,
                                        count=1), parser)  # quita el namespace de los elementos
            except Exception as e:
                raise UserError("Por favor cargue un archivo en formato XML.\n%s" % (e.message,))


            resumenFactura = root.findall('ResumenFactura')[0]
            if resumenFactura is not None:
                to_update = {
                    'amount_total_electronic_invoice': float(resumenFactura.findall('TotalComprobante')[0].text)
                }
                total_impuestos = resumenFactura.findall('TotalImpuesto')
                if total_impuestos and total_impuestos is not None and total_impuestos[0].text:
                    to_update.update({'amount_tax_electronic_invoice': total_impuestos[0].text})
                i.update(to_update)

    regimen_simplificado = fields.Boolean('Factura Regimen simplificado?')

    number_electronic = fields.Char(string="Número electrónico", copy=False, index=True)
    date_issuance = fields.Datetime(string="Fecha de emisión", copy=False)

    state_invoice_partner = fields.Selection([('05', 'Aceptado'), ('06', 'Aceptacion parcial'), ('07', 'Rechazado')],
                                             'Respuesta del Cliente')

    reference_code_id = fields.Many2one("reference.code", string="Código de referencia")
    payment_methods_id = fields.Many2one("payment.methods", string="Métodos de Pago")
    invoice_id = fields.Many2one("account.invoice", string="Documento de referencia", copy=False)
    amount_tax_electronic_invoice = fields.Monetary('Total de impuestos FE', readonly=True, compute=_compute_amounts_fe, store=True)
    amount_total_electronic_invoice = fields.Monetary('Total FE', readonly=True, compute=_compute_amounts_fe, store=True)

    xml_respuesta_tributacion = fields.Binary("Respuesta Tributación XML", copy=False, attachment=True)
    fname_xml_respuesta_tributacion = fields.Char("Nombre de archivo XML Respuesta Tributación",
                                                  copy=False)
    xml_comprobante = fields.Binary("Comprobante XML",  copy=False, attachment=True)
    fname_xml_comprobante = fields.Char("Nombre de archivo Comprobante XML",  copy=False, attachment=True)

    xml_supplier_approval = fields.Binary("XML Proveedor",  copy=False, attachment=True)
    fname_xml_supplier_approval = fields.Char("Nombre de archivo Comprobante XML proveedor", copy=False, attachment=True)

    correo_envio_fe = fields.Char('Correo para envio de FE', help="Puede enviar diferentes correos divididos por una ,")

    _sql_constraints = [
        ('number_electronic_uniq', 'unique (number_electronic)', "La clave de comprobante debe ser única"),
    ]

    def sendError(self, nodo):
        return {'value': {'xml_supplier_approval': False},
                'warning': {'title': 'Atención',
                            'message': 'El archivo xml no contiene el nodo ' + nodo +
                                       '.\nPor favor cargue un archivo con el formato correcto.'}}
    @api.multi
    def asignar_clave(self):
        inv = self
        if inv.xml_supplier_approval:
            parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
            root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', base64.b64decode(inv.xml_supplier_approval), count=1), parser)
            _logger.info("ID--> %s" %(inv.id))
            inv.number_electronic = root.findall('Clave')[0].text

    @api.multi
    def get_qr_url(self):
        url = self.env['ir.config_parameter'].get_param('web.base.url')
        clave = self.clave_envio_hacienda or ''
        return url + "/visor/"+ self.company_id.partner_id.ref + "/" + clave + ".xml"

    def amount_to_text(self, amount, currency=False):
        currency_name = "COLONES"
        if currency and currency.id == 3:
            currency_name = "DOLARES"
        return amt_text.number_to_text_es(amount, currency_name)

    @api.onchange('xml_supplier_approval')
    def _onchange_xml_supplier_approval(self):
        if self.xml_supplier_approval:
            try:
                parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
                root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', base64.b64decode(self.xml_supplier_approval),
                                        count=1), parser)  # quita el namespace de los elementos
            except Exception as e:
                raise UserError("Por favor cargue un archivo en formato XML.\n%s" % (e.message,))

            if not root.findall('Clave'):
                return self.sendError('Clave')
            if not root.findall('FechaEmision'):
                return self.sendError('FechaEmision')
            if not root.findall('Emisor'):
                return self.sendError('Emisor')
            if not root.findall('Emisor')[0].findall('Identificacion'):
                return self.sendError('Identificacion')
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Tipo'):
                return self.sendError('Tipo')
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Numero'):
                return self.sendError('Numero')
            #if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalImpuesto')):
            #    return self.sendError('TotalImpuesto')
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalComprobante')):
                return self.sendError('TotalComprobante')
            return self.load_supplier_xml(root)

    def search_data(self, table, data, field='name', company=False):
        """
        :param table: nombre de la tabla en la que se va a buscar
        :param data: valor que se va a busar
        :param field: campo que se quiere buscar, por defecto va ser 'name'
        :param company: condicion para buscar por compañia y además será el valor de la compañia actual
        :return: id del registro encontrado
        """
        query = """select id from %s where %s ilike '%%%s%%' """ % (table, field, data)
        if company:
            query += " and (company_id=%s or company_id is null)" % (company)
        query += " limit 1;"
        self._cr.execute(query)
        val = self._cr.dictfetchone()
        if val:
            return val['id']
        return False

    @api.model
    def _default_account(self):
        if self._context.get('journal_id'):
            journal = self.env['account.journal'].browse(self._context.get('journal_id'))
            if self._context.get('type') in ('out_invoice', 'in_refund'):
                return journal.default_credit_account_id.id
            return journal.default_debit_account_id.id


    def load_supplier_xml(self, root):
        """
        :param root: root XML document
        :return: completa la CxP con los datos enviados en el XML del proveedor
        """
        partner = self.env['res.partner'].search(
            [('ref', '=', root.findall('Emisor')[0].find('Identificacion')[1].text), ('supplier', '=', True)], limit=1 )
        if partner:
            self.partner_id = partner.id
        else:
            alerta = {
                'title': 'Atención',
                'message': 'El proveedor con identificación ' + root.findall('Emisor')[0].find('Identificacion')[
                1].text + ' no existe. Por favor creelo primero en el sistema.'
            }
            return {'value': {'xml_supplier_approval': False}, 'warning': alerta}
        fecha = parse(root.findall('FechaEmision')[0].text)
        resumenFactura = root.findall('ResumenFactura')[0]
        fecha = datetime.strftime(fecha, DEFAULT_SERVER_DATETIME_FORMAT)
        lineas_factura = []
        company_id = self.env.user.company_id.id

        moneda = 'CRC'

        moneda_resumen = resumenFactura.find('CodigoTipoMoneda')
        if moneda_resumen is not None and moneda_resumen != False:
            _logger.info("1 %s"%(moneda_resumen,))
            moneda_resumen = moneda_resumen.find('CodigoMoneda')
            moneda = moneda_resumen.text
        else:
            _logger.info("2 %s"%(moneda_resumen,))
            moneda_resumen = resumenFactura.find('CodigoMoneda')
            if moneda_resumen is not None and moneda_resumen != False:
                moneda = moneda_resumen.text


        values = {
            'number_electronic': root.findall('Clave')[0].text,
            'date_issuance': fecha,
            'date_invoice': fecha,
            'date': fecha,
            'amount_total_electronic_invoice': float(resumenFactura.findall('TotalComprobante')[0].text),
            'currency_id': self.search_data('res_currency', moneda),
            'company_id': company_id
        }

        if not self.invoice_line_ids:
            default_account = self.with_context({'journal_id': self.journal_id.id, 'type': self.type})._default_account()
            for l in root.findall('DetalleServicio')[0].findall('LineaDetalle'):
                linea = {
                    'account_id': default_account,
                    'name': l.find('Detalle').text,
                    'quantity': float(l.find('Cantidad').text),
                    'uom_id': self.search_data('product_uom', l.find('UnidadMedida').text, 'code'),
                    'price_unit': float(l.find('PrecioUnitario').text)
                }
                if l.find('Codigo') and l.find('Codigo').find('Codigo'):
                    linea['name'] = '['+l.find('Codigo').find('Codigo').text+'] ' + linea['name']

                impuesto = l.find('Impuesto')
                if impuesto and impuesto is not None:
                    new_impuesto = self.env['account.tax'].search([('name', '=', str( int( float(impuesto.find('Tarifa').text) ) ) ), ('type_tax_use', '=', 'purchase')], limit=1)
                    if new_impuesto:
                        linea.update({'invoice_line_tax_ids': [new_impuesto.id]})
                    else:
                        tarifa = impuesto.find('Tarifa')
                        if tarifa is not None:
                            if re.match("^\d+?\.\d+?$", tarifa.text) is not None:
                                new_impuesto2 = self.env['account.tax'].search(
                                    [('amount', '=', float(tarifa.text)), ('type_tax_use', '=', 'purchase')], limit=1)
                                if new_impuesto2:
                                    linea.update({'invoice_line_tax_ids': [new_impuesto2.id]})

                else:
                    codigo_impuesto = self.search_data('account_tax_cr_code', '00', 'code')
                    if codigo_impuesto:
                        impuesto = self.env['account.tax'].search([('tax_code', '=', codigo_impuesto), ('type_tax_use', '=', 'purchase')], limit=1)
                        if impuesto:
                            linea.update({'invoice_line_tax_ids': [impuesto.id]})

                descuento = l.find('MontoDescuento')
                if descuento is not None:
                    desc = float(descuento.text)
                    if desc > 0.00:
                        monto_total = linea['quantity'] * linea['price_unit']
                        linea.update({'discount': round((desc / monto_total) * 100, 2)})

                lineas_factura.append([0, 0, linea])
            values.update({'invoice_line_ids': lineas_factura})

        if resumenFactura.findall('TotalImpuesto'):
            values.update({'amount_tax_electronic_invoice': float(resumenFactura.findall('TotalImpuesto')[0].text)})
        self.update(values)


    def action_invoice_open_aux(self):
        inv = self
        if inv.payment_term_id:
            if not inv.payment_term_id.sale_conditions_id:
                raise UserError('Debe configurar las condiciones de pago para %s' % (inv.payment_term_id.name,))

        currency_rate = 1 / inv.currency_id.rate

        resumen = {
            'moneda': inv.currency_id.name,
            'tipo_cambio': round(currency_rate, 5)
        }
        resumen.update(dict.fromkeys(['totalservicioexento', 'totalexonerado', 'totalventa', 'totalimpuestos',
                                      'totalservicioexonerado', 'totalcomprobante', 'totalmercaderiagravado',
                                      'totalexento', 'totalmercaderiaexonerado', 'totalmercaderiaexento',
                                      'totalgravado', 'totaldescuentos', 'totalserviciogravado',
                                      'totalventaneta'], 0.0))
        posicion_fiscal = False
        if inv.fiscal_position_id:
            posicion_fiscal = inv.fiscal_position_id.tax_ids
            if not posicion_fiscal:
                raise UserError('No se ha encontrado impuestos en la exoneración')
            posicion_fiscal = posicion_fiscal[0].porc_auth

        for inv_line in inv.invoice_line_ids:
            monto_impuesto = 0.0

            total_venta = round(inv_line.price_unit * inv_line.quantity, 2) #venta total
            descuento   = round(total_venta * ( (inv_line.discount or 0.0) / 100.0 ), 2) #descuento
            subtotal    = round(total_venta - descuento, 2) #subtotal

            impuestos = inv_line.invoice_line_tax_ids
            sum_venta = True
            sum_venta_total = True
            if impuestos: #impuestos de la linea
                for i in impuestos:
                    exonerado = 0.0

                    restar_imp = 0
                    if i.price_include:
                        restar_imp = i.compute_all(inv_line.price_unit, inv_line.invoice_id.currency_id, inv_line.quantity, False,
                                                   inv_line.invoice_id.partner_id)['taxes'][0].get('amount', 0)
                    total_venta -= restar_imp
                    # debe volver a recalcula los valores por imp incluido
                    descuento = round(total_venta * ((inv_line.discount or 0.0) / 100.0), 2)
                    subtotal = round(total_venta - descuento, 2)

                    if posicion_fiscal:
                        old_tax = inv_line.product_id.taxes_id  # impuestos ficha del producto
                        if old_tax: #sacar impuesto viejo para exoneracion
                            old_tax = old_tax[0]
                            imp_viejo = inv_line.price_subtotal * (old_tax.amount / 100)
                            impuesto_neto = imp_viejo #calcula linea para sacar diferencia

                            line_tax = inv.fiscal_position_id.tax_ids.filtered(lambda t: t.tax_src_id.id == old_tax.id)

                            impuesto_neto -= (impuesto_neto / 100.00) * line_tax.porc_auth

                            monto_impuesto += impuesto_neto


                    if inv_line.uom_id.code in ('Al', 'Alc', 'Cm', 'I', 'Os', 'Sp', 'Spe', 'St', 'd', 'h', 's'):
                        if posicion_fiscal:
                            exonerado = round( (total_venta * (posicion_fiscal / 100.0)), 2 )
                            resumen['totalservicioexonerado'] += exonerado
                            resumen['totalserviciogravado'] += total_venta - exonerado
                        else:
                            resumen['totalserviciogravado'] += total_venta
                    else:
                        if posicion_fiscal:
                            exonerado = (total_venta * (posicion_fiscal / 100.0))
                            resumen['totalmercaderiaexonerado'] += exonerado
                            resumen['totalmercaderiagravado'] += total_venta - exonerado
                        else:
                            if sum_venta:
                                resumen['totalmercaderiagravado'] += total_venta
                                sum_venta = False

                    if sum_venta_total:
                        resumen['totalgravado'] += total_venta - exonerado
                        sum_venta_total = False
                    resumen['totalexonerado'] += exonerado
            else:
                if inv_line.uom_id.code == 'Sp':
                    resumen['totalservicioexento'] += subtotal
                else:
                    resumen['totalmercaderiaexento'] += total_venta
                resumen['totalexento'] += total_venta

            resumen['totaldescuentos'] += round(descuento, 2)
            resumen['totalventa'] += round(total_venta, 2)
            resumen['totalventaneta'] += round(total_venta - descuento, 2)

            #resumen['totalimpuestos'] += round(monto_impuesto, 2)
            resumen['totalcomprobante'] += round((total_venta - descuento), 2) # + monto_impuesto

        return {
            'resumen': resumen
        }

    @api.multi
    def regenerar_xml(self):
        result = self.action_invoice_open_aux()
        _logger.info("REGENERANDO XML DE FACTURA %s compannia: %s" % (self.number, self.company_id.name))
        if self.type in ('in_invoice', 'in_refund'):  # validacion no aplica para CxP o ND de proveedor
            return result


        compania = self.company_id
        cliente = self.partner_id


        if not cliente.ref:
            raise UserError(_("Hace falta completar la cedula del cliente/proveedor. "+ cliente.name))
        if not compania.partner_id.ref:
            raise UserError(_("Hace falta completar la cedula  de la compañia."))

        if not compania.usuario_hacienda or not compania.clave_hacienda:
            raise UserError(_("Hace falta completar el usuario o la contraseña de hacienda en su compañia."))

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        fecha = datetime.now() - timedelta(hours=6)  # Hora en CR

        #if not compania.get_token():
        #    raise UserError(_("Hubo un errror al obtener el token de hacienda, contacte con su administrador."))

        inv_type = self.type
        tipo_doc = {
            'in_invoice': 'facturaCompra',  # Vendor Bill
            'in_refund': 'notaDebito',  # Vendor Refund
            'out_invoice': 'facturaVenta',  # Customer Invoice
            'out_refund': 'notaCredito',  # Customer Refund
        }[inv_type]

        if inv_type == "out_invoice" and self.journal_id.exportacion:
            tipo_doc = 'facturaVentaExportacion'
        #elif inv_type == "out_invoice" and self.partner_id.cliente_generico:
        #        tipo_doc = 'tiquete'

        if self.invoice_id and self.invoice_id.type == 'out_refund':
            tipo_doc = "notaDebito"

        xml_doc = DocumentoXml(self, tipo_doc, fecha, result['resumen'])
        _logger.info('generando nuevo xml')
        xml_firmado = xml_doc.generate_xml()
        self.xml_file_hacienda = xml_firmado.replace("&", "&amp;")
        archivo_firmado = self.firmar()
        _logger.info('actualizando nuevo xml')
        clave = xml_doc.get_Clave()
        self.write({
            'status_hacienda': 'generado',
            'xml_file_hacienda_firmado': archivo_firmado,
            'xml_comprobante': base64.b64encode(archivo_firmado),
            'fname_xml_comprobante': clave + ".xml",
            'clave_envio_hacienda': clave,
            'fecha_envio_hacienda': (fecha + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        })
        return self.enviar_factura_hacienda(archivo_firmado, xml_doc.get_Clave(), fecha)

    def forzar_enviar_factura_hacienda(self, archivo_firmado, clave, fecha, reintentar=False):
        params = self.consultar_parametros()

        recepcion = "recepcion"
        if params['facturacion_test']:
            recepcion = "recepcion-sandbox"
            
        emisor = self.company_id.partner_id
        receptor = self.partner_id
        if self.type == "in_invoice":
            # invierte los datos en caso que se vaya a generar un mensaje
            emisor = self.partner_id
            receptor = self.company_id.partner_id

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML
        values_to_send = {
            "fecha": fecha.strftime('%Y-%m-%dT%H:%M:%S'),  # "2018-01-17T00:00:00-0600"
            "clave": clave,
            "emisor": {
                "tipoIdentificacion": emisor.identification_id.code,
                "numeroIdentificacion": str(emisor.ref or "")
            },
            "receptor": {
                "tipoIdentificacion": receptor.identification_id.code,
                "numeroIdentificacion": str(receptor.ref or "")
            },
            "comprobanteXml": base64.b64encode(archivo_firmado)
        }

        token = self.company_id.token_hacienda

        headers = {'Content-type': 'application/json;charset=UTF-8',
                   'Authorization': token}

        json2send = simplejson.dumps(values_to_send)

        values2write = {
            'status_hacienda': 'generado',
            'xml_file_hacienda_firmado': archivo_firmado,
            'xml_comprobante': base64.b64encode(archivo_firmado),
            'fname_xml_comprobante': clave + ".xml",
            'clave_envio_hacienda': clave,
            'fecha_envio_hacienda': (fecha + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        }

        r = requests.post('https://api.comprobanteselectronicos.go.cr/' + recepcion + '/v1/recepcion', data=json2send,
                          headers=headers)  # envia archivo a hacienda

        if int(r.status_code) >= 200 and int(r.status_code) <= 205:
            _logger.info("Factura %s enviada de manera exitosa" % (clave,))
            values2write.update({'status_hacienda': 'procesando'})

        elif int(r.status_code) >= 401 and int(r.status_code) <= 403:
            if not reintentar:
                self.company_id.get_token()
                return self.forzar_enviar_factura_hacienda(archivo_firmado, clave, fecha, True)
            raise UserError('Credenciales invalidos, contacte con el administrador de su sistema')
        self.write(values2write)
        return True

    @api.multi
    def action_invoice_open_bryan(self):
        result = self.action_invoice_open_aux()
        if self.type in ('in_invoice', 'in_refund'):  # validacion no aplica para CxP o ND de proveedor
            if self.xml_supplier_approval:

                new_context = self.env.context.copy()
                if 'bin_size' in new_context:
                    del new_context['bin_size']
                archivo = base64.b64decode(self.with_context(new_context).xml_supplier_approval)
                root = False
                try:
                    parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
                    root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', archivo.decode('utf-8'),
                                                count=1), parser)  # quita el namespace de los elementos
                except Exception as e:
                    raise UserError("Por favor cargue un archivo en formato XML.\n%s" % (e.message,))
                if False: #root is not None:
                    if not self.validar_monto(root):
                            raise UserError(
                                'Error!.\nEl monto total de la factura no coincide con el monto total del archivo XML')
                return result


        compania = self.company_id
        cliente = self.partner_id


        if not cliente.ref:
            raise UserError(_("Hace falta completar la cedula del cliente/proveedor. "+ cliente.name))
        if not compania.partner_id.ref:
            raise UserError(_("Hace falta completar la cedula  de la compañia."))

        if not compania.usuario_hacienda or not compania.clave_hacienda:
            raise UserError(_("Hace falta completar el usuario o la contraseña de hacienda en su compañia."))

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        fecha = datetime.now() - timedelta(hours=6)  # Hora en CR


        inv_type = self.type
        tipo_doc = {
            'in_invoice': 'facturaCompra',  # Vendor Bill
            'in_refund': 'notaDebito',  # Vendor Refund
            'out_invoice': 'facturaVenta',  # Customer Invoice
            'out_refund': 'notaCredito',  # Customer Refund
        }[inv_type]

        if inv_type == "out_invoice" and self.journal_id.exportacion:
            tipo_doc = 'facturaVentaExportacion'


        if self.invoice_id and self.invoice_id.type == 'out_refund':
            tipo_doc = "notaDebito"
        xml_doc = DocumentoXml(self, tipo_doc, fecha, result['resumen'])
        xml_firmado = xml_doc.generate_xml()
        self.xml_file_hacienda = xml_firmado.replace("&", "&amp;")
        archivo_firmado = self.firmar()
        return self.enviar_factura_hacienda(archivo_firmado, xml_doc.get_Clave(), fecha)





    def validar_monto(self, root):
        total = round(float(root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text), 2)
        amount_total = round(self.amount_total, 2)
        _logger.info(total)
        _logger.info(amount_total)
        if str(total) != str(amount_total):
            if (total >= amount_total - 1) and (total <= amount_total + 1):
                return True
            else:
                return False
        return True

    def validate_cabys(self):
        for line in self.invoice_line_ids:
            if (line.product_id and not line.product_id.x_codigo_cabys):
                raise UserError('Debe asignar un código cabys a la linea de producto %s' % (line.product_id.name,))
            elif not line.product_id:
                raise UserError('Ahora debe asignar un producto y asignar un código cabys a la linea %s' % (line.name,))

    @api.multi
    def action_invoice_open(self):
        super(InvoiceElectronic, self).action_invoice_open()
        result = self.action_invoice_open_aux()
        if self.type in ('in_invoice', 'in_refund'):  # validacion no aplica para CxP o ND de proveedor
            if self.xml_supplier_approval:

                new_context = self.env.context.copy()
                if 'bin_size' in new_context:
                    del new_context['bin_size']
                archivo = base64.b64decode(self.with_context(new_context).xml_supplier_approval)
                root = False
                try:
                    parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
                    root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', archivo,
                                                count=1), parser)  # quita el namespace de los elementos
                except Exception as e:
                    raise UserError("Por favor cargue un archivo en formato XML.\n%s" % (e.message,))
                if False:#root is not None:
                    if not self.validar_monto(root):
                            raise UserError(
                                'Error!.\nEl monto total de la factura no coincide con el monto total del archivo XML')
                self.send_xml()
            return result
        self.validate_cabys()
        compania = self.company_id
        cliente = self.partner_id
        if not cliente.ref:
            raise UserError(_("Hace falta completar la cedula del cliente. "+ cliente.name))
        if not compania.partner_id.ref:
            raise UserError(_("Hace falta completar la cedula  de la compañia."))

        if not compania.usuario_hacienda or not compania.clave_hacienda:
            raise UserError(_("Hace falta completar el usuario o la contraseña de hacienda en su compañia."))

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        fecha = datetime.now() - timedelta(hours=6)  # Hora en CR
        if self.date_invoice:
            nueva_fecha = parse(self.date_invoice)
            fecha = fecha.replace(day=nueva_fecha.day, month=nueva_fecha.month, year=nueva_fecha.year)

        #if not compania.get_token():
        #    raise UserError(_("Hubo un errror al obtener el token de hacienda, contacte con su administrador."))

        inv_type = self.type
        tipo_doc = {
            'in_invoice': 'facturaCompra',  # Vendor Bill
            'in_refund': 'notaDebito',  # Vendor Refund
            'out_invoice': 'facturaVenta',  # Customer Invoice
            'out_refund': 'notaCredito',  # Customer Refund
        }[inv_type]

        if inv_type == "out_invoice" and self.journal_id.exportacion:
            tipo_doc = 'facturaVentaExportacion'
        elif inv_type == "out_invoice" and (cliente.cliente_generico or cliente.identification_id.code == "05"):
            tipo_doc = 'tiquete'

        if self.invoice_id and self.invoice_id.type == 'out_refund':
            tipo_doc = "notaDebito"

        #raise UserError("Alerta!\n Tipo de documento igual a: "+ tipo_doc)
        if self.type in ('in_invoice', 'in_refund'):
            if not self.xml_supplier_approval and not self.regimen_simplificado:
                return True

        xml_doc = DocumentoXml(self, tipo_doc, fecha, result['resumen'])
        xml_firmado = xml_doc.generate_xml()
        self.xml_file_hacienda = xml_firmado.replace("&", "&amp;")
        archivo_firmado = self.firmar()
        return self.enviar_factura_hacienda(archivo_firmado, xml_doc.get_Clave(), fecha)

    @api.multi
    def send_xml(self):
        """
        :return: retorna a hacienda el mensaje de recibido
        """
        resumen = {}
        inv = self
        if inv.xml_supplier_approval:
            parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
            root = ET.fromstring(re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', base64.b64decode(inv.xml_supplier_approval), count=1), parser)
            if not inv.state_invoice_partner:
                raise UserError('Aviso!.\nDebe primero seleccionar el tipo de respuesta para el archivo cargado.')
            if True: #self.validar_monto(root):
                    status = inv.state_invoice_partner
                    detalle_mensaje = {'05': ('1', 'Aceptado'), '06': ('2', 'Aceptado parcial'), '07': ('3', 'Rechazado')}[status]
                    journal = inv.journal_id
                    if not journal.sucursal or not journal.terminal:
                        raise UserError("Debe definir una sucursal y una terminal para el diario")
                    total_impuestos = root.findall('ResumenFactura')[0].find('TotalImpuesto')
                    if total_impuestos and total_impuestos is not None:
                        total_impuestos = total_impuestos.text
                    else:
                        total_impuestos = 0
                    if not inv.number:
                        raise UserError("Debe primero validar el archivo antes de enviarlo a Hacienda")
                    resumen = {
                            'tipo': status,
                            'sucursal': journal.sucursal,  # sucursal,#TODO
                            'terminal': journal.terminal,  # terminal,
                            'numero_documento': root.findall('Clave')[0].text,
                            'numero_cedula_emisor': root.findall('Emisor')[0].find('Identificacion')[1].text,
                            'fecha_emision_doc': root.findall('FechaEmision')[0].text,
                            'mensaje': detalle_mensaje[0],
                            'detalle_mensaje': detalle_mensaje[1],
                            'monto_total_impuesto': float(total_impuestos),
                            'total_factura': root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text,
                            'numero_cedula_receptor': inv.company_id.ref or inv.company_id.vat,
                            'num_consecutivo_receptor': inv.number[:20],
                            'emisor': {
                                'identificacion': {
                                    'tipo': root.findall('Emisor')[0].findall('Identificacion')[0].findall('Tipo')[
                                        0].text,
                                    'numero':
                                        root.findall('Emisor')[0].findall('Identificacion')[0].findall('Numero')[
                                            0].text,
                                },
                            },
                    }

            else:
                raise UserError(
                    'Error!.\nEl monto total de la factura no coincide con el monto total del archivo XML')

        fecha = datetime.now() - timedelta(hours=6)
        xml_doc = DocumentoXml(self, "mensaje", fecha, resumen)

        xml_firmado = xml_doc.generar_respuesta_xml()
        self.xml_file_hacienda = xml_firmado.replace("&", "&amp;")
        archivo_firmado = self.firmar()
        return self.enviar_factura_hacienda(archivo_firmado, xml_doc.get_Clave(), fecha)

    @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None, invoice_id=None,
               reference_code_id=None, payment_term_id=False):

        new_invoices = self.browse()
        for invoice in self:
            # create the new invoice
            values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                          description=description, journal_id=journal_id)
            values.update({'invoice_id': invoice_id,
                   'reference_code_id': reference_code_id,
                   'payment_term_id': payment_term_id,
                    'tipo_documento_pf': invoice.tipo_documento_pf,
                    'numero_documento_pf': invoice.numero_documento_pf,
                    'nombre_institucion_pf': invoice.nombre_institucion_pf,
                    'fecha_emision_pf': invoice.fecha_emision_pf,
                    'payment_methods_id': invoice.payment_methods_id.id,
                    'actividad_id': invoice.actividad_id.id,
            })
            refund_invoice = self.create(values)
            invoice_type = {
                'out_invoice': ('Nota de Credito'),
                'in_invoice': ('Nota de Debito'),
                'out_refund': ('Nota de Debito'),
            }
            #print invoice_type[invoice.type], invoice.id, invoice.number
            message = _("Esta %s fue creado desde: <a href=# data-oe-model=account.invoice data-oe-id=%d>%s</a>") % (invoice_type[invoice.type], invoice.id, invoice.number)
            refund_invoice.message_post(body=message)
            new_invoices += refund_invoice
        return new_invoices

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        super(InvoiceElectronic, self)._onchange_partner_id()
        self.payment_methods_id = self.partner_id.payment_methods_id
        self.correo_envio_fe = self.partner_id.correo_envio_fe

InvoiceElectronic()


class Invoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def _get_default_actividad(self):
        return False #355
        actividad = self.company_id.codigo_ids
        if actividad:
            return actividad[0].id
        else:
            return False

    xml_file_hacienda = fields.Text('Factura en formato XML', copy=False)
    xml_file_hacienda_firmado = fields.Text('XML Firmado', copy=False)
    fecha_envio_hacienda = fields.Datetime('Fecha envio XML', copy=False)
    validate_date = fields.Datetime('Fecha de validación', copy=False)
    clave_envio_hacienda = fields.Char('Clave envio XML', copy=False, index=True)
    fecha_recibo_hacienda = fields.Datetime('Fecha recibo respuesta hacienda', copy=False)
    status_hacienda = fields.Selection([("error", "Enviada con errores"),
                                        ("generado", "Generado"),
                                        ("aceptado", "Aceptada"),
                                        ("procesando", "Procesando"),
                                        ("recibido", "Recibido"),
                                        ("rechazado", "Rechazado")],
                                       string="Estatus hacienda", copy=False, default=False)
    mostrar_boton = fields.Boolean('Mostrar boton para envio de facturas', compute='_compute_mostrar_boton', store=True)

    celula_fisica = fields.Char('Cédula fisica')
    celula_juridica = fields.Char('Cédula Juridica')
    nombre_facturar = fields.Char('Nombre a facturar')

    # exoneracion
    tipo_documento_pf = fields.Selection([('01', 'Compras Autorizadas'),
                                          ('02', 'Ventas exentas a diplomáticos'),
                                          ('03', 'Autorizado por Ley Especial'),
                                          ('04', 'Exenciones Direccion General de Hacienda'),
                                          ('05', 'Transitorio V'),
                                          ('06', 'Transitorio IX'),
                                          ('07', 'Transitorio XVII'),
                                          ('99', 'Otros')], string='Tipo de Documento')
    numero_documento_pf = fields.Char('Numero de Documento')
    nombre_institucion_pf = fields.Char('Nombre de Institucion')
    fecha_emision_pf = fields.Date('Fecha de Emision')
    situacion = fields.Selection([('1', 'Normal'), ('2', 'Contingencia'), ('3', 'Sin Internet')],
                                 string='Situación del comprobante', default='1')
    pendiente_enviar = fields.Boolean('Pendiente enviar', default=False, copy=False)

    status_code = fields.Integer('Código Estado Hacienda', copy=False, default=0)
    actividad_id = fields.Many2one('codigo.actividad', 'Código de actividad', default=_get_default_actividad)
    correo_enviado = fields.Datetime('Fecha de envío de correo', copy=False, default=False)
    # se usara en caso que exista contingencia

    @api.depends('state', 'status_hacienda')
    def _compute_mostrar_boton(self):
        for inv in self:
            if inv.state == 'open' and inv.status_hacienda == 'procesando':
                inv.mostrar_boton = True
            else:
                inv.mostrar_boton = False

    @api.multi
    def consulta_estado_hacienda(self):
        """
        Consulta estado de factura, se llama desde boton en formulario pero se puede usar para multiples facturas
        :return: Nada, actualiza estado de hacienda de la factura
        """
        token = self[0].company_id.get_token()
        for inv in self:
            params = inv.consultar_parametros()
            recepcion = "recepcion"
            if params['facturacion_test']:
                recepcion = "recepcion-sandbox"
            #token = inv.company_id.token_hacienda
            inv.consultar_invoice(token, recepcion, True)
        return True

    def consultar_parametros(self):
        """
        Verifica que los paramentros de la facturacion estén correctos
        :return: parametros de facturacion
        """
        query = "select key, value from ir_config_parameter where key in ('facturacion_test', 'skip_facturacion', 'web.base.url');"
        cr = self.env.cr
        cr.execute(query)
        params = {}
        for r in cr.dictfetchall():
            params[r['key']] = True if r['value'] != '0' else False
            if r['key'] == 'web.base.url':
                params[r['key']] = r['value']

        if not ('facturacion_test' in params) or not ('skip_facturacion' in params):
            raise UserError('Se debe definir los parametros de facturación primero')
        return params


    @api.model
    def reenviar_facturas_hacienda(self):
        """
        Método utilizado por cron que se ejecuta cada 2 min.
        Toma las facturas pendientes de ENVIAR A HACIENDA de todas las companias, las agrupa y envia cada una
        :return: Nada, actualiza estado de hacienda de la factura
        """

        invoices = self.env['account.invoice'].search([('status_hacienda', '=', 'generado')], limit=10)
        companies = invoices.mapped('company_id')
        invoices_by_company = {}
        for i in invoices:
            if not invoices_by_company.get(i.company_id.id, False):
                invoices_by_company[i.company_id.id] = [i]
            else:
                invoices_by_company[i.company_id.id].append(i)
        for c in companies:
            company_id = c.id
            token = c.get_token()  # pide token por compania antes de comenzar con las consultas
            for inv in invoices_by_company[company_id]:
                inv.forzar_enviar_factura_hacienda(inv.xml_file_hacienda_firmado, inv.clave_envio_hacienda,
                                                   inv.fecha_envio_hacienda and datetime.strptime(
                                                       inv.fecha_envio_hacienda,
                                                       '%Y-%m-%d %H:%M:%S') or datetime.now())

    @api.model
    def consulta_estado_facturas_hacienda(self):
        """
        Método utilizado por cron que se ejecuta cada 10 min.
        Toma las facturas pendientes de revision de todas las companias, las agrupa y consulta cada una
        :return: Nada, actualiza estado de hacienda de la factura
        """

        params = self.consultar_parametros()
        recepcion = "recepcion"
        if params['facturacion_test']:
            recepcion = "recepcion-sandbox"
        invoices = self.env['account.invoice'].search(
            [('fname_xml_respuesta_tributacion', '=', False), ('clave_envio_hacienda', '!=', False), ('status_hacienda', '=', 'procesando') ], limit=30)
        companies = invoices.mapped('company_id')
        invoices_by_company = {}
        for i in invoices:
            if not invoices_by_company.get(i.company_id.id, False):
                invoices_by_company[i.company_id.id] = [i]
            else:
                invoices_by_company[i.company_id.id].append(i)
        companies = dict(map(lambda c: (c.id, c), companies))
        for c in companies:
            company_id = companies[c]
            token = company_id.get_token()  # pide token por compania antes de comenzar con las consultas
            for i in invoices_by_company[c]:
                i.consultar_invoice(token, recepcion, True)
        return True

    @api.multi
    def consultar_invoice(self, token, recepcion, reintentar=True):
        """
        Consulta estado de facturas en hacienda
        :param token:
        :param recepcion:
        :param reintentar:
        :return:
        """
        headers = {'Content-type': 'application/json;charset=UTF-8',
                   'Authorization': token}

        consulta = 'https://api.comprobanteselectronicos.go.cr/' + recepcion + '/v1/recepcion/' + self.clave_envio_hacienda
        try:
            respuesta = requests.get(consulta, headers=headers)
        except Exception as e:
            _logger.error("Error al obtener estado de factura %s\nRespuesta1: " %
                          (self.clave_envio_hacienda, e.message))


        try:
            if int(respuesta.status_code) in (401, 403) and reintentar:
                _logger.info("Reintentando")
                return self.consultar_invoice(self.company_id.get_token(), recepcion, False)
            elif int(respuesta.status_code) in (401, 403):
                _logger.error("Error al obtener estado de factura %s\nRespuesta2: %s" %
                              (self.clave_envio_hacienda, respuesta.text))
                raise UserError("Error al obtener estado de factura %s\nRespuesta3: %s" %
                              (self.clave_envio_hacienda, respuesta.text))
            elif str(respuesta.status_code).startswith('4'):
                _logger.error("Error al obtener estado de factura %s\nRespuesta2: %s" %
                              (self.clave_envio_hacienda, respuesta.text))
                return True

            valores = eval(respuesta.text)  # convierte respuesta en dict
            if type(valores) is dict:
                to_update = {
                            'status_hacienda': valores.get("ind-estado", "procesando")
                }
                if valores.get('respuesta-xml', False):
                   to_update.update({
                       'xml_respuesta_tributacion': valores.get('respuesta-xml', False),
                       'fname_xml_respuesta_tributacion': valores['clave'] + "-Respuesta.xml",
                       'fecha_recibo_hacienda': datetime.now()
                   })
                self.write(to_update)
                _logger.info("Resultado al obtener estado de factura %s\nRespuesta: %s" %
                              (self.clave_envio_hacienda, respuesta.text))

        except Exception as e:
            _logger.error("Error al obtener estado de factura %s\nRespuesta4: %s" %
                          (self.clave_envio_hacienda, respuesta.text or e.message))
        return True

    def _process_job(self, job_cr, job, cron_cr, fname):
        """ Run a given job taking care of the repetition.

        :param job_cr: cursor to use to execute the job, safe to commit/rollback
        :param job: job to be run (as a dictionary).
        :param cron_cr: cursor holding lock on the cron job row, to use to update the next exec date,
            must not be committed/rolled back!
        """
        try:
            with api.Environment.manage():
                new_env = api.Environment(job_cr, job['user_id'], {})

                # command_env.browse(job['invoice_id']).send_notifications(event=event)
                invoice_env = new_env['account.invoice']

                email_template = new_env.ref('account.email_template_edi_invoice', False)

                attachment = new_env['ir.attachment'].search(
                    [('res_model', '=', 'account.invoice'), ('res_id', '=', job['invoice_id']),
                     ('res_field', '=', 'xml_comprobante')], limit=1)

                respuesta = new_env['ir.attachment']._file_read(attachment.store_fname)
                #attachment.with_env(new_env).write({'name': fname, 'datas_fname': fname})

                #email_template.with_env(new_env).attachment_ids = [(6, 0, [attachment.id])]
                # {'default_attachment_ids': [attachment.id]}
                email_template.with_env(new_env).with_context({'others_attachments': [(fname, respuesta)]}).send_mail(job['invoice_id'],
                                                           raise_exception=False,
                                                           force_send=True)  # default_type='binary'
                #email_template.attachment_ids = [(3, attachment.id)]
                _logger.debug("Correo enviado de manera exitosa")

                invoice_env.invalidate_cache()
        finally:
            job_cr.commit()
            cron_cr.commit()

    def send_mail_background(self, fname):

        dbname = self._cr.dbname
        db = odoo.sql_db.db_connect(dbname)
        threading.current_thread().telegram_dbname = dbname
        try:
            with db.cursor() as cr:
                cr.execute("SELECT latest_version FROM ir_module_module WHERE name=%s", ['base'])
                (version,) = cr.fetchone()
                if version is None or version != BASE_VERSION:
                    raise BadDatabase()

            lock_cr = db.cursor()
            try:
                job_cr = db.cursor()
                try:
                    registry = odoo.registry(dbname)
                    self._process_job(job_cr, {'invoice_id': self.id, 'user_id': SUPERUSER_ID}, lock_cr, fname)
                except Exception as e:
                    _logger.exception('Unexpected exception while processing cron job %r', e)
                finally:
                    job_cr.close()

            except psycopg2.OperationalError, e:
                if e.pgcode == '55P03':
                    pass
                else:
                    raise
            finally:
                lock_cr.close()

        finally:
            if hasattr(threading.current_thread(), 'dbname'):
                del threading.current_thread().dbname

    @api.multi
    def reenviar_facturas_por_correo_action(self):
        """
        Método utilizado por cron que se ejecuta cada 2 min.
        Toma las facturas pendientes de ENVIAR POR CORREO de todas las companias, las agrupa y envia cada una
        :return: Nada, actualiza estado de hacienda de la factura
        """
        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        invoices = self
        companies = invoices.mapped('company_id')
        invoices_by_company = {}
        for i in invoices:
            if not invoices_by_company.get(i.company_id.id, False):
                invoices_by_company[i.company_id.id] = [i]
            else:
                invoices_by_company[i.company_id.id].append(i)
        email_template = self.env.ref('account.email_template_edi_invoice', False)
        for c in companies:
            company_id = c.id
            for inv in invoices_by_company[company_id]:
                    attachs = [
                        (inv.clave_envio_hacienda + ".xml", inv.xml_comprobante),
                        (inv.clave_envio_hacienda + "-RESPUESTA.xml", inv.xml_respuesta_tributacion)
                    ]
                    if inv.partner_id.email or inv.partner_id.correo_envio_fe:
                        email_template.with_context({'another_attachment': attachs}).send_mail(inv.id,
                                                                                               raise_exception=False,
                                                                                               force_send=True)  # default_type='binary'
                        _logger.info("Correo enviado exitosamente!!!")
                    inv.correo_enviado = datetime.now()


    @api.model
    def reenviar_facturas_por_correo(self):
        """
        Método utilizado por cron que se ejecuta cada 2 min.
        Toma las facturas pendientes de ENVIAR POR CORREO de todas las companias, las agrupa y envia cada una
        :return: Nada, actualiza estado de hacienda de la factura
        """
        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        invoices = self.env['account.invoice'].search([('status_hacienda', '=', 'aceptado'), ('correo_enviado', '=', False), ('type', 'in', ['out_invoice', 'out_refund']) ], limit=10)
        companies = invoices.mapped('company_id')
        invoices_by_company = {}
        for i in invoices:
            if not invoices_by_company.get(i.company_id.id, False):
                invoices_by_company[i.company_id.id] = [i]
            else:
                invoices_by_company[i.company_id.id].append(i)
        email_template = self.env.ref('account.email_template_edi_invoice', False)
        for c in companies:
            company_id = c.id
            for inv in invoices_by_company[company_id]:
                    attachs = [
                        (inv.clave_envio_hacienda + ".xml", inv.xml_comprobante),
                        (inv.clave_envio_hacienda + "-RESPUESTA.xml", inv.xml_respuesta_tributacion)
                    ]
                    if inv.partner_id.email or inv.partner_id.correo_envio_fe:
                        email_template.with_context({'another_attachment': attachs}).send_mail(inv.id,
                                                                                               raise_exception=False,
                                                                                               force_send=True)  # default_type='binary'
                        _logger.info("Correo enviado exitosamente!!!")
                    inv.correo_enviado = datetime.now()

    """
    def enviar_factura_hacienda_aux(self, archivo_firmado, clave, fecha, reintentar=False, token=False):
        params = self.consultar_parametros()

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML


        recepcion = "recepcion"
        if params['facturacion_test']:
            recepcion = "recepcion-sandbox"

        emisor = self.company_id.partner_id
        receptor = self.partner_id
        if self.type == "in_invoice":
            # invierte los datos en caso que se vaya a generar un mensaje
            emisor = self.partner_id
            receptor = self.company_id.partner_id

        values_to_send = {
            "fecha": fecha.strftime('%Y-%m-%dT%H:%M:%S'),  # "2018-01-17T00:00:00-0600"
            "clave": clave,
            "emisor": {
                "tipoIdentificacion": emisor.identification_id.code,
                "numeroIdentificacion": str(emisor.ref or "")
            },
            "comprobanteXml": base64.b64encode(archivo_firmado)
        }
        if receptor and not receptor.cliente_generico and receptor.identification_id:
            values_to_send.update({
                "receptor": {
                     "tipoIdentificacion": receptor.identification_id.code,
                     "numeroIdentificacion": str(receptor.ref or "")
                }
            })

        if 'localhost' not in params['web.base.url']:
            values_to_send.update({'callbackUrl': params['web.base.url'] + "/receptor/hacienda"})

        token = token or self.company_id.token_hacienda

        headers = {'Content-type': 'application/json;charset=UTF-8',
                   'Authorization': token}

        json2send = simplejson.dumps(values_to_send)

        values2write = {
            'status_hacienda': 'generado',
            'xml_file_hacienda_firmado': archivo_firmado,
            'xml_comprobante': base64.b64encode(archivo_firmado),
            'fname_xml_comprobante': clave + ".xml",
            'clave_envio_hacienda': clave,
            'fecha_envio_hacienda': (fecha + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        }
        values2write.update({'pendiente_enviar': params['skip_facturacion']})
        # en caso que la bandera esté en True se intentara enviar luego
        
        #if params['skip_facturacion']:
        #    # Crea el archivo pero no lo intenta enviar, esta opción es creada x si hacienda está caida
        #    self.write(values2write)

        #    return True

        r = requests.post('https://api.comprobanteselectronicos.go.cr/' + recepcion + '/v1/recepcion', data=json2send,
                          headers=headers, timeout=70)  # envia archivo a hacienda

        _logger.info("Enviado: %s" % (json2send))

        status_code = int(r.status_code)
        values2write.update({'status_code': status_code})
        _logger.info("Codigo respuesta: %s" % (status_code,))
        _logger.info("Respuesta: %s" % (r.text))

        if status_code >= 200 and status_code <= 205:
            _logger.info("Factura %s enviada de manera exitosa" % (clave,))
            values2write.update({'status_hacienda':  'procesando'})

            self.write(values2write)
        elif (status_code >= 401 and status_code <= 403):
            if not reintentar:
                new_token = self.company_id.get_token()
                _logger.info("Reintentando envio %s" % (clave,))
                return self.enviar_factura_hacienda_aux(archivo_firmado, clave, fecha, True, new_token)
            else:
                self.write(values2write)
                raise UserError('Credenciales invalidos, contacte con el administrador de su sistema')


        return True
    """

    @api.multi
    def enviar_correo_generico_otro_biopharma(self):

        if self.partner_id.opt_out:
            return True

        if not self.partner_id.email and not self.partner_id.correo_envio_fe and not self.correo_envio_fe:
            _logger.info("Sin correos "+ self.clave_envio_hacienda)
            return True

        _logger.info("\n\nComienza envio de factura por correo")

        correos = (self.partner_id.email or ' ' ) + ',' + (self.partner_id.correo_envio_fe or ' ') + ',' + (self.correo_envio_fe or ' ')
        correos = correos.replace(" ", ",")
        correos_separados = correos.split(",")

        def validaCorreo(correo):
            if correo != "":
                if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", correo.lower()):
                    return False
                else:
                    return correo
            else:
                return False
        #_logger.info(correos_separados)
        correos = ','.join(filter(lambda c: validaCorreo(c), correos_separados))
        _logger.info(correos)

        if correos == "":
            _logger.error("Correo para factura %s(%s) no puede ser enviado por falta de destinatarios" % (self.number, self.id))
            return True


        plantilla = self.env.ref('account.email_template_edi_invoice', False)
        values = plantilla.generate_email(self.id) #self.pool['mail.template'].generate_email(self.env.cr, self.env.uid, plantilla.id, self.id, context={}) #plantilla.generate_email_batch_inherit(self.id)

        SENDER = 'no-responder@crfacturaelectronica.com'
        SENDERNAME = 'Facturacion Electronica CR '
        SENDERNAME = (self.company_id.commercial_name or self.company_id.name) +', ' + (
                    self.type == 'out_invoice' and 'Factura' or 'NC') + ': ' + (self.number or '')

        USERNAME_SMTP = "AKIAI4LPJFP5CTPMKN6A"
        PASSWORD_SMTP = "Ar2+5a4DRrwgc4i6z893VumLs5dCW7yvaxGuCfJxQuAr"

        HOST = "email-smtp.us-west-2.amazonaws.com"
        PORT = 587

        BODY_HTML = values['body_html']
        msg = MIMEMultipart('alternative')
        msg['Subject'] = values['subject']
        msg['From'] = email.utils.formataddr((SENDERNAME, SENDER))

        msg['To'] = RECIPIENT = correos
        if validaCorreo(self.user_id.login):
            msg.add_header('reply-to', self.user_id.login)

        attachments = values.get('attachments', [])
        if len(attachments) > 0:
            attachments.append((self.fname_xml_comprobante, self.xml_comprobante))
            if self.xml_respuesta_tributacion:
                attachments.append((self.fname_xml_respuesta_tributacion, self.xml_respuesta_tributacion))
            for attach in attachments:
                #ext = file_name.split(".")[1]
                file_name = attach[0]
                ext = file_name.split(".")[1]

                #_logger.info(attach[0])

                att = MIMEBase("application", ext)
                att.add_header('Content-Transfer-Encoding', 'base64')
                if ext != "xml":
                    file_name = self.clave_envio_hacienda + ".pdf"

                att.add_header('Content-Disposition', 'attachment', filename=file_name)

                att.set_payload(attach[1])
                msg.attach(att)

        msg.attach(MIMEText(BODY_HTML, 'html'))

        try:
            server = smtplib.SMTP(HOST, PORT)
            server.ehlo()
            server.starttls()

            server.ehlo()
            server.login(USERNAME_SMTP, PASSWORD_SMTP)
            #_logger.info(RECIPIENT)
            #_logger.info(msg.as_string())
            _logger.info("VA A ENVIARSE")

            server.sendmail(SENDER, RECIPIENT.split(","), msg.as_string())
            server.close()

        except Exception as e:
            _logger.error("Error: %s"% (e,))
            return False
        _logger.info("Correo enviado correctamente en factura: %s a: %s\n\n" % (self.clave_envio_hacienda, correos))


        return True

    @api.multi
    def enviar_correo_generico_otro(self):

        if self.partner_id.opt_out:
            return True

        if not self.partner_id.email and not self.partner_id.correo_envio_fe and not self.correo_envio_fe:
            _logger.info("Sin correos "+ self.clave_envio_hacienda)
            return True

        _logger.info("Comienza envio de factura por correo")

        correos = (self.partner_id.email or ' ' ) + ',' + (self.partner_id.correo_envio_fe or ' ') + ',' + (self.correo_envio_fe or ' ')
        correos = correos.replace(" ", ",")
        correos_separados = correos.split(",")

        def validaCorreo(correo):
            _logger.info(correo)
            if correo != "":
                if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", correo.lower()):
                    return False
                else:
                    return correo
            else:
                return False
        _logger.info(correos_separados)
        correos = ','.join(filter(lambda c: validaCorreo(c), correos_separados))
        _logger.info("'%s'" %correos)

        if correos == "":
            _logger.error("Correo para factura %s(%s) no puede ser enviado por falta de destinatarios" % (self.number, self.id))
            return True


        plantilla = self.env.ref('account.email_template_edi_invoice', False)
        values = plantilla.generate_email(self.id) #self.pool['mail.template'].generate_email(self.env.cr, self.env.uid, plantilla.id, self.id, context={}) #plantilla.generate_email_batch_inherit(self.id)

        SENDER = 'fe-app@crfacturaelectronica.com'
        SENDERNAME = 'Facturacion Electronica CR'

        USERNAME_SMTP = "AKIAI4LPJFP5CTPMKN6A"
        PASSWORD_SMTP = "Ar2+5a4DRrwgc4i6z893VumLs5dCW7yvaxGuCfJxQuAr"

        HOST = "email-smtp.us-west-2.amazonaws.com"
        PORT = 587

        BODY_HTML = values['body_html']
        msg = MIMEMultipart('mixed')
        msg['Subject'] = values['subject']
        msg['From'] = email.utils.formataddr((SENDERNAME, SENDER))

        msg['To'] = RECIPIENT = correos
        if validaCorreo(self.user_id.login):
            msg.add_header('reply-to', self.user_id.login)

        attachments = values.get('attachments', [])
        if len(attachments) > 0:
            attachments.append((self.fname_xml_comprobante, self.xml_comprobante))
            if self.xml_respuesta_tributacion:
                attachments.append((self.fname_xml_respuesta_tributacion, self.xml_respuesta_tributacion))
            for attach in attachments:
                #ext = file_name.split(".")[1]
                file_name = attach[0]
                ext = file_name.split(".")[1]

                #_logger.info(attach[0])

                att = MIMEBase("application", ext)
                att.add_header('Content-Transfer-Encoding', 'base64')
                if ext != "xml":
                    file_name = self.number + ".pdf"

                att.add_header('Content-Disposition', 'attachment', filename=file_name)

                att.set_payload(attach[1])
                msg.attach(att)

        msg.attach(MIMEText(BODY_HTML, 'html'))

        try:
            server = smtplib.SMTP(HOST, PORT)
            server.ehlo()
            server.starttls()

            server.ehlo()
            server.login(USERNAME_SMTP, PASSWORD_SMTP)
            #_logger.info(RECIPIENT)
            #_logger.info(msg.as_string())
            _logger.info("\n\n\nVA A ENVIARSE\n\n")

            server.sendmail(SENDER, RECIPIENT.split(","), msg.as_string())
            server.close()

        except Exception as e:
            _logger.error("Error: %s"% (e,))
            return False
        _logger.info("Correo enviado correctamente en factura: %s a: %s" % (self.clave_envio_hacienda, correos))


        return True




    def enviar_factura_hacienda(self, archivo_firmado, clave, fecha, reintentar=False):
        params = self.consultar_parametros()

        recepcion = "recepcion"
        if params['facturacion_test']:
            recepcion = "recepcion-sandbox"

        emisor = self.company_id.partner_id
        receptor = self.partner_id
        if self.type == "in_invoice":
            # invierte los datos en caso que se vaya a generar un mensaje
            emisor = self.partner_id
            receptor = self.company_id.partner_id

        values_to_send = {
            "fecha": fecha.strftime('%Y-%m-%dT%H:%M:%S'),  # "2018-01-17T00:00:00-0600"
            "clave": clave,
            "emisor": {
                "tipoIdentificacion": emisor.identification_id.code,
                "numeroIdentificacion": str(emisor.ref or "")
            },
            "comprobanteXml": base64.b64encode(archivo_firmado)
        }
        if receptor and not receptor.cliente_generico and receptor.identification_id:
            values_to_send.update({
                "receptor": {
                     "tipoIdentificacion": receptor.identification_id.code,
                     "numeroIdentificacion": str(receptor.ref or "")
                }
            })

        if 'localhost' not in params['web.base.url']:
            values_to_send.update({'callbackUrl': params['web.base.url'] + "/receptor/hacienda"})

        token = self.company_id.token_hacienda

        headers = {'Content-type': 'application/json;charset=UTF-8',
                   'Authorization': token}

        json2send = simplejson.dumps(values_to_send)

        values2write = {
            'status_hacienda': 'generado',
            'xml_file_hacienda_firmado': archivo_firmado,
            'xml_comprobante': base64.b64encode(archivo_firmado),
            'fname_xml_comprobante': clave + ".xml",
            'clave_envio_hacienda': clave,
            'fecha_envio_hacienda': (fecha + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        }
        values2write.update({'pendiente_enviar': params['skip_facturacion']})
        # en caso que la bandera esté en True se intentara enviar luego
        
        if params['skip_facturacion']:
            # Crea el archivo pero no lo intenta enviar, esta opción es creada x si hacienda está caida
            self.write(values2write)
            if False: #not self.partner_id.opt_out and self.type in ('out_invoice', 'in_refund'):
                try:
                   self._cr.commit()
                   # envio de correo
                   threaded_calculation = threading.Thread(target=self.send_mail_background, args=(clave + ".xml",))
                   threaded_calculation.start()
                except:
                   pass

            return True

        r = requests.post('https://api.comprobanteselectronicos.go.cr/' + recepcion + '/v1/recepcion', data=json2send,
                          headers=headers, timeout=70)  # envia archivo a hacienda

        status_code = int(r.status_code)
        values2write.update({'status_code': status_code})
        if status_code >= 200 and status_code <= 205:
            _logger.info("Factura %s enviada de manera exitosa" % (clave,))
            values2write.update({'status_hacienda': 'procesando',})
            self.write(values2write)
        elif (status_code >= 401 and status_code <= 403):
            if not reintentar:
                self.company_id.get_token()
                _logger.info("Reintentando envio %s" % (clave,))
                return self.enviar_factura_hacienda(archivo_firmado, clave, fecha, True)
            else:
                self.write(values2write)
                raise UserError('Credenciales invalidos, contacte con el administrador de su sistema')

        if False: #not self.partner_id.opt_out and self.type in ('out_invoice', 'in_refund'):
            try:
                self._cr.commit()
                # envio de correo
                threaded_calculation = threading.Thread(target=self.send_mail_background, args=(clave + ".xml",))
                threaded_calculation.start()
            except:
                pass
        return True

    @contextlib.contextmanager
    def generarXMLTemp(self):
        """
        :return: archivo XMl Temporal
        """
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as t_xml:
            t_xml.write(self.xml_file_hacienda)
            t_xml.close()
            yield t_xml.name

    @contextlib.contextmanager
    def generarP12Temp(self):
        """
        :return: archivo P12 Temporal
        """
        with tempfile.NamedTemporaryFile(suffix='.p12', delete=False) as t_p12:
            t_p12.write(base64.decodestring(self.company_id.llave_hacienda))
            t_p12.close()
            yield t_p12.name

    def firmar(self):
        archivo_xml = False
        archivo_p12 = False

        with self.generarXMLTemp() as a_xml:
            archivo_xml = a_xml
        with self.generarP12Temp() as a_p12:
            archivo_p12 = a_p12
        try:
            JAR_PATH = 'firmador/firmador.py'  # 'firmador/firmar-xades.jar'
            current_dir = os.path.dirname(__file__)
            firma_path = os.path.join(current_dir, JAR_PATH)
            archivo_firmado = archivo_xml + "_firmado"
            # subprocess.call(['java', '-jar',  firma_path, archivo_p12, self.company_id.clave_llave, archivo_xml, archivo_firmado])
            #procesos = ['java', '-jar', firma_path, 'sign', archivo_p12, self.company_id.clave_llave, archivo_xml,
            #                 archivo_firmado]
            procesos = ['python3', firma_path, archivo_p12, self.company_id.clave_llave, archivo_xml]
            _logger.info( " ".join(procesos) )

            subprocess.call(procesos)
            firmado = open(archivo_firmado, "r").read()
            # print firmado
            return firmado  # open(archivo_firmado, "r").read()
        except Exception as e:
            raise UserError(
                _("Hubo un error al intentar firmar el archivo, contacte con su administrador\nError: (%s)." % (e,)))

    @api.multi
    def action_invoice_sent_inherit(self):
        result = super(Invoice, self).action_invoice_sent()
        _logger.info("Cargando archivos adjuntos")
        result['context']['another_attachment'] = [(self.fname_xml_comprobante, self.xml_comprobante)]
        if self.xml_respuesta_tributacion:
            result['context']['another_attachment'].append( tuple((self.fname_xml_respuesta_tributacion, self.xml_respuesta_tributacion)) )
        if self.correo_envio_fe:
            for correo in self.correo_envio_fe.replace("   ", " ").replace("  ", " ").replace(" ", ",").split(","):
                partner_id = self.env['res.partner'].with_context({}).find_or_create(correo)
                result['context']['others_emails'] = [partner_id]
        return result

    action_invoice_sent = action_invoice_sent_inherit

Invoice()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    price_with_discount = fields.Float('Precio con descuento', compute='_compute_price', store=True)
    tax_amount = fields.Float('Monto Impuesto', compute='_compute_price', store=True)

    # Inicio campos Mario
    discount_note = fields.Char(string="Nota de descuento", required=False, )
    # Fin campos Mario

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
                 'product_id', 'invoice_id.partner_id', 'invoice_id.currency_id',
                 'invoice_id.date_invoice')
    def _compute_price_inherit(self):
        super(AccountInvoiceLine, self)._compute_price()
        price_with_discount = self.price_unit - (self.price_unit * self.discount / 100.0)
        self.price_with_discount = price_with_discount
        tax_result = 0
        if self.invoice_line_tax_ids:
            tax_result = \
                self.invoice_line_tax_ids.compute_all(price_with_discount, self.currency_id, self.quantity, False,
                                                      self.partner_id)['taxes'][0].get('amount', 0)
        self.tax_amount = tax_result

    _compute_price = _compute_price_inherit


class AccountInvoiceRefund(models.TransientModel):
    _inherit = "account.invoice.refund"

    @api.model
    def _get_invoice_id(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        if active_id:
            return active_id
        return False

    @api.model
    def _default_reference_code_id(self):
        reference_code = self.env.ref('cr_electronic_invoice.ReferenceCode_1')
        if reference_code:
            return reference_code.id
        return False

    reference_code_id = fields.Many2one("reference.code", string="Código de referencia")#, default=_default_reference_code_id)
    invoice_id = fields.Many2one("account.invoice", string="Documento de referencia",
                                 default=_get_invoice_id, required=False, )

    filter_refund = fields.Selection([('refund', 'Crear una factura rectificativa borrador'), ('cancel', 'Cancelar: crea la factura rectificativa y concilia')],
        default='refund', string='Refund Method', required=True, help='Factura rectificativa basada en este tipo. No se puede modificar o cancelar si la factura ya está conciliada')

    nd = fields.Boolean('Nota de Débito')

    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms', related="invoice_id.payment_term_id")

    @api.onchange('invoice_id')
    def onchange_factura(self):
        reference_code_anulacion = self.env.ref('cr_electronic_invoice.ReferenceCode_1')
        reference_code_modificacion = self.env.ref('cr_electronic_invoice.ReferenceCode_3')
        toUpdate = {'nd': True if self.invoice_id.type == 'in_invoice' else False}
        self.update(toUpdate)
        return {'domain': {'reference_code_id': [('id', '=', (reference_code_anulacion.id, reference_code_modificacion.id))]},
                'values': toUpdate}

    @api.multi
    def compute_refund(self, mode='refund'):
        inv_obj = self.env['account.invoice']
        inv_tax_obj = self.env['account.invoice.tax']
        inv_line_obj = self.env['account.invoice.line']
        context = dict(self._context or {})
        xml_id = False

        for form in self:
            created_inv = []
            date = False
            description = False
            for inv in inv_obj.browse(context.get('active_ids')):
                if inv.state in ['draft', 'proforma2', 'cancel']:
                    raise UserError(_('Cannot refund draft/proforma/cancelled invoice.'))
                if inv.reconciled and mode in ('cancel', 'modify'):
                    raise UserError(_(
                        'Cannot refund invoice which is already reconciled, invoice should be unreconciled first. You can only refund this invoice.'))

                date = form.date or False
                description = form.description or inv.name
                refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id, form.invoice_id.id,
                                    form.reference_code_id.id, form.payment_term_id.id)

                created_inv.append(refund.id)
                if mode in ('cancel', 'modify'):
                    movelines = inv.move_id.line_ids
                    to_reconcile_ids = {}
                    to_reconcile_lines = self.env['account.move.line']
                    for line in movelines:
                        if line.account_id.id == inv.account_id.id:
                            to_reconcile_lines += line
                            to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
                        if line.reconciled:
                            line.remove_move_reconcile()
                    refund.action_invoice_open()
                    for tmpline in refund.move_id.line_ids:
                        if tmpline.account_id.id == inv.account_id.id:
                            to_reconcile_lines += tmpline
                    to_reconcile_lines.filtered(lambda l: l.reconciled == False).reconcile()
                    if mode == 'modify':
                        invoice = inv.read(inv_obj._get_refund_modify_read_fields())
                        invoice = invoice[0]
                        del invoice['id']
                        invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
                        invoice_lines = inv_obj.with_context(mode='modify')._refund_cleanup_lines(invoice_lines)
                        tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
                        tax_lines = inv_obj._refund_cleanup_lines(tax_lines)
                        invoice.update({
                            'type': inv.type,
                            'date_invoice': form.date_invoice,
                            'state': 'draft',
                            'number': False,
                            'invoice_line_ids': invoice_lines,
                            'tax_line_ids': tax_lines,
                            'date': date,
                            'origin': inv.origin,
                            'fiscal_position_id': inv.fiscal_position_id.id,
                            'invoice_id': inv.id,  # agregado
                            'reference_code_id': form.reference_code_id.id,
                            'payment_term_id': inv.payment_term_id.id,
                        })
                        for field in inv_obj._get_refund_common_fields():
                            if inv_obj._fields[field].type == 'many2one':
                                invoice[field] = invoice[field] and invoice[field][0]
                            else:
                                invoice[field] = invoice[field] or False
                        inv_refund = inv_obj.create(invoice)
                        if inv_refund.payment_term_id.id:
                            inv_refund._onchange_payment_term_date_invoice()
                        created_inv.append(inv_refund.id)
                xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1_refund_view1' or \
                         (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree_refund2'
                # Put the reason in the chatter
                subject = _("Invoice refund")
                body = description
                refund.message_post(body=body, subject=subject)
        if xml_id:
            result = self.env.ref('facturacion_hacienda.%s' % (xml_id)).read()[0]
            invoice_domain = safe_eval(result['domain'])
            invoice_domain.append(('id', 'in', created_inv))
            result['domain'] = invoice_domain
            return result
        return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
