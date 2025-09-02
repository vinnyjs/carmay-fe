# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
import random
from dateutil.parser import parse
from datetime import timedelta
from odoo import _
import re, logging

_logger = logging.getLogger(__name__)

cabeceras = {
    "facturaVenta": """<FacturaElectronica
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronica"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">""",

    "facturaVentaExportacion": """<FacturaElectronicaExportacion
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronicaExportacion"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">""",

    "facturaCompra": """<FacturaElectronicaCompra
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/facturaElectronicaCompra"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">""",

    "notaCredito": """<NotaCreditoElectronica 
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaCreditoElectronica" 
        xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">""",

    "notaDebito": """<NotaDebitoElectronica
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/notaDebitoElectronica"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">""",

    "mensaje": """<MensajeReceptor
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/mensajeReceptor" 
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">"""
}

cierres = {
    "facturaVenta": """</FacturaElectronica>""",

    "facturaVentaExportacion": """</FacturaElectronicaExportacion>""",

    "facturaCompra": """</FacturaElectronicaCompra>""",

    "notaCredito": """</NotaCreditoElectronica>""",

    "notaDebito": """</NotaDebitoElectronica>""",

    "mensaje": """</MensajeReceptor>""",
}


class DocumentoXml:

    def __init__(self, invoice_data):
        self.invoice = invoice_data
        type_doc = {
            '00': 'mensaje',
            '01': 'facturaVenta',
            '02': 'notaDebito',
            '03': 'notaCredito',
            '08': 'facturaCompra',
            '09': 'facturaVentaExportacion'
        }[invoice_data['clave'][29:31]]

        if type_doc not in cabeceras.keys():
            raise UserError(("Tipo de documento no existe."))
        self.tipo_doc = type_doc
        self.clave = invoice_data['clave']
        self.fecha = invoice_data['encabezado']['fecha']
        self.resumen = invoice_data['resumen']


    def getConsecutivo(self):
        invoice = self.invoice
        sucursal = (invoice.journal_id.sucursal or "001").zfill(3)
        punto_de_venta = (invoice.journal_id.terminal or "00001").zfill(5)
        tipo_doc = {
            'in_invoice': '00',  # Vendor Bill
            'out_invoice': '01',  # Customer Invoice
            'out_refund': '03',  # Customer Refund
            'in_refund': '00',  # Vendor Refund
        }
        tipo = tipo_doc[invoice.type]
        if tipo == '00':
            if not invoice.xml_supplier_approval:
                tipo = '08'
            else:
                tipo = invoice.state_invoice_partner
        if tipo == '01':
            if invoice.journal_id.exportacion:
                tipo = '09'
        return sucursal + punto_de_venta + tipo + invoice.number.zfill(
            10)  # str(int(random.random() *123123)).zfill(10)

    def get_Clave(self):
        return self.clave

    def generarClaveFactura(self):
        clave = "506"
        fecha = self.fecha
        invoice = self.invoice
        clave += str(fecha.strftime('%d'))
        clave += str(fecha.strftime('%m'))
        clave += str(fecha.strftime('%y'))
        clave += invoice.company_id.partner_id.ref.zfill(12)
        numeroConsecutivo = self.getConsecutivo()
        clave += numeroConsecutivo
        clave += invoice.situacion
        clave += str(int(random.random() * 123123)).zfill(8)
        self.clave = clave
        return (clave, numeroConsecutivo)

    def get_informacion_extra(self):
        last_invoice = self.invoice.invoice_id
        if not last_invoice:
            return ""
        types = {
            'out_invoice': '01',
            'out_refund': '02',
            'in_refund': '03'
        }

        clave = last_invoice.clave_envio_hacienda or last_invoice.number
        fecha_anulacion = (parse(last_invoice.fecha_envio_hacienda or last_invoice.validate_date) - timedelta(
            hours=6)).strftime('%Y-%m-%dT%H:%M:%S')

        template = """
            <InformacionReferencia>
            <TipoDoc>""" + types[last_invoice.type] + """</TipoDoc>
            <Numero>""" + clave + """</Numero>
            <FechaEmision>""" + fecha_anulacion + """</FechaEmision>
            <Codigo>""" + self.invoice.reference_code_id.code + """</Codigo>
            <Razon>""" + (self.invoice and self.invoice.name or 'Error')[:180] + """</Razon>
            </InformacionReferencia>
        """
        return template

    def generate_xml(self):

        clave, numeroConsecutivo = self.clave, self.clave[21:41]
        doc = """<?xml version="1.0" encoding="UTF-8"?>"""
        doc += cabeceras[self.tipo_doc]
        doc += self.devolverPlantilla(clave, numeroConsecutivo)
        doc += cierres[self.tipo_doc]
        return doc

    def validar_telefonos(self, numero):
        if numero:
            if not numero.isdigit():
                raise UserError('El número de teléfono o fax debe contener solamente numeros.')
            if len(numero) > 20:
                raise UserError('El número de teléfono o fax debe ser de un largo de 20 caracteres.')

    def validar_correo(self, correo):
        if correo:
            if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", correo.lower()):
                raise UserError('El correo electrónico no cumple con una estructura válida.')

    def validar_datos(self, cliente):
        if cliente.identification_id:
            code = cliente.identification_id.code
            ced = cliente.ref
            if not ced or not code:
                raise UserError(
                    'Debe asignar un código o una cédula al cliente.')
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
            self.validar_telefonos(cliente.phone)
            self.validar_telefonos(cliente.fax)
            self.validar_telefonos(cliente.mobile)
            self.validar_correo(cliente.email)
            self.validar_correo(cliente.correo_envio_fe)

    def devolverPlantilla(self, clave, numeroConsecutivo):
        """
            a=506 --> codigo pais
            b=17  --> dia
            c=01  -->  mes
            d=18  --> año
            e=000304670331 --> cedula
            f=00100001010000000004 -->numeración consecutiva del comprobante electrónico
            g=1 --> situación del comprobante electrónico
            h=99999931 --> Secuencia generada por el sistema

           ****
            Explicacion de f 00100001010000000004
            001--> casa matriz, sucursales
            00001--> termminal o punto de venta
            01 --> tipo de comprobante o documento asociado
            0000000004 --> consecutivo de los comprobantes
            electrónicos o documento asociado iniciando en el número 1, para cada sucursal o terminal
            según sea el caso(me parece que es)
        """
        # ----------------------------- 2018-04-25T15:22:18.020
        # ----------------------------- 25-04-2018 22:50:08
        resumen = self.resumen
        tipo_doc = self.tipo_doc
        fecha = self.fecha

        invoice = self.invoice

        fecha_actual = fecha.strftime('%Y-%m-%dT%H:%M:%S')
        partner = invoice.partner_id
        company_partner = invoice.company_id.partner_id

        if invoice.type == "in_invoice":
            # invierte los datos en caso que se vaya a generar un mensaje
            partner = invoice.company_id.partner_id
            company_partner = invoice.partner_id

        global cont_linea
        cont_linea = 0
        posicion_fiscal = invoice.fiscal_position_id or False

        def crearLinea(l):  # Crea las lineas de las facturas
            global cont_linea
            cont_linea += 1
            tipo_codigo_producto = l.product_id and l.product_id.code_type_id.code or "04"
            codigo_producto = l.product_id and (l.product_id.default_code or l.product_id.barcode) or "Sin código"
            if not l.uom_id:
                raise UserError(_("Hace falta definir un la unidad de medida."))
            if not l.uom_id.code:
                raise UserError(_("Hace falta definir un código a la unidad de medida."))
            exoneracion = ""
            impuesto = ""
            if posicion_fiscal:
                old_tax = l.product_id.taxes_id[0]
                line_tax = posicion_fiscal.tax_ids.filtered(lambda t: t.tax_src_id.id == old_tax.id)
                if not line_tax:
                    raise UserError("No se ha encontrado el impuesto sustituto.")
                if int(line_tax.porc_auth) == 0:
                    raise UserError("Debe especificar el monto a exonerar en la ficha de la posición fiscal.")

                exoneracion = """<Exoneracion>
        					<TipoDocumento>""" + invoice.tipo_documento_pf + """</TipoDocumento>
        					<NumeroDocumento>""" + invoice.numero_documento_pf[:17] + """</NumeroDocumento>
        					<NombreInstitucion>""" + invoice.nombre_institucion_pf[:100] + """</NombreInstitucion>
        					<FechaEmision>""" + parse(invoice.fecha_emision_pf).strftime('%Y-%m-%dT%H:%M:%S') + """</FechaEmision>
        					<MontoImpuesto>""" + str(l.price_subtotal * (old_tax.amount / 100)) + """</MontoImpuesto>
        					<PorcentajeCompra>""" + str(int(line_tax.porc_auth)) + """</PorcentajeCompra>
        				</Exoneracion>
                        """
            if len(l.invoice_line_tax_ids):
                if not l.invoice_line_tax_ids[0].tax_code.code:
                    raise UserError("Hace falta configurar el código a los impuestos.")
                else:
                    impuesto = """<Impuesto>
                                    <Codigo>""" + str(l.invoice_line_tax_ids[0].tax_code.code) + """</Codigo>
                                    <CodigoTarifa>08</CodigoTarifa>
                                    <Tarifa>""" + str(l.invoice_line_tax_ids[0].amount) + """</Tarifa>
                                    <Monto>""" + str(l.tax_amount) + """</Monto>""" + exoneracion + \
                               """</Impuesto>"""
            monto_descuento = 0
            descuento = ""
            if int(l.discount) > 0:
                monto_descuento = round((l.price_unit * (l.discount or 0.0) / 100.0) * l.quantity, 2)
                descuento = """<MontoDescuento>""" + str(monto_descuento) + """</MontoDescuento>
                        <NaturalezaDescuento>Descuento de ventas</NaturalezaDescuento>"""
            imp = l.invoice_line_tax_ids
            restar_imp = 0
            if len(imp) > 0:
                if imp[0].price_include:
                    restar_imp = imp.compute_all(l.price_unit, l.invoice_id.currency_id, 1, False,
                                                 l.invoice_id.partner_id)['taxes'][0].get('amount', 0)

            monto_total = (l.price_unit - restar_imp) * l.quantity
            subtotal = monto_total - monto_descuento
            return """
                        <LineaDetalle>
                            <NumeroLinea>""" + str(cont_linea) + """</NumeroLinea>
                            <Codigo>""" + str(codigo_producto)[:20] + """</Codigo>
                            <Cantidad>""" + str(l.quantity) + """</Cantidad>
                            <UnidadMedida>""" + str(l.uom_id.code) + """</UnidadMedida>
                            <UnidadMedidaComercial>""" + str(l.uom_id.name)[:20] + """</UnidadMedidaComercial>
                            <Detalle>""" + l.name[:160] + """</Detalle>
                            <PrecioUnitario>""" + str(l.price_unit - restar_imp) + """</PrecioUnitario>
                            <MontoTotal>""" + str(monto_total) + """</MontoTotal>
                            """ + descuento + """
                            <SubTotal>""" + str(subtotal) + """</SubTotal>""" + impuesto + """
                            <MontoTotalLinea>""" + str(subtotal + l.tax_amount) + """</MontoTotalLinea>
                        </LineaDetalle>
                    """

        lineasFactura = " ".join(map(crearLinea, invoice.invoice_line_ids))

        if not company_partner.identification_id.code:
            raise UserError("Configure el código de la cédula de la compañia")

        if not partner.identification_id.code:
            raise UserError("Configure el código de la cédula del cliente.")
        self.validar_datos(company_partner)
        plantilla = """<Clave>""" + clave + """</Clave>
                      <CodigoActividad>722003</CodigoActividad>
                      <NumeroConsecutivo>""" + numeroConsecutivo + """</NumeroConsecutivo>
                      <FechaEmision>""" + fecha_actual + """</FechaEmision>
                      <Emisor>
                        <Nombre>""" + str(company_partner.name or "")[:80] + """</Nombre>
                        <Identificacion>
                          <Tipo>""" + str(company_partner.identification_id.code or "01") + """</Tipo>
                          <Numero>""" + str(company_partner.ref or "") + """</Numero>
                        </Identificacion>
                        <NombreComercial>""" + str(company_partner.commercial_name or company_partner.name)[
                                               :80] + """</NombreComercial>"""
        plantilla += """<Ubicacion>
                          <Provincia>""" + str(company_partner.state_id.code or "") + """</Provincia>
                          <Canton>""" + str(company_partner.county_id.code or "") + """</Canton>
                          <Distrito>""" + str(company_partner.district_id.code or "") + """</Distrito>
                          <Barrio>""" + str(company_partner.neighborhood_id.code or "") + """</Barrio>
                          <OtrasSenas>""" + str(company_partner.street or "") + """</OtrasSenas>
                        </Ubicacion>"""
        if company_partner.phone:
            phone = re.sub("""(\-|\s|\+|506)""", '', company_partner.phone)
            plantilla += """<Telefono>
                      <CodigoPais>506</CodigoPais>
                      <NumTelefono>""" + str(phone or "")[:20] + """</NumTelefono>
                    </Telefono>"""
        if company_partner.mobile:
            mobile = re.sub("""(\-|\s|\+|506)""", '', company_partner.mobile)
            plantilla += """<Fax>
                          <CodigoPais>506</CodigoPais>
                          <NumTelefono>""" + str(mobile or "")[:20] + """</NumTelefono>
                    </Fax>"""
        plantilla += """<CorreoElectronico>""" + str(company_partner.email or "") + """</CorreoElectronico>"""
        plantilla += """</Emisor>"""

        identificacion = ''
        if not partner.cliente_generico:
            if partner.identification_id and partner.ref:
                self.validar_datos(partner)
            else:
                raise UserError("Debe completar el tipo de documento y la cédula del cliente")

            if partner.identification_id.code == '05':
                identificacion = """<IdentificacionExtranjero>""" + str(partner.ref).zfill(20)[
                                                                    :20] + """</IdentificacionExtranjero>"""
            else:
                if not str(partner.ref).isdigit():
                    raise UserError("Cedula incorrecta")

                identificacion = """
                        <Identificacion>
                              <Tipo>""" + str(partner.identification_id.code or "01") + """</Tipo>
                              <Numero>""" + str(partner.ref or "") + """</Numero>
                        </Identificacion>
                        """

            plantilla += """
                      <Receptor>
                        <Nombre>""" + str(partner.name or "")[:80] + """</Nombre>
                        """ + identificacion + """
                        <NombreComercial>""" + str(partner.commercial_name or partner.name)[
                                               :80] + """</NombreComercial>"""

            if partner.identification_id.code in ('01', '02'):
                if partner.country_id and partner.state_id and partner.county_id and partner.district_id and partner.neighborhood_id:
                    if partner.country_id.name == "Costa Rica":
                        plantilla += """<Ubicacion>
                                  <Provincia>""" + partner.state_id.code + """</Provincia>"""
                        if partner.county_id:
                            plantilla += """<Canton>""" + partner.county_id.code + """</Canton>"""
                        if partner.district_id:
                            plantilla += """<Distrito>""" + partner.district_id.code + """</Distrito>"""
                        if partner.neighborhood_id:
                            plantilla += """<Barrio>""" + partner.neighborhood_id.code + """</Barrio>"""

                        plantilla += """<OtrasSenas>""" + str((partner.street or "No indica"))[
                                                          :160] + """</OtrasSenas>"""
                        plantilla += """</Ubicacion>"""
                if partner.phone:
                    phone = re.sub("""(\-|\s|\+|506)""", '', partner.phone)
                    plantilla += """<Telefono>
                              <CodigoPais>""" + (partner.phone_code or '506')[:3] + """</CodigoPais>
                              <NumTelefono>""" + str(phone or "")[:20] + """</NumTelefono>
                            </Telefono>"""
                if partner.mobile:
                    mobile = re.sub("""(\-|\s|\+|506)""", '', partner.mobile)
                    plantilla += """<Fax>
                              <CodigoPais>""" + (partner.fax_code or '506')[:3] + """</CodigoPais>
                              <NumTelefono>""" + str(mobile or "")[:20] + """</NumTelefono>
                            </Fax>"""
            correo = False
            if partner.correo_envio_fe:
                correo = partner.correo_envio_fe
            elif partner.email:
                correo = partner.email

            if correo:
                if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", correo.lower()):
                    raise UserError("Error en el correo del cliente")

                plantilla += """<CorreoElectronico>""" + str(correo or "") + """</CorreoElectronico>"""
            plantilla += """</Receptor>"""
        payment_term_id = invoice.payment_term_id
        if not payment_term_id:
            raise UserError("Debe definir un plazo de pago")

        if not payment_term_id.sale_conditions_id:
            raise UserError("Debe definir una condicion para el plazo de pago")

        if not len(payment_term_id.line_ids.ids):
            raise UserError("Debe configurar los dias para el plazo de pago")

        plantilla += """
                  <CondicionVenta>""" + (payment_term_id.sale_conditions_id.sequence or '01') + """</CondicionVenta>
                  <PlazoCredito>""" + str(payment_term_id.line_ids[0].days) + """</PlazoCredito>
                  <MedioPago>""" + (invoice.payment_methods_id.sequence or '01') + """</MedioPago>
                  <DetalleServicio>
                    """ + lineasFactura + """
                  </DetalleServicio>
                  <ResumenFactura>
                    <CodigoTipoMoneda>
                        <CodigoMoneda>""" + resumen['moneda'] + """</CodigoMoneda>
                        <TipoCambio>""" + str(resumen['tipo_cambio']) + """</TipoCambio>
                    </CodigoTipoMoneda>
                    <TotalServGravados>""" + str(resumen['totalserviciogravado']) + """</TotalServGravados>
                    <TotalServExentos>""" + str(resumen['totalservicioexento']) + """</TotalServExentos>"""

        if self.tipo_doc != "facturaVentaExportacion":
            plantilla += """<TotalServExonerado>0.00000</TotalServExonerado>"""

        plantilla += """<TotalMercanciasGravadas>""" + str(resumen['totalmercaderiagravado']) + """</TotalMercanciasGravadas>
                    <TotalMercanciasExentas>""" + str(
            resumen['totalmercaderiaexento']) + """</TotalMercanciasExentas>"""

        if self.tipo_doc != "facturaVentaExportacion":
            plantilla += """<TotalMercExonerada>0.00000</TotalMercExonerada>"""

        plantilla += """<TotalGravado>""" + str(resumen['totalgravado']) + """</TotalGravado>
                    <TotalExento>""" + str(resumen['totalexento']) + """</TotalExento>"""

        if self.tipo_doc != "facturaVentaExportacion":
            plantilla += """<TotalExonerado>0.00000</TotalExonerado>"""

        plantilla += """<TotalVenta>""" + str(resumen['totalventa']) + """</TotalVenta>
                    <TotalDescuentos>""" + str(resumen['totaldescuentos']) + """</TotalDescuentos>
                    <TotalVentaNeta>""" + str(resumen['totalventaneta']) + """</TotalVentaNeta>
                    <TotalImpuesto>""" + str(resumen['totalimpuestos']) + """</TotalImpuesto>
                    <TotalOtrosCargos>0.00000</TotalOtrosCargos>
                    <TotalComprobante>""" + str(resumen['totalcomprobante']) + """</TotalComprobante>
                  </ResumenFactura>"""

        plantilla += self.get_informacion_extra()

        return plantilla

    def generar_respuesta_xml(self):

        doc = """<?xml version="1.0" encoding="UTF-8"?>"""

        doc += cabeceras[self.tipo_doc]

        clave, numeroConsecutivo = self.generarClaveFactura()
        resumen = self.resumen

        doc += """
          <Clave>""" + resumen['numero_documento'] + """</Clave>
          <NumeroCedulaEmisor>""" + resumen['numero_cedula_emisor'] + """</NumeroCedulaEmisor>
          <FechaEmisionDoc>""" + resumen['fecha_emision_doc'] + """</FechaEmisionDoc>
          <Mensaje>""" + resumen['mensaje'] + """</Mensaje>
          <DetalleMensaje>""" + resumen['detalle_mensaje'] + """</DetalleMensaje>
          <MontoTotalImpuesto>""" + str(resumen['monto_total_impuesto']) + """</MontoTotalImpuesto>
          <TotalFactura>""" + str(resumen['total_factura']) + """</TotalFactura>
          <NumeroCedulaReceptor>""" + resumen['numero_cedula_receptor'] + """</NumeroCedulaReceptor>
          <NumeroConsecutivoReceptor>""" + numeroConsecutivo + """</NumeroConsecutivoReceptor>
        """

        doc += cierres[self.tipo_doc]

        return doc

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
