# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
import random
from dateutil.parser import parse
from datetime import timedelta
from odoo import _

cabeceras = {
    "tiquete": """<TiqueteElectronico 
        xmlns="https://tribunet.hacienda.go.cr/docs/esquemas/2016/v4.2/tiqueteElectronico" 
        xmlns:ds="http://www.w3.org/2000/09/xmldsig#"  
        xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="https://tribunet.hacienda.go.cr/docs/esquemas/2016/v4.2/tiqueteElectronico https://tribunet.hacienda.go.cr/docs/esquemas/2016/v4.2/tiqueteElectronico.xsd">""",
}

cierres = {
    "tiquete": """</TiqueteElectronico>""",
}

class DocumentoXml:

    def __init__(self, invoice, type_doc, fecha, resumen):
        self.invoice = invoice
        if type_doc not in cabeceras.keys():
            raise UserError(("Tipo de documento no existe."))
        self.tipo_doc = type_doc
        self.fecha = fecha
        self.resumen = resumen

    def getConsecutivo(self):
        invoice = self.invoice
        sucursal = (invoice.user_id.sucursal or "001").zfill(3)
        punto_de_venta = (invoice.user_id.punto_de_venta or "00001").zfill(5)
        tipo_doc = {
            'in_invoice': '00',          # Vendor Bill
            'out_invoice': '01',        # Customer Invoice
            'out_refund': '03',        # Customer Refund
            'in_refund': '00',          # Vendor Refund
        }
        tipo = tipo_doc[invoice.type]
        if tipo == '00':
            tipo = invoice.state_invoice_partner
        return sucursal + punto_de_venta + tipo + invoice.number.zfill(10)#str(int(random.random() *123123)).zfill(10)

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
        clave += str(int(random.random() *123123)).zfill(8)
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

        template = """
          <InformacionReferencia>
            <TipoDoc>""" + types[last_invoice.type] + """</TipoDoc>
            <Numero>""" + last_invoice.clave_envio_hacienda + """</Numero>
            <FechaEmision>""" + (parse(last_invoice.fecha_envio_hacienda) - timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S') + """</FechaEmision>
            <Codigo>""" + self.invoice.reference_code_id.code + """</Codigo>
            <Razon>""" + (self.invoice.name or 'Error')[:180] + """</Razon>
          </InformacionReferencia>
        """
        return template

    def generate_xml(self):

        doc = """<?xml version="1.0" encoding="UTF-8"?>"""
        doc += cabeceras[self.tipo_doc]

        clave, numeroConsecutivo = self.generarClaveFactura()
        self.clave = clave
        doc += self.devolverPlantilla(clave, numeroConsecutivo)

        doc += cierres[self.tipo_doc]
        return doc

    def devolverPlantilla(self, clave, numeroConsecutivo):
        """
            a=506 --> codigo pais
            b=17  --> dia
            c=01  -->  mes
            d=18  -->año
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
        #----------------------------- 2018-04-25T15:22:18.020
        #----------------------------- 25-04-2018 22:50:08
        resumen = self.resumen
        tipo_doc = self.tipo_doc
        fecha = self.fecha

        invoice = self.invoice

        fecha_actual = fecha.strftime('%Y-%m-%dT%H:%M:%S')
        partner = invoice.partner_id
        company_partner = invoice.company_id.partner_id
        global cont_linea
        cont_linea = 0
        posicion_fiscal = invoice.fiscal_position_id or False
        def crearLinea(l):#Crea las lineas de las facturas
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
                exoneracion = """<Exoneracion>
					<TipoDocumento>""" + invoice.tipo_documento_pf + """</TipoDocumento>
					<NumeroDocumento>""" + invoice.numero_documento_pf[:17] + """</NumeroDocumento>
					<NombreInstitucion>""" + invoice.nombre_institucion_pf[:100] + """</NombreInstitucion>
					<FechaEmision>""" + parse(invoice.fecha_emision_pf).strftime('%Y-%m-%dT%H:%M:%S') + """</FechaEmision>
					<MontoImpuesto>""" + str(l.price_subtotal * (old_tax.amount/100)) + """</MontoImpuesto>
					<PorcentajeCompra>""" + str(int(line_tax.porc_auth)) + """</PorcentajeCompra>
				</Exoneracion>
                """
            if len(l.invoice_line_tax_ids):
                if not l.invoice_line_tax_ids[0].tax_code.code:
                    raise UserError("Hace falta configurar el código a los impuestos.")
                else:
                    impuesto = """<Impuesto>
                            <Codigo>""" + str(l.invoice_line_tax_ids[0].tax_code.code) + """</Codigo>
                            <Tarifa>""" + str(l.invoice_line_tax_ids[0].amount) + """</Tarifa>
                            <Monto>""" + str(l.tax_amount)+"""</Monto>""" + exoneracion + \
                    """</Impuesto>"""
            descuento = ""
            if int(l.discount) > 0:
                descuento = """<MontoDescuento>""" + str((l.price_unit *  (l.discount or 0.0) / 100.0) * l.quantity) + """</MontoDescuento>
                <NaturalezaDescuento>Descuento de ventas</NaturalezaDescuento>"""
            return """
                <LineaDetalle>
                    <NumeroLinea>""" + str(cont_linea) + """</NumeroLinea>
                    <Codigo>
                        <Tipo>""" + str(tipo_codigo_producto) + """</Tipo>
                        <Codigo>""" + str(codigo_producto)[:20] + """</Codigo>
                    </Codigo>
                    <Cantidad>""" + str(l.quantity) + """</Cantidad>
                    <UnidadMedida>""" + str(l.uom_id.code) + """</UnidadMedida>
                    <UnidadMedidaComercial>""" + str(l.uom_id.name)[:20] + """</UnidadMedidaComercial>
                    <Detalle>""" + l.name[:160] + """</Detalle>
                    <PrecioUnitario>""" + str(l.price_unit) + """</PrecioUnitario>
                    <MontoTotal>""" + str(l.price_unit*l.quantity) + """</MontoTotal>
                    """ + descuento + """
                    <SubTotal>""" + str(l.price_subtotal) + """</SubTotal>""" + impuesto + """
                    <MontoTotalLinea>""" + str(l.price_subtotal + l.tax_amount) + """</MontoTotalLinea>
                </LineaDetalle>
            """
        lineasFactura = " ".join(map(crearLinea, invoice.invoice_line_ids))

        if not company_partner.identification_id.code:
            raise UserError("Configure el código de la cédula de la compañia")

        if not partner.identification_id.code:
            raise UserError("Configure el código de la cédula del cliente.")

        plantilla = """<Clave>""" + clave + """</Clave>
              <NumeroConsecutivo>""" + numeroConsecutivo + """</NumeroConsecutivo>
              <FechaEmision>""" + fecha_actual + """</FechaEmision>
              <Emisor>
                <Nombre>""" + str(company_partner.name or "")[:80]+"""</Nombre>
                <Identificacion>
                  <Tipo>""" + str(company_partner.identification_id.code or "01") + """</Tipo>
                  <Numero>""" + str(company_partner.ref or "") + """</Numero>
                </Identificacion>
                <NombreComercial>""" + str(company_partner.commercial_name or company_partner.name)[:80] + """</NombreComercial>
                <Ubicacion>
                  <Provincia>"""+ str(company_partner.state_id.code or "")+"""</Provincia>
                  <Canton>"""+ str(company_partner.county_id.code or "")+"""</Canton>
                  <Distrito>"""+ str(company_partner.district_id.code or "")+"""</Distrito>
                  <Barrio>"""+ str(company_partner.neighborhood_id.code or "")+"""</Barrio>
                  <OtrasSenas>"""+ str(company_partner.street or "")+"""</OtrasSenas>
                </Ubicacion>"""
        if company_partner.phone:
            plantilla += """<Telefono>
              <CodigoPais>506</CodigoPais>
              <NumTelefono>"""+ str(company_partner.phone or "")+"""</NumTelefono>
            </Telefono>"""
        if company_partner.mobile:
            plantilla += """<Fax>
                  <CodigoPais>506</CodigoPais>
                  <NumTelefono>"""+ str(company_partner.mobile or "")+"""</NumTelefono>
            </Fax>"""
        identificacion = ''
        if partner.identification_id.code == '05':
            identificacion = """<IdentificacionExtranjero>"""+ str(partner.ref)[:20]+"""</IdentificacionExtranjero>"""
        else:
            identificacion = """<IdentificacionExtranjero>""" + str(partner.ref)[:20] + """</IdentificacionExtranjero>"""
        plantilla += """<CorreoElectronico>""" + str(company_partner.email or "")+ """</CorreoElectronico>
          </Emisor>
          <Receptor>
            <Nombre>"""+ str(partner.name or "")[:80]+"""</Nombre>
            <Identificacion>
                  <Tipo>"""+ str(partner.identification_id.code or "01")+"""</Tipo>
                  <Numero>"""+ str(partner.ref or "")+"""</Numero>
            </Identificacion>
            <NombreComercial>"""+ str(partner.commercial_name or partner.name)[:80]+"""</NombreComercial>"""

        if partner.state_id:
            plantilla += """<Ubicacion>
              <Provincia>""" + partner.state_id.code + """</Provincia>"""
            if partner.county_id:
                plantilla += """<Canton>""" + partner.county_id.code + """</Canton>"""
            if partner.district_id:
                plantilla += """<Distrito>""" + partner.district_id.code + """</Distrito>"""
            if partner.neighborhood_id:
                plantilla += """<Barrio>"""+ partner.neighborhood_id.code+"""</Barrio>"""
            if partner.street:
                plantilla += """<OtrasSenas>"""+ partner.street[:160]+"""</OtrasSenas>"""
            plantilla += """</Ubicacion>"""

        if partner.phone:
            plantilla += """<Telefono>
              <CodigoPais>""" + (partner.phone_code or '506') + """</CodigoPais>
              <NumTelefono>"""+ str(partner.phone or "")+"""</NumTelefono>
            </Telefono>"""
        if partner.mobile:
            plantilla += """<Fax>
              <CodigoPais>""" + (partner.fax_code or '506') + """</CodigoPais>
              <NumTelefono>"""+ str(partner.mobile or "")+"""</NumTelefono>
            </Fax>"""
        if partner.email:
            plantilla += """<CorreoElectronico>""" + str(partner.email or "")+ """</CorreoElectronico>"""

        plantilla += """</Receptor>
          <CondicionVenta>""" + (invoice.payment_term_id.sale_conditions_id.sequence or '01') + """</CondicionVenta>
          <PlazoCredito>""" + str(invoice.payment_term_id.line_ids[0].days) + """</PlazoCredito>
          <MedioPago>""" + (invoice.payment_methods_id.sequence or '01') + """</MedioPago>
          <DetalleServicio>
            """+ lineasFactura +"""
          </DetalleServicio>
          <ResumenFactura>
            <CodigoMoneda>""" + resumen['moneda'] + """</CodigoMoneda>
            <TipoCambio>""" + str(resumen['tipo_cambio']) + """</TipoCambio>
            <TotalServGravados>""" + str(resumen['totalserviciogravado']) + """</TotalServGravados>
            <TotalServExentos>""" + str(resumen['totalservicioexento']) + """</TotalServExentos>
            <TotalMercanciasGravadas>""" + str(resumen['totalmercaderiagravado']) + """</TotalMercanciasGravadas>
            <TotalMercanciasExentas>""" + str(resumen['totalmercaderiaexento']) + """</TotalMercanciasExentas>
            <TotalGravado>""" + str(resumen['totalgravado']) + """</TotalGravado>
            <TotalExento>""" + str(resumen['totalexento']) + """</TotalExento>
            <TotalVenta>""" + str(resumen['totalventa']) + """</TotalVenta>
            <TotalDescuentos>""" + str(resumen['totaldescuentos']) + """</TotalDescuentos>
            <TotalVentaNeta>""" + str(resumen['totalventaneta']) + """</TotalVentaNeta>
            <TotalImpuesto>""" + str(resumen['totalimpuestos']) + """</TotalImpuesto>
            <TotalComprobante>""" + str(resumen['totalcomprobante']) + """</TotalComprobante>
          </ResumenFactura>"""

        plantilla += self.get_informacion_extra() + """
          <Normativa>
            <NumeroResolucion>DGT-R-48-2016</NumeroResolucion>
            <FechaResolucion>07-10-2016 08:00:00</FechaResolucion>
          </Normativa>

        """

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
          <MontoTotalImpuesto>""" + resumen['monto_total_impuesto'] + """</MontoTotalImpuesto>
          <TotalFactura>""" + resumen['total_factura'] + """</TotalFactura>
          <NumeroCedulaReceptor>""" + resumen['numero_cedula_receptor'] + """</NumeroCedulaReceptor>
          <NumeroConsecutivoReceptor>""" + numeroConsecutivo + """</NumeroConsecutivoReceptor>
        """

        doc += cierres[self.tipo_doc]

        return doc




# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
