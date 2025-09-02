# -*- coding: utf-8 -*-
import json
import requests
import logging
import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval
import datetime
import pytz
import base64
import xml.etree.ElementTree as ET
from odoo.addons.base.res.res_partner import Partner
from odoo.addons.base.res.res_company import Company
from dateutil.parser import parse
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT

_logger = logging.getLogger(__name__)


class IdentificationType(models.Model):
    _name = "identification.type"

    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )
    notes = fields.Text(string="Notas", required=False, )


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


class ElectronicTaxCode(models.Model):
    _name = "account.tax.cr.code"

    name = fields.Char(string="Descripción", required=True)
    code = fields.Char(string="Código de impuesto", required=True)

    _sql_constraints = [
        ('code_uniq', 'unique (code)', "El código ya ha sido asignado!"),
    ]


class  FiscalPositionTax(models.Model):
    _inherit = "account.fiscal.position.tax"

    porc_auth = fields.Integer(string="Porcentaje de la compra exonerado", required=True)


class InvoiceTaxElectronic(models.Model):
    _inherit = "account.tax"

    tax_code = fields.Many2one("account.tax.cr.code", string="Código de impuesto", required=False)


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


class ReferenceCode(models.Model):
    _name = "reference.code"

    active = fields.Boolean(string="Activo", required=False, default=True)
    code = fields.Char(string="Código", required=False, )
    name = fields.Char(string="Nombre", required=False, )


class Resolution(models.Model):
    _name = "resolution"

    active = fields.Boolean(string="Activo", required=False, default=True)
    name = fields.Char(string="Nombre", required=False, )
    date_resolution = fields.Datetime(string="Fecha de resolución", required=False, )


class ProductUom(models.Model):
    _inherit = "product.uom"
    code = fields.Char(string="Código", required=False, )


class AccountJournal(models.Model):
    _inherit = "account.journal"
    nd = fields.Boolean(string="Nota de Débito", required=False, )


class AccountInvoiceRefund(models.TransientModel):
    _inherit = "account.invoice.refund"

    @api.model
    def _get_invoice_id(self):
        context = dict(self._context or {})
        active_id = context.get('active_id', False)
        if active_id:
            return active_id
        return ''


    @api.model
    def _default_reference_code_id(self):
        reference_code = self.env.ref('cr_electronic_invoice.ReferenceCode_1')
        if reference_code:
            return reference_code.id
        return False

    reference_code_id = fields.Many2one(comodel_name="reference.code", string="Código de referencia", required=True)#, default=_default_reference_code_id)
    invoice_id = fields.Many2one(comodel_name="account.invoice", string="Documento de referencia",
                                 default=_get_invoice_id, required=False, )

    @api.onchange('invoice_id')
    def onchange_factura(self):
        reference_code_anulacion = self.env.ref('cr_electronic_invoice.ReferenceCode_1')
        reference_code_modificacion = self.env.ref('cr_electronic_invoice.ReferenceCode_3')
        return {'domain': {'reference_code_id': [('id', '=', (reference_code_anulacion.id, reference_code_modificacion.id))]}}

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


class InvoiceLineElectronic(models.Model):
    _inherit = "account.invoice.line"

    total_amount = fields.Float(string="Monto total", required=False, )
    total_discount = fields.Float(string="Total descuento", required=False, )
    discount_note = fields.Char(string="Nota de descuento", required=False, )
    total_tax = fields.Float(string="Total impuesto", required=False, )


    # exoneration_total = fields.Float(string="Exoneración total", required=False, )
    # total_line_exoneration = fields.Float(string="Exoneración total de la línea", required=False, )
    # exoneration_id = fields.Many2one(comodel_name="exoneration", string="Exoneración", required=False, )


