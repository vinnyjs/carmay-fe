# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import logging
from yattag import indent
from datetime import datetime
import base64
_logger = logging.getLogger(__name__)


class Receptor(http.Controller):

    @http.route('/receptor/hacienda', type='json', auth='none', cors='*', methods=['POST'])
    def recibe_respuesta(self, **kwargs):
        """
        :param data: Respuesta enviada por parte de hacienda
        :return: respuesta 200 para hacienda, no se debe devolver algo
        distinto debido a que hacienda pone al contribuyente en lista negra
        """
        data = request.jsonrequest
        _logger.error("Obteniendo respuesta de hacienda %s", data)
        try:
            if not type(data) is dict:
                return {}
            _logger.info("Respuesta:%s" % (data['clave'],))
            cr = request.env.cr
            cr.execute("select id from account_invoice where clave_envio_hacienda='%s' limit 1;" % (data['clave'],))
            _logger.info("Query:%s" % (cr.query,))
            result = cr.dictfetchone()
            if result:
                factura = request.env['account.invoice'].browse(result['id'])

                to_update = {
                            'status_hacienda': data.get("ind-estado", "procesando")
                }
                if data.get('respuesta-xml', False):
                   to_update.update({
                       'xml_respuesta_tributacion': data.get('respuesta-xml', False),
                       'fname_xml_respuesta_tributacion': data['clave'] + "-Respuesta.xml",
                       'fecha_recibo_hacienda': datetime.now()
                   })
                factura.write(data)

                _logger.info("Actualizada:%s" % (data['clave'],))
        except Exception as e:
            _logger.error("Error al obtener estado de factura\n" + e.message)
        finally:
            return {} #Devolver 200 siempre para que hacienda no se enoje



class VisorDocumentosHacienda(http.Controller):

    @http.route('/visor/<string:cedula>/<string:clave>', type='http', auth="none", cors="*")
    def mostrar_archivos(self, cedula, clave):
        """
        :param cedula: Cédula de la compañia
        :param clave: clave del archivo de hacienda que queremos consultar
        :return: plantilla para visualizar documentos en linea
        """
        if not cedula or not clave:
            return False
        cr = request.env.cr
        clave2search = clave.replace('.xml', '')
        cr.execute("select id, xml_file_hacienda_firmado from account_invoice where clave_envio_hacienda='%s' limit 1;" % (clave2search,))
        _logger.info("Query: %s" % (cr.query,))
        result = cr.dictfetchone()
        data = {}
        if result:
            """
            report_obj = request.env['report']
            pdf_file = report_obj.sudo().get_pdf([result['id']], u'account.report_invoice', data={})
            pdf = "data:application/pdf;base64," + pdf_file.encode("base64")
            data.update({"pdf": pdf})
            """
            respuesta = False
            data.update({"pdf": "/report/preview/public?data=[%22%2Freport%2Fpdf%2Faccount.account_invoice_report_duplicate_main%2F" +str(result['id'])+ "%3Fenable_editor%3D1%22%2C%22qweb-pdf%22]&token=1550871087756"})

            xml = bytes(bytearray(result['xml_file_hacienda_firmado'], encoding='utf-8'))
            cr.execute("select store_fname from ir_attachment where \
                        res_model='account.invoice' and res_field='xml_respuesta_tributacion' and res_id=%s;" % (
                        result['id'],))
            _logger.info("Query Respuesta: %s" % (cr.query,))
            resultRespuesta = cr.dictfetchone()
            if resultRespuesta and resultRespuesta.get('store_fname'):
                respuesta = request.env['ir.attachment']._file_read(resultRespuesta['store_fname'])
                data.update({"respuestaXmlFile": indent(base64.decodestring(respuesta), indentation='    ')})

            data.update({"xmlFile": indent(xml, indentation='    ')})

        return request.render('facturacion_hacienda.visor_documentos', data)
