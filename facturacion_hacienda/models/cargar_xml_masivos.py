# -*- coding: utf-8 -*-
import psycopg2
import psycopg2.extras
from datetime import datetime
from dateutil.parser import parse
import sys
# import chilkat
from os import listdir
from os.path import isfile, join
from lxml import etree as ET
import re
from odoo import models, api
import base64
import logging
_logger = logging.getLogger("CARGAR ARCHIVOS XML MASIVAMENTE")

DEFAULT_SERVER_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_SERVER_TIME_FORMAT = "%H:%M:%S"
DEFAULT_SERVER_DATETIME_FORMAT = "%s %s" % (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_TIME_FORMAT)

# glob = chilkat.CkGlobal()
# KEY_CHILKAT = "PRCWLL.CB1012020_HJ4nYdcR59mg"
KEY_CHILKAT = "AKHVAT.CB4112019_nu3k6EN2no4h"
# KEY_CHILKAT = "TNYNSC.CB1012020_EmzcqmDxk26p"
# success = glob.UnlockBundle(KEY_CHILKAT)
class Invoice(models.Model):
    _inherit = 'account.invoice'

    def find_between(self, s, value):
        first = '<' + value
        last = value + '>'
        try:
            start = s.index(first) + len(first)
            #_logger.info("start:%s"%start)
            end = s.index(last, start)
            #_logger.info("end:%s"%end)

            parser = ET.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
            #_logger.info(value)
            #_logger.info(s[start:end])

            doc = ET.fromstring(first + s[start:end] + last, parser)
            #_logger.info("sale")

            return doc

        except ValueError as e:
            #_logger.error("%s"%e)
            return False


    def find_record(self, table, condition, cursor):
        query = '''
            select id from %s where %s limit 1
        '''
        query_condition = ''
        for cond in condition:
            val = condition[cond]
            val_type = type(val)

            if val_type in (str, unicode):
                value = " like '%%" + val + "%%'"
            elif val_type in (int, float):
                value = " = " + str(val)
            elif val_type is bool:
                value = " = " + (val and "'t'" or "'f'")
            #_logger.info(cond)
            #_logger.info(condition) 

            query_condition += cond + value + ' and '

        query_condition += ' id != 0 '
        cursor.execute(query % (table, query_condition))
        # print cursor.query
        result = cursor.fetchone()

        if result and len(result) > 0:
            return result[0]
        return False


    def load_massive_supplier_xml(self, archivo, company_id, connection, cursor):
        """
        :param archivo: root XML document
        :return: completa la CxP con los datos enviados en el XML del proveedor
        """
        # partner = self.env['res.partner'].search(
        #    [('ref', '=', archivo.get('emisor').find('Identificacion')[1].text), ('supplier', '=', True)])
        cedula_proveedor = archivo.get('emisor').find('Identificacion')[1].text
        partner = self.find_record('res_partner', {
            'ref': cedula_proveedor,
            'supplier': True,
            'company_id': company_id
        }, cursor)

        if not partner:
            cursor.execute("""insert into res_partner(active, name, display_name, email, company_id, identification_id, ref, notify_email, supplier, sale_warn, invoice_warn, picking_warn, purchase_warn) 
                                        values('t', '%s', '%s', '%s', %s, %s, '%s', 'always', 't', 'no-message', 'no-message', 'no-message', 'no-message') RETURNING id""" %
                           (archivo.get('emisor').find('Nombre').text, archivo.get('emisor').find('Nombre').text,
                            archivo.get('emisor').find('CorreoElectronico') and archivo.get('emisor').find('CorreoElectronico').text or "",
                            company_id, 1 if len(cedula_proveedor) == 9 else 2, cedula_proveedor))
            partner = cursor.fetchone()[0]
            connection.commit()

        fecha = parse(archivo.get('emision').text)
        resumenFactura = archivo.get('resumen')
        fecha = datetime.strftime(fecha, DEFAULT_SERVER_DATETIME_FORMAT)
        lineas_factura = []

        diario_id = self.find_record('account_journal', {'company_id': company_id, 'type': 'purchase'}, cursor)
        default_payable_account = self.find_record('account_account', {'company_id': company_id, 'code': '0-211001'}, cursor)
        clave = archivo.get('clave').text

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
            'number_electronic': clave,
            'date_issuance': fecha,
            'date_invoice': fecha,
            'date': fecha,
            'amount_total_electronic_invoice': float(resumenFactura.find('TotalComprobante').text),
            'currency_id': self.find_record('res_currency', {'name': moneda }, cursor),
            'company_id': company_id,
            'partner_id': partner,
            'journal_id': diario_id,
            'account_id': default_payable_account,
            'reference': clave[21:41],
            'type':  'in_invoice', #'in_refund',
            'state_invoice_partner': '05'
        }


        default_account = self.find_record('account_account', {'company_id': company_id, 'code': '0-511301'}, cursor)


        for l in archivo.get('lineas').findall('LineaDetalle'):
            linea = {
                'account_id': default_account,
                'name': l.find('Detalle').text,
                'quantity': float(l.find('Cantidad').text),
                'uom_id': self.find_record('product_uom', {'code': l.find('UnidadMedida').text}, cursor),
                'price_unit': float(l.find('PrecioUnitario').text)
            }
            if l.find('Codigo') is not None and l.find('Codigo').find('Codigo') is not None:
                linea['name'] = '[' + l.find('Codigo').find('Codigo').text + '] ' + linea['name']

            impuesto = l.find('Impuesto')
            if impuesto is not None:
                impuesto = self.find_record('account_tax', {'name': str( int( float(impuesto.find('Tarifa').text) ) ), 'type_tax_use': 'purchase', 'company_id': company_id}, cursor)
                if impuesto:
                    linea.update({'invoice_line_tax_ids': [ [ 6, False, [impuesto] ] ] })
                elif impuesto:
                    _logger.info("IMPUESTO ---> "+str(impuesto))
                    cursor.execute("""insert into account_tax(active, name, tax_code, type_tax_code, company_id, amount, amount_type) 
                                        values('t', '%s', 2, 'purchase', %s, %s, 'percent') RETURNING id""" %
                           ( str(int( float(impuesto.find('Tarifa').text) )), company_id, float(impuesto.find('Tarifa').text) ) )
                    impuesto = cursor.fetchone()[0]
                    connection.commit()
                    linea.update({'invoice_line_tax_ids': [ [ 6, False, [impuesto] ] ] })

                if False: #codigo_impuesto:
                    new_impuesto = self.find_record('account_tax', {'tax_code': codigo_impuesto, 'type_tax_use': 'purchase',
                                                               'company_id': company_id}, cursor)
                    if new_impuesto:
                        linea.update({'invoice_line_tax_ids': [new_impuesto]})
                    else:
                        tarifa = impuesto.find('Tarifa')
                        if tarifa is not None:
                            if re.match("^\d+?\.\d+?$", tarifa.text) is not None:
                                new_impuesto2 = self.find_record('account_tax',
                                                            {'amount': float(tarifa.text), 'type_tax_use': 'purchase',
                                                             'company_id': company_id}, cursor)
                                if new_impuesto2:
                                    linea.update({'invoice_line_tax_ids': [new_impuesto2]})

            else:
                codigo_impuesto = self.find_record('account_tax_cr_code', {'code': '00'}, cursor)
                if codigo_impuesto:
                    impuesto = self.find_record('account_tax', {'tax_code': codigo_impuesto, 'type_tax_use': 'purchase',
                                                           'company_id': company_id}, cursor)
                    if impuesto:
                        linea.update({'invoice_line_tax_ids': [impuesto]})

            descuento = l.find('MontoDescuento')
            if descuento is not None:
                desc = float(descuento.text)
                monto_total = linea['quantity'] * linea['price_unit']
                linea.update({'discount': round((desc / monto_total) * 100, 2)})

            lineas_factura.append([0, 0, linea])
        values.update({'invoice_line_ids': lineas_factura})

        if resumenFactura.findall('TotalImpuesto'):
            values.update({'amount_tax_electronic_invoice': float(resumenFactura.findall('TotalImpuesto')[0].text)})

        return values

    @api.multi
    def load_multi_invoices(self, location, company_id, start=0, stop=50, terminos_validos=['FacturaElectronica']): #, 'TiqueteElectronico']):
        connection = psycopg2.connect(user="odoo",
                                      host="127.0.0.1",
                                      port="5432",
                                      database="ssvmn.videncr.com",
                                      password="GoAbMh7ZNzi5Kadmin@")

        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

        mypath = location

        onlyfiles = [f for f in listdir(mypath) if isfile(join(mypath, f)) and '.xml' in f.lower()]
        cant_archivos = len(onlyfiles)
        _logger.info("Cantidad de xml encontrados %s" % (cant_archivos,) )

        for file in onlyfiles[start:stop]:

            if True: #try:
                f = open(join(mypath, file), "r")
                archivo = f.read()
                valido = False
                for term in terminos_validos:
                    _logger.info("termino:%s, archivo:%s" %(term, file))
                    if not valido:
                        valido = self.find_between(archivo, term)

                if not valido:
                    _logger.info("Archivo no valido: %s" %( file,))
                    cant_archivos -= 1
                    continue
                else:
                    pass #_logger.info("Pasa")
                #_logger.info("AQIOIIII = %s"%(valido,))


                clave = self.find_between(ET.tostring(valido), "Clave")
                _logger.info("REVISANDO = %s"%( {'number_electronic': clave.text},))

                resultado_repetidos = self.find_record('account_invoice', {'number_electronic': clave.text}, cursor)
                #_logger.info("resultado_repetidos = %s"%( resultado_repetidos,))

                if resultado_repetidos:
                    _logger.info("Clave duplicada: %s" %(clave.text,))
                    cant_archivos -= 1
                    continue

                emisor = self.find_between(ET.tostring(valido), "Emisor")
                receptor = self.find_between(ET.tostring(valido), "Receptor")

                f_emision = self.find_between(ET.tostring(valido), "FechaEmision")
                lineas_factura = self.find_between(ET.tostring(valido), "DetalleServicio")
                resumen = self.find_between(ET.tostring(valido), "ResumenFactura")

                factura = {
                    'emisor': emisor,
                    'receptor': receptor,
                    'emision': f_emision,
                    'clave': clave,
                    'lineas': lineas_factura,
                    'resumen': resumen
                }

                invoice_vals = self.load_massive_supplier_xml(factura, company_id, connection, cursor)

                invoice_vals.update({'fname_xml_supplier_approval': file, 'xml_supplier_approval': base64.b64encode( '<?xml version="1.0" encoding="utf-8"?>' + ET.tostring(valido) )})
                self.create(invoice_vals)
            if False: #except Exception as e:
                _logger.info("ERROR en archivo: %s\n%s" % (file, e))
            cant_archivos -= 1
            _logger.info("Faltan: %s archivos" % (cant_archivos,))

        return True