class AccountInvoiceElectronic(models.Model):
    _inherit = "account.invoice"

    number_electronic = fields.Char(string="Número electrónico",  copy=False, index=True)
    date_issuance = fields.Datetime(string="Fecha de emisión",  copy=False)
    state_send_invoice = fields.Selection([('aceptado', 'Aceptado'), ('rechazado', 'Rechazado'), ],
                                          'Estado FE Proveedor')
    state_tributacion = fields.Selection(
        [('aceptado', 'Aceptado'), ('rechazado', 'Rechazado'), ('no_encontrado', 'No encontrado')], 'Estado FE',
        copy=False)
    state_invoice_partner = fields.Selection([('05', 'Aceptado'), ('06', 'Aceptacion parcial'), ('07', 'Rechazado')],
                                             'Respuesta del Cliente')
    reference_code_id = fields.Many2one(comodel_name="reference.code", string="Código de referencia",  )
    payment_methods_id = fields.Many2one(comodel_name="payment.methods", string="Métodos de Pago" )
    invoice_id = fields.Many2one(comodel_name="account.invoice", string="Documento de referencia",
                                 copy=False)
    xml_respuesta_tributacion = fields.Binary(string="Respuesta Tributación XML",  copy=False,
                                              attachment=True)
    fname_xml_respuesta_tributacion = fields.Char(string="Nombre de archivo XML Respuesta Tributación",
                                                  copy=False)
    xml_comprobante = fields.Binary(string="Comprobante XML",  copy=False, attachment=True)
    fname_xml_comprobante = fields.Char(string="Nombre de archivo Comprobante XML",  copy=False,
                                        attachment=True)
    xml_supplier_approval = fields.Binary(string="XML Proveedor",  copy=False, attachment=True)
    fname_xml_supplier_approval = fields.Char(string="Nombre de archivo Comprobante XML proveedor",
                                              copy=False, attachment=True)
    amount_tax_electronic_invoice = fields.Monetary(string='Total de impuestos FE', readonly=True, )
    amount_total_electronic_invoice = fields.Monetary(string='Total FE', readonly=True, )

    _sql_constraints = [
        ('number_electronic_uniq', 'unique (number_electronic)', "La clave de comprobante debe ser única"),
    ]

    @api.onchange('xml_supplier_approval')
    def _onchange_xml_supplier_approval(self):
        if self.xml_supplier_approval:
            try:
                root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(self.xml_supplier_approval),
                                        count=1))  # quita el namespace de los elementos
            except:
                raise UserError("Por favor cargue un archivo en formato XML.")
            if not root.findall('Clave'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo Clave. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('FechaEmision'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo FechaEmision. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo Emisor. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo Identificacion. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Tipo'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo Tipo. Por favor cargue un archivo con el formato correcto.'}}
            if not root.findall('Emisor')[0].findall('Identificacion')[0].findall('Numero'):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'El archivo xml no contiene el nodo Numero. Por favor cargue un archivo con el formato correcto.'}}
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalImpuesto')):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'No se puede localizar el nodo TotalImpuesto. Por favor cargue un archivo con el formato correcto.'}}
            if not (root.findall('ResumenFactura') and root.findall('ResumenFactura')[0].findall('TotalComprobante')):
                return {'value': {'xml_supplier_approval': False}, 'warning': {'title': 'Atención',
                                                                               'message': 'No se puede localizar el nodo TotalComprobante. Por favor cargue un archivo con el formato correcto.'}}

    # self.fname_xml_supplier_approval = 'comrpobante_proveedor.xml'

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

    @api.onchange('xml_supplier_approval')
    def charge_xml_data(self):
        if self.xml_supplier_approval:
            root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(self.xml_supplier_approval),
                                        count=1))  # quita el namespace de los elementos
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
            fecha = datetime.datetime.strftime(fecha, DEFAULT_SERVER_DATETIME_FORMAT)
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
                'currency_id': self.search_data('res_currency', resumenFactura.findall('CodigoMoneda')[0].text),
                'invoice_line_ids': lineas_factura
            })

    @api.multi
    def send_xml(self):
        inv  = self
        if inv.xml_supplier_approval:
            root = ET.fromstring(re.sub(' xmlns="[^"]+"', '', base64.b64decode(inv.xml_supplier_approval), count=1))
            if not inv.state_invoice_partner:
                raise UserError('Aviso!.\nDebe primero seleccionar el tipo de respuesta para el archivo cargado.')
            if float(root.findall('ResumenFactura')[0].findall('TotalComprobante')[0].text) == inv.amount_total:
                    status = inv.state_invoice_partner
                    journal = inv.journal_id
                    if not journal.sucursal or not journal.terminal:
                        raise UserError("Debe definir una sucursal y una terminal para el diario")

                    detalle_mensaje = {'05': ('1', 'Aceptado'), '06': ('2', 'Aceptado parcial'), '07': ('3', 'Rechazado')}[status]
                    payload = {
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
                    return payload

            else:
                raise UserError(
                    'Error!.\nEl monto total de la factura no coincide con el monto total del archivo XML')

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
        super(AccountInvoiceElectronic, self)._onchange_partner_id()
        self.payment_methods_id = self.partner_id.payment_methods_id

    @api.multi
    def action_invoice_open(self):
        super(AccountInvoiceElectronic, self).action_invoice_open()
        _logger.error('MAB - entrando action_invoice_open')
        import sys
        reload(sys)
        sys.setdefaultencoding('UTF8')
        for inv in self:
            if True:
                TipoDocumento = ''
                FacturaReferencia = ''
                now_utc = datetime.datetime.now(pytz.timezone('UTC'))
                now_cr = now_utc.astimezone(pytz.timezone('America/Costa_Rica'))
                date_cr = now_cr.strftime("%Y-%m-%dT%H:%M:%S-06:00")
                tipo_documento_referencia = ''
                numero_documento_referencia = ''
                fecha_emision_referencia = ''
                codigo_referencia = ''
                razon_referencia = ''
                medio_pago = inv.payment_methods_id.sequence or '01'
                if inv.type == 'out_invoice':  # FC Y ND
                    if inv.invoice_id and inv.journal_id and inv.journal_id.nd:
                        TipoDocumento = '02'
                        tipo_documento_referencia = inv.invoice_id.number_electronic[
                                                    29:31]  # 50625011800011436041700100001 01 0000000154112345678
                        numero_documento_referencia = inv.invoice_id.number_electronic
                        fecha_emision_referencia = inv.invoice_id.date_issuance
                        codigo_referencia = inv.reference_code_id.code
                        razon_referencia = inv.reference_code_id.name
                        medio_pago = ''
                    else:
                        TipoDocumento = '01'
                if inv.type == 'out_refund':  # NC
                    if inv.invoice_id.journal_id.nd:
                        tipo_documento_referencia = '02'
                    else:
                        tipo_documento_referencia = '01'
                    TipoDocumento = '03'
                    numero_documento_referencia = inv.invoice_id.number_electronic
                    fecha_emision_referencia = inv.invoice_id.date_issuance
                    codigo_referencia = inv.reference_code_id.code
                    razon_referencia = inv.reference_code_id.name
                    if inv.origin and inv.origin.isdigit():
                        FacturaReferencia = (inv.origin)
                    else:
                        FacturaReferencia = 0
                if inv.payment_term_id:
                    if inv.payment_term_id.sale_conditions_id:
                        sale_conditions = inv.payment_term_id.sale_conditions_id.sequence or '01'
                    else:
                        raise UserError(
                            'No se pudo Crear la factura electrónica: \n Debe configurar condiciones de pago para %s' %
                            (inv.payment_term_id.name,))
                else:
                    sale_conditions = '01'

                if TipoDocumento:
                    currency_rate = 1 / inv.currency_id.rate
                    lines = []
                    base_total = 0.0
                    numero = 0
                    if inv.partner_id.identification_id.code == '05':
                        receptor_identificacion = {
                            'tipo': False,
                            'numero': False,
                        }
                        receptor_identificacion_extranjero = inv.partner_id.vat
                    else:
                        receptor_identificacion = {
                            'tipo': inv.partner_id.identification_id.code,
                            'numero': inv.partner_id.vat,
                        }
                        receptor_identificacion_extranjero = ''

                    totalserviciogravado = 0.0
                    totalservicioexento = 0.0
                    totalmercaderiagravado = 0.0
                    totalmercaderiaexento = 0.0
                    for inv_line in inv.invoice_line_ids:
                        impuestos_acumulados = 0.0
                        numero += 1
                        base_total += inv_line.price_unit * inv_line.quantity
                        impuestos = []
                        for i in inv_line.invoice_line_tax_ids:
                            code = i.tax_code.code
                            if code <> '00':
                                impuestos.append({
                                    'codigo': code,
                                    'tarifa': i.amount,
                                    'monto': round(i.amount / 100 * inv_line.price_subtotal, 2),
                                })
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
                        line = {
                            'numero': numero,
                            'codigo': [{
                                'tipo': inv_line.product_id.code_type_id.code or '04',
                                'codigo': inv_line.product_id.default_code or '000',
                            }],
                            'cantidad': inv_line.quantity,
                            'unidad_medida': inv_line.uom_id.code or 'Sp',
                            'unidad_medida_comercial': inv_line.product_id.commercial_measurement,
                            'detalle': inv_line.name[:159],
                            'precio_unitario': inv_line.price_unit,
                            'monto_total': inv_line.quantity * inv_line.price_unit,
                            'descuento': (round(inv_line.quantity * inv_line.price_unit, 2) - round(
                                inv_line.price_subtotal, 2)) or '',
                            'naturaleza_descuento': inv_line.discount_note,
                            'subtotal': inv_line.price_subtotal,
                            'impuestos': impuestos,
                            'montototallinea': inv_line.price_subtotal + impuestos_acumulados,
                        }
                        lines.append(line)
                    _logger.info('MAB - formando payload')
                    journal = inv.journal_id
                    if not journal.sucursal or not journal.terminal:
                        raise UserError("Debe definir una sucursal y una terminal para el diario")

                    payload = {
                        'clave': {
                            'sucursal': journal.sucursal,
                            'terminal': journal.terminal,
                            'tipo': TipoDocumento,
                            'comprobante': inv.number,#int(inv.number),
                            'pais': '506',
                            'dia': '%02d' % now_cr.day,
                            'mes': '%02d' % now_cr.month,
                            'anno': str(now_cr.year)[2:4],
                            'situacion_presentacion': '1',

                        },
                        'encabezado': {
                            'fecha': date_cr,
                            # 'fecha': "2018-01-19T23:17:00+06:00",
                            'condicion_venta': sale_conditions,
                            'plazo_credito': '0',
                            'medio_pago': medio_pago
                        },
                        'emisor': {
                            'nombre': inv.company_id.name,
                            'identificacion': {
                                'tipo': inv.company_id.identification_id.code,
                                'numero': inv.company_id.vat,
                            },
                            'nombre_comercial': inv.company_id.commercial_name or '',
                            'ubicacion': {
                                'provincia': inv.company_id.state_id.code,
                                'canton': inv.company_id.county_id.code,
                                'distrito': inv.company_id.district_id.code,
                                'barrio': inv.company_id.neighborhood_id.code,
                                'sennas': inv.company_id.street,
                            },
                            'telefono': {
                                'cod_pais': inv.company_id.phone_code,
                                'numero': inv.company_id.phone,
                            },
                            'fax': {
                                'cod_pais': inv.company_id.fax_code,
                                'numero': inv.company_id.fax,
                            },
                            'correo_electronico': inv.company_id.email,
                        },
                        'receptor': {  ##
                            'nombre': inv.partner_id.name[:80],
                            'identificacion': receptor_identificacion,
                            'IdentificacionExtranjero': receptor_identificacion_extranjero,
                        },
                        'detalle': lines,
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
                        },
                        'referencia': [{
                            'tipo_documento': tipo_documento_referencia,
                            'numero_documento': numero_documento_referencia,
                            'fecha_emision': fecha_emision_referencia,
                            'codigo': codigo_referencia,
                            'razon': razon_referencia,
                        }],
                        'otros': [{
                            'codigo': '',
                            'texto': '',
                            'contenido': ''
                        }],
                    }

                    return payload


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
