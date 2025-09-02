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
import xml.etree.ElementTree as ET
from dateutil.parser import parse
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from documento_xml import DocumentoXml

_logger = logging.getLogger(__name__)
BASE_VERSION = odoo.modules.load_information_from_description_file('base')['version']


class InvoiceElectronic(models.Model):
    _inherit = 'account.invoice'

    number_electronic = fields.Char(string="Número electrónico", copy=False, index=True)
    date_issuance = fields.Datetime(string="Fecha de emisión", copy=False)

    state_invoice_partner = fields.Selection([('05', 'Aceptado'), ('06', 'Aceptacion parcial'), ('07', 'Rechazado')],
                                             'Respuesta del Cliente')

    reference_code_id = fields.Many2one("reference.code", string="Código de referencia")
    payment_methods_id = fields.Many2one("payment.methods", string="Métodos de Pago")
    invoice_id = fields.Many2one("account.invoice", string="Documento de referencia", copy=False)
    amount_tax_electronic_invoice = fields.Monetary('Total de impuestos FE', readonly=True, )
    amount_total_electronic_invoice = fields.Monetary('Total FE', readonly=True, )

    xml_respuesta_tributacion = fields.Binary("Respuesta Tributación XML", copy=False, attachment=True)
    fname_xml_respuesta_tributacion = fields.Char("Nombre de archivo XML Respuesta Tributación",
                                                  copy=False)
    xml_comprobante = fields.Binary("Comprobante XML",  copy=False, attachment=True)
    fname_xml_comprobante = fields.Char("Nombre de archivo Comprobante XML",  copy=False, attachment=True)

    xml_supplier_approval = fields.Binary("XML Proveedor",  copy=False, attachment=True)
    fname_xml_supplier_approval = fields.Char("Nombre de archivo Comprobante XML proveedor", copy=False, attachment=True)

    _sql_constraints = [
        ('number_electronic_uniq', 'unique (number_electronic)', "La clave de comprobante debe ser única"),
    ]

    def sendError(self, nodo):
        return {'value': {'xml_supplier_approval': False},
                'warning': {'title': 'Atención',
                            'message': 'El archivo xml no contiene el nodo ' + nodo +
                                       '.\nPor favor cargue un archivo con el formato correcto.'}}

    @api.onchange('xml_supplier_approval')
    def _onchange_xml_supplier_approval(self):
        if self.xml_supplier_approval:
            try:
                root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(self.xml_supplier_approval),
                                        count=1))  # quita el namespace de los elementos
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
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalImpuesto')):
                return self.sendError('TotalImpuesto')
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalComprobante')):
                return self.sendError('TotalComprobante')
            self.load_supplier_xml(root)

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

    def load_supplier_xml(self, root):
        """
        :param root: root XML document
        :return: completa la CxP con los datos enviados en el XML del proveedor
        """
        partner = self.env['res.partner'].search(
            [('ref', '=', root.findall('Emisor')[0].find('Identificacion')[1].text)])
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
        for l in root.findall('DetalleServicio')[0].findall('LineaDetalle'):
            linea = {
                'name': '['+l.find('Codigo').find('Codigo').text+'] ' + l.find('Detalle').text,
                'quantity': float(l.find('Cantidad').text),
                'uom_id': self.search_data('product_uom', l.find('UnidadMedida').text, 'code'),
                'price_unit': float(l.find('PrecioUnitario').text)
            }
            impuesto = l.find('Impuesto')
            if impuesto:
                codigo_impuesto = self.search_data('account_tax_cr_code', impuesto.find('Codigo').text, 'code')
                if codigo_impuesto:
                    impuesto = self.env['account.tax'].search([('tax_code', '=', codigo_impuesto), ('type_tax_use', '=', 'purchase')], limit=1)
                    if impuesto:
                        linea.update({'invoice_line_tax_ids': [impuesto.id]})
            else:
                codigo_impuesto = self.search_data('account_tax_cr_code', '00', 'code')
                if codigo_impuesto:
                    impuesto = self.env['account.tax'].search([('tax_code', '=', codigo_impuesto), ('type_tax_use', '=', 'purchase')], limit=1)
                    if impuesto:
                        linea.update({'invoice_line_tax_ids': [impuesto.id]})

            lineas_factura.append([0, 0, linea])
        self.update({
            'number_electronic': root.findall('Clave')[0].text,
            'date_issuance': fecha,
            'date_invoice': fecha,
            'date': fecha,
            'amount_tax_electronic_invoice': float(resumenFactura.findall('TotalImpuesto')[0].text),
            'amount_total_electronic_invoice': float(resumenFactura.findall('TotalComprobante')[0].text),
            'currency_id': self.search_data('res_currency', resumenFactura.findall('CodigoMoneda')[0].text),
            'invoice_line_ids': lineas_factura
        })


    def action_invoice_open_aux(self):
        inv = self
        if inv.payment_term_id:
            if not inv.payment_term_id.sale_conditions_id:
                raise UserError('Debe configurar las condiciones de pago para %s' % (inv.payment_term_id.name,))

        currency_rate = 1 / inv.currency_id.rate
        base_total = 0.0
        totalserviciogravado = 0.0
        totalservicioexento = 0.0
        totalmercaderiagravado = 0.0
        totalmercaderiaexento = 0.0
        for inv_line in inv.invoice_line_ids:
            impuestos_acumulados = 0.0
            base_total += inv_line.price_unit * inv_line.quantity
            for i in inv_line.invoice_line_tax_ids:
                code = i.tax_code.code
                if code != '00':
                    impuestos_acumulados += round(i.amount / 100 * inv_line.price_subtotal, 2)
            if inv_line.product_id:
                if inv_line.product_id.type == 'service':
                    if impuestos_acumulados:
                        totalserviciogravado += inv_line.quantity * inv_line.price_unit
                    else:
                        totalservicioexento += inv_line.quantity * inv_line.price_unit
                else:
                    if impuestos_acumulados:
                        totalmercaderiagravado += inv_line.quantity * inv_line.price_unit
                    else:
                        totalmercaderiaexento += inv_line.quantity * inv_line.price_unit
            else:  # se asume que si no tiene producto setrata como un type product
                if impuestos_acumulados:
                    totalmercaderiagravado += inv_line.quantity * inv_line.price_unit
                else:
                    totalmercaderiaexento += inv_line.quantity * inv_line.price_unit

        _logger.error('MAB - formando payload')
        return {
            'resumen': {
                'moneda': inv.currency_id.name,
                'tipo_cambio': round(currency_rate, 5),
                'totalserviciogravado': totalserviciogravado,
                'totalservicioexento': totalservicioexento,
                'totalmercaderiagravado': totalmercaderiagravado,
                'totalmercaderiaexento': totalmercaderiaexento,
                'totalgravado': totalserviciogravado + totalmercaderiagravado,
                'totalexento': totalservicioexento + totalmercaderiaexento,
                'totalventa': totalserviciogravado + totalmercaderiagravado + totalservicioexento + totalmercaderiaexento,
                'totaldescuentos': round(base_total, 2) - round(inv.amount_untaxed, 2),
                'totalventaneta': (totalserviciogravado + totalmercaderiagravado + totalservicioexento +
                                   totalmercaderiaexento) - (base_total - inv.amount_untaxed),
                'totalimpuestos': inv.amount_tax,
                'totalcomprobante': inv.amount_total,
            }
        }


    @api.multi
    def action_invoice_open(self):
        super(InvoiceElectronic, self).action_invoice_open()
        result = self.action_invoice_open_aux()
        if self.type in ('in_invoice', 'in_refund'):  # validacion no aplica para CxP o ND de proveedor
            return result

        compania = self.company_id
        cliente = self.partner_id
        if not cliente.ref:
            raise UserError(_("Hace falta completar la cedula del cliente."))
        if not compania.partner_id.ref:
            raise UserError(_("Hace falta completar la cedula  de la compañia."))

        if not compania.usuario_hacienda or not compania.clave_hacienda:
            raise UserError(_("Hace falta completar el usuario o la contraseña de hacienda en su compañia."))

        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')  # se carga para que no existan errores al generar el XML

        fecha = datetime.now() - timedelta(hours=6)  # Hora en CR

        if not compania.get_token():
            raise UserError(_("Hubo un errror al obtener el token de hacienda, contacte con su administrador."))

        tipo_doc = {
            'in_invoice': '00',  # Vendor Bill
            'out_invoice': 'factura',  # Customer Invoice
            'out_refund': 'notaCredito',  # Customer Refund
            'in_refund': 'notaDebito',  # Vendor Refund
        }[self.type]

        xml_doc = DocumentoXml(self, tipo_doc, fecha, result['resumen'])
        self.xml_file_hacienda = xml_doc.generate_xml()
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
            root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(inv.xml_supplier_approval), count=1))
            if not inv.state_invoice_partner:
                raise UserError('Aviso!.\nDebe primero seleccionar el tipo de respuesta para el archivo cargado.')
            if str(float(root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text)) == str(inv.amount_total):
                    status = inv.state_invoice_partner
                    journal = inv.journal_id
                    if not journal.sucursal or not journal.terminal:
                        raise UserError("Debe definir una sucursal y una terminal para el diario")

                    detalle_mensaje = {'05': ('1', 'Aceptado'), '06': ('2', 'Aceptado parcial'), '07': ('3', 'Rechazado')}[status]
                    resumen = {
                            'tipo': status,
                            'sucursal': journal.sucursal,  # sucursal,#TODO
                            'terminal': journal.terminal,  # terminal,
                            'numero_documento': root.findall('Clave')[0].text,
                            'numero_cedula_emisor': root.findall('Emisor')[0].find('Identificacion')[1].text,
                            'fecha_emision_doc': root.findall('FechaEmision')[0].text,
                            'mensaje': detalle_mensaje[0],
                            'detalle_mensaje': detalle_mensaje[1],
                            'monto_total_impuesto': root.findall('ResumenFactura')[0].findall('TotalImpuesto')[
                                0].text,
                            'total_factura': root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text,
                            'numero_cedula_receptor': inv.company_id.vat or inv.company_id.ref,
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
        self.xml_file_hacienda = xml_doc.generar_respuesta_xml()
        archivo_firmado = self.firmar()
        return self.enviar_factura_hacienda(archivo_firmado, xml_doc.get_Clave(), fecha)

    @api.multi
    @api.returns('self')
    def refund(self, date_invoice=None, date=None, description=None, journal_id=None, invoice_id=None,
               reference_code_id=None):

        new_invoices = self.browse()
        for invoice in self:
            # create the new invoice
            values = self._prepare_refund(invoice, date_invoice=date_invoice, date=date,
                                          description=description, journal_id=journal_id)
            values.update({'invoice_id': invoice_id,
                   'reference_code_id': reference_code_id,
                    'tipo_documento_pf': invoice.tipo_documento_pf,
                    'numero_documento_pf': invoice.numero_documento_pf,
                    'nombre_institucion_pf': invoice.nombre_institucion_pf ,
                    'fecha_emision_pf': invoice.fecha_emision_pf,
                    'payment_methods_id': invoice.payment_methods_id.id
            })
            refund_invoice = self.create(values)
            invoice_type = {
                'out_invoice': ('Nota de Credito'),
                'in_invoice': ('Nota de Debito')
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

InvoiceElectronic()


class Invoice(models.Model):
    _inherit = 'account.invoice'

    xml_file_hacienda = fields.Text('Factura en formato XML', copy=False)
    xml_file_hacienda_firmado = fields.Text('XML Firmado', copy=False)
    fecha_envio_hacienda = fields.Datetime('Fecha envio XML', copy=False)
    clave_envio_hacienda = fields.Char('Clave envio XML', copy=False, index=True)
    fecha_recibo_hacienda = fields.Datetime('Fecha recibo respuesta hacienda', copy=False)
    status_hacienda = fields.Selection([("error", "Enviada con errores"),
                                        ("aceptado", "Aceptada"),
                                        ("procesando", "Procesando"),
                                        ("rechazado", "Rechazado")],
                                       string="Estatus hacienda", copy=False, default=False)
    mostrar_boton = fields.Boolean('Mostrar boton para envio de facturas', compute='_compute_mostrar_boton', store=True)

    celula_fisica = fields.Char('Cédula fisica')
    celula_juridica = fields.Char('Cédula Juridica')
    nombre_facturar = fields.Char('Nombre a facturar')

    # exoneracion
    tipo_documento_pf = fields.Selection([('01', 'Compras Autorizadas'),
                                          ('02', 'Ventas exentas a diplomáticos'),
                                          ('03', 'Orden de compra (instituciones publicas y otros organismos)'),
                                          ('04', 'Exenciones Direccion General de Hacienda'),
                                          ('05', 'Zonas Francas'),
                                          ('99', 'Otros')], string='Tipo de Documento')
    numero_documento_pf = fields.Char('Numero de Documento')
    nombre_institucion_pf = fields.Char('Nombre de Institucion')
    fecha_emision_pf = fields.Datetime('Fecha de Emision')
    situacion = fields.Selection([('1', 'Normal'), ('2', 'Contingencia'), ('3', 'Sin Internet')],
                                 string='Situación del comprobante', default='1')
    pendiente_enviar = fields.Boolean('Pendiente enviar', default=False, copy=False)
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
        for inv in self:
            params = inv.consultar_parametros()
            recepcion = "recepcion"
            if params['facturacion_test']:
                recepcion = "recepcion-sandbox"
            token = inv.company_id.token_hacienda
            inv.consultar_invoice(token, recepcion, True)

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
            [('fname_xml_respuesta_tributacion', '=', False), ('clave_envio_hacienda', '!=', False)])
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
            for i in invoices_by_company[company_id]:
                i.consultar_invoice(token, recepcion, True)

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
        respuesta = requests.get(consulta, headers=headers)

        try:
            if int(respuesta.status_code) == 403 and reintentar:
                return self.consultar_invoice(self.company_id.get_token(), recepcion, False)
            elif int(respuesta.status_code) == 403:
                _logger.error("Error al obtener estado de factura %s\nRespuesta:",
                              (self.clave_envio_hacienda, respuesta.text))
                raise UserError("Error al obtener estado de factura %s\nRespuesta:",
                              (self.clave_envio_hacienda, respuesta.text))

            valores = eval(respuesta.text)  # convierte respuesta en dict
            if type(valores) is dict and valores.get("ind-estado", False):
                self.write({
                            'status_hacienda': valores.get("ind-estado"),
                            'xml_respuesta_tributacion': valores.get('respuesta-xml', False),
                            'fname_xml_respuesta_tributacion': "Respuesta " + self.number + ".xml",
                            'fecha_recibo_hacienda': datetime.now()
                })
        except:
            _logger.error("Error al obtener estado de factura %s\nRespuesta:",
                          (self.clave_envio_hacienda, respuesta.text))

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

                attachment.with_env(new_env).write({'name': fname, 'datas_fname': fname})

                email_template.with_env(new_env).attachment_ids = [(6, 0, [attachment.id])]
                # {'default_attachment_ids': [attachment.id]}
                email_template.with_env(new_env).send_mail(job['invoice_id'],
                                                           raise_exception=False,
                                                           force_send=True)  # default_type='binary'
                email_template.attachment_ids = [(3, attachment.id)]
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
            "receptor": {
                "tipoIdentificacion": receptor.identification_id.code,
                "numeroIdentificacion": str(receptor.ref or "")
            },
            "comprobanteXml": base64.b64encode(archivo_firmado)
        }

        if 'localhost' not in params['web.base.url']:
            values_to_send.update({'callbackUrl': params['web.base.url'] + "/receptor/hacienda"})

        token = self.company_id.token_hacienda

        headers = {'Content-type': 'application/json;charset=UTF-8',
                   'Authorization': token}

        json2send = simplejson.dumps(values_to_send)

        values2write = {
            'status_hacienda': 'procesando',
            'xml_file_hacienda_firmado': archivo_firmado,
            'xml_comprobante': base64.b64encode(archivo_firmado),
            'fname_xml_comprobante': clave + ".xml",
            'clave_envio_hacienda': clave,
            'fecha_envio_hacienda': (fecha + timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')
        }
        values2write.update({'pendiente_enviar': params['skip_facturacion']})
        # en caso que la bandera esté en True se intentara enviar luego
        self.write(values2write)
        if params['skip_facturacion']:
            # Crea el archivo pero no lo intenta enviar, esta opción es creada x si hacienda está caida
            return True

        r = requests.post('https://api.comprobanteselectronicos.go.cr/' + recepcion + '/v1/recepcion', data=json2send,
                          headers=headers)  # envia archivo a hacienda

        if int(r.status_code) >= 200 and int(r.status_code) <= 205:
            _logger.error("Factura %s enviada de manera exitosa" % (clave,))

        elif int(r.status_code) == 403 and not reintentar:
            self.company_id.get_token()
            return self.enviar_factura_hacienda(archivo_firmado, clave, fecha, True)
        elif int(r.status_code) == 403 and reintentar:
            raise UserError('Credenciales invalidos, contacte con el administrador de su sistema')

        if not self.partner_id.opt_out:
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
            JAR_PATH = 'firmador/xadessignercr.jar'  # 'firmador/firmar-xades.jar'
            firma_path = os.path.join(os.path.dirname(__file__), JAR_PATH)
            archivo_firmado = archivo_xml + "_firmado"
            # subprocess.call(['java', '-jar',  firma_path, archivo_p12, self.company_id.clave_llave, archivo_xml, archivo_firmado])
            subprocess.call(['java', '-jar', firma_path, 'sign', archivo_p12, self.company_id.clave_llave, archivo_xml,
                             archivo_firmado])
            firmado = open(archivo_firmado, "r").read()
            # print firmado
            return firmado  # open(archivo_firmado, "r").read()
        except Exception as e:
            raise UserError(
                _("Hubo un error al intentar firmar el archivo, contacte con su administrador\nError: (%s)." % (e,)))

    def action_invoice_sent_inherit(self):
        result = super(Invoice, self).action_invoice_sent()
        result['context']['another_attachment'] = (self.fname_xml_comprobante, self.xml_comprobante)
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
                                    form.reference_code_id.id)

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
                            'reference_code_id': form.reference_code_id.id,  # agregado
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
                xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1' or \
                         (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree2'
                # Put the reason in the chatter
                subject = _("Invoice refund")
                body = description
                refund.message_post(body=body, subject=subject)
        if xml_id:
            result = self.env.ref('account.%s' % (xml_id)).read()[0]
            invoice_domain = safe_eval(result['domain'])
            invoice_domain.append(('id', 'in', created_inv))
            result['domain'] = invoice_domain
            return result
        return True

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: