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

    "tiquete": """<TiqueteElectronico
        xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.3/tiqueteElectronico"
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

    "tiquete": """</TiqueteElectronico>""",

    "facturaCompra": """</FacturaElectronicaCompra>""",

    "notaCredito": """</NotaCreditoElectronica>""",

    "notaDebito": """</NotaDebitoElectronica>""",

    "mensaje": """</MensajeReceptor>""",
}

class DocumentoXml:

    def __init__(self, invoice, type_doc, fecha, resumen):
        self.invoice = invoice
        _logger.info('type_doc=%s'%(type_doc,))
        if type_doc not in cabeceras.keys():
            raise UserError(("Tipo de documento no existe."))
        self.tipo_doc = type_doc
        self.fecha = fecha
        self.resumen = resumen

    def getConsecutivo(self):
        invoice = self.invoice
        sucursal = (invoice.journal_id.sucursal or "001").zfill(3)
        punto_de_venta = (invoice.journal_id.terminal or "00001").zfill(5)
        tipo_doc = {
            'in_invoice': '00',          # Vendor Bill
            'out_invoice': '01',        # Customer Invoice
            'out_refund': '03',        # Customer Refund
            'in_refund': '00',          # Vendor Refund
        }
        tipo = tipo_doc[invoice.type]
        if tipo == '00':
            if not invoice.xml_supplier_approval:
                tipo = '08'
                self.validar_datos(invoice.partner_id)
            else:
                tipo = invoice.state_invoice_partner

        if tipo == '01':
            if invoice.journal_id.exportacion:
                tipo = '09'
            else:
                if invoice.partner_id.identification_id.code=="05" or invoice.partner_id.cliente_generico:
                    tipo = '04'
                elif self.tipo_doc == "notaDebito":
                    tipo = '02'
        return sucursal + punto_de_venta + tipo + invoice.number.zfill(10)#str(int(random.random() *123123)).zfill(10)

    def get_Clave(self):
        return self.clave

    def generarClaveFactura(self):
        clave = "506"
        fecha = self.fecha
        invoice = self.invoice
        clave_existente = invoice.clave_envio_hacienda
        if clave_existente:
            return (clave_existente, clave_existente[21:41])
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
            if False: #not self.invoice.refund_invoice_id and self.invoice.name:
                return """
                    <InformacionReferencia>
                    <TipoDoc>09</TipoDoc>
                    <Numero>""" + self.invoice.name + """</Numero>
                    <FechaEmision>2015-12-16T15:22:23</FechaEmision>
                    <Codigo>03</Codigo>
                    <Razon>Rebajo consignación por devolucion</Razon>
                    </InformacionReferencia>
                """
            return ""
        types = {
            'out_invoice': '01',
            'out_refund': '02',
            'in_refund': '03'
        }

        clave = last_invoice.clave_envio_hacienda or last_invoice.number
        fecha_anulacion = (parse(last_invoice.fecha_envio_hacienda or last_invoice.validate_date) - timedelta(hours=6)).strftime('%Y-%m-%dT%H:%M:%S')

        template = """
            <InformacionReferencia>
            <TipoDoc>""" + types[last_invoice.type] + """</TipoDoc>
            <Numero>""" + clave + """</Numero>
            <FechaEmision>""" + fecha_anulacion + """</FechaEmision>
            <Codigo>""" + '01' + """</Codigo>
            <Razon>""" + (self.invoice and self.invoice.name or 'Error')[:180] + """</Razon>
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

        posicion_fiscal = invoice.fiscal_position_id or False

        def crearLinea(l, numLinea):  # Crea las lineas de las facturas
            tipo_codigo_producto = l.product_id and l.product_id.code_type_id.code or "04"
            #codigo_producto = l.product_id and (l.product_id.default_code or l.product_id.barcode) or "Sin código"

            codigo_producto = l.product_id.x_codigo_cabys #l.product_id and (l.product_id.default_code or l.product_id.barcode) or "Sin código"
            if not codigo_producto:
                raise UserError(_("Hace falta el código cabys en la linea %s." % (l.name,)))
            else:
                codigo_producto = codigo_producto.zfill(13)

            if not l.uom_id:
                raise UserError(_("Hace falta definir un la unidad de medida."))
            if not l.uom_id.code:
                raise UserError(_("Hace falta definir un código a la unidad de medida."))
            exoneracion = ""
            impuesto = ""
            impuesto_neto = 0
            line_tax = False
            old_tax = False
            impuesto_anterior = 0
            
            if posicion_fiscal:
                old_tax = l.product_id.taxes_id
                if old_tax:
                    old_tax = old_tax
                else:
                    return ""
                line_tax = posicion_fiscal.tax_ids.filtered(lambda t: t.tax_src_id.id == old_tax.id)
                if not line_tax:
                    raise UserError("No se ha encontrado el impuesto sustituto.")
                if int(line_tax.porc_auth) == 0:
                    raise UserError("Debe especificar el monto a exonerar en la ficha de la posición fiscal.")

                imp_viejo = l.price_subtotal * (old_tax.amount / 100)
                impuesto_neto = imp_viejo
                impuesto_neto -= (impuesto_neto / 100.00) * line_tax.porc_auth

                impuesto_anterior = imp_viejo - impuesto_neto
                exoneracion = """<Exoneracion>
        					<TipoDocumento>""" + invoice.tipo_documento_pf + """</TipoDocumento>
        					<NumeroDocumento>""" + invoice.numero_documento_pf[:17] + """</NumeroDocumento>
        					<NombreInstitucion>""" + invoice.nombre_institucion_pf[:100] + """</NombreInstitucion>
        					<FechaEmision>""" + parse(invoice.fecha_emision_pf).strftime('%Y-%m-%dT00:00:00') + """</FechaEmision>
        					<PorcentajeExoneracion>""" + str(line_tax.porc_auth) + """</PorcentajeExoneracion>
        					<MontoExoneracion>""" + str(round(impuesto_anterior, 2)) + """</MontoExoneracion>
        				</Exoneracion>
                        """
            
            restar_imp = 0
            imp = l.invoice_line_tax_ids
            impuesto_neto = 0
            
            if len(imp):
                #imp = imp[0]
                if float(l.discount) > 0.00 and int(l.discount) != 100:
                    precio = l.price_subtotal / l.quantity
                    if len(imp) == 1 and imp[0].price_include:
                        precio = l.price_unit - (l.price_unit * (l.discount/100))
                else:
                    precio = l.price_unit
                imp_calculados = imp.compute_all(precio, l.invoice_id.currency_id, l.quantity, False, l.invoice_id.partner_id)['taxes']
                calc_impuestos = {}
                for i in imp_calculados:
                    calc_impuestos[i['id']] = i
            
            for tax_obj in imp:
                #tax_obj = imp[0]
                if not tax_obj.tax_code.code:
                    raise UserError("Hace falta configurar el código a los impuestos.")
                #elif not tax_obj.cod_tarifa:
                #    raise UserError("El impuesto debe tener una tarifa asignada.")
                else:
                    tarifa = tax_obj.amount
                    monto_impuesto = l.tax_amount
                    _logger.info("l.invoice_line_tax_ids: %s " % (l.invoice_line_tax_ids,))
                    
                    if posicion_fiscal:
                        tax_obj = old_tax
                        if l.invoice_line_tax_ids:
                            imp_linea = posicion_fiscal.tax_ids.filtered(lambda t: t.tax_src_id.id == old_tax.id)
                            if imp_linea:
                                imp_viejo = imp_linea.tax_src_id
                                imp_linea = imp_linea.tax_dest_id
                                impuesto_neto += imp_linea.compute_all(precio, l.invoice_id.currency_id, l.quantity, False, l.invoice_id.partner_id)['taxes'][0]['amount']
                                imp_linea = imp_viejo.compute_all(precio, l.invoice_id.currency_id, l.quantity, False, l.invoice_id.partner_id)['taxes'][0]['amount']
                    elif l.invoice_line_tax_ids:
                        imp_linea = calc_impuestos[tax_obj.id]['amount']
                        impuesto_neto += imp_linea
                    impuesto += """<Impuesto>
                                    <Codigo>""" + str(tax_obj.tax_code.code) + """</Codigo>"""
                    if tax_obj.cod_tarifa:
                        impuesto += """<CodigoTarifa>""" + str(tax_obj.cod_tarifa) + """</CodigoTarifa>"""

                    impuesto += """<Tarifa>""" + str(tax_obj.amount) + """</Tarifa>
                                    <Monto>""" + str(imp_linea) + """</Monto>""" + exoneracion + \
                               """</Impuesto>"""
                if tax_obj.price_include:
                    restar_imp += imp.compute_all(l.price_unit, l.invoice_id.currency_id, 1, False,
                                                 l.invoice_id.partner_id)['taxes'][0].get('amount', 0)

            monto_descuento = 0
            descuento = ""
            if float(l.discount) > 0.00:
                total_venta = round(l.price_unit * l.quantity, 2)  # venta total
                restar_imp_total = restar_imp * l.quantity
                total_venta -= restar_imp_total
                monto_descuento = round( total_venta * ((l.discount or 0.0) / 100.0), 2)
                if int(l.discount) == 100:
                    monto_descuento = round((l.price_unit - restar_imp) * l.quantity, 2)
                descuento = """<Descuento><MontoDescuento>""" + str(monto_descuento) + """</MontoDescuento>
                        <NaturalezaDescuento>Descuento de ventas</NaturalezaDescuento></Descuento>"""

            monto_total = round((l.price_unit - restar_imp) * l.quantity,2)

            subtotal = monto_total - monto_descuento
            if subtotal < 0:
                subtotal = 0
            imp_neto = ""
            if posicion_fiscal:
                impuesto_neto = round(impuesto_neto - impuesto_anterior, 2)
                if impuesto_neto >= 0:
                    imp_neto = """<ImpuestoNeto>""" + str(impuesto_neto) + """</ImpuestoNeto>"""
                else:
                    impuesto_neto = 0
                    imp_neto = """<ImpuestoNeto>""" + str(impuesto_neto) + """</ImpuestoNeto>"""

            if impuesto_neto > 0:
                resumen['totalimpuestos'] += impuesto_neto

            return """
                        <LineaDetalle>
                            <NumeroLinea>""" + str(numLinea) + """</NumeroLinea>
                            <Codigo>""" + str(codigo_producto)[:13] + """</Codigo>
                            <Cantidad>""" + str(l.quantity) + """</Cantidad>
                            <UnidadMedida>""" + str(l.uom_id.code) + """</UnidadMedida>
                            <UnidadMedidaComercial>""" + str(l.uom_id.name)[:20] + """</UnidadMedidaComercial>
                            <Detalle>""" + l.name[:160].replace('<', '').replace('>', '') + """</Detalle>
                            <PrecioUnitario>""" + str(l.price_unit - restar_imp) + """</PrecioUnitario>
                            <MontoTotal>""" + str(monto_total) + """</MontoTotal>
                            """ + descuento + """
                            <SubTotal>""" + str(subtotal) + """</SubTotal>"""\
                            + impuesto \
                            + imp_neto \
                            + """<MontoTotalLinea>""" + str( round(round(subtotal, 2)+ round(impuesto_neto, 2), 2) ) + """</MontoTotalLinea>
                        </LineaDetalle>
                    """

        lineasFactura = " "
        contLinea = 1
        for linea in invoice.invoice_line_ids:
            lineasFactura += crearLinea(linea, contLinea)
            contLinea = contLinea + 1

        if not company_partner.identification_id.code:
            raise UserError("Configure el código de la cédula de la compañia")

        if not partner.identification_id.code:
            raise UserError("Configure el código de la cédula del cliente.")
        self.validar_datos(company_partner)
        plantilla = """<Clave>""" + clave + """</Clave>
                      <CodigoActividad>""" + str(invoice.actividad_id.code).zfill(6) + """</CodigoActividad>
                      <NumeroConsecutivo>""" + numeroConsecutivo + """</NumeroConsecutivo>
                      <FechaEmision>""" + fecha_actual + """</FechaEmision>
                      <Emisor>
                        <Nombre>""" + str(company_partner.name or "")[:80] + """</Nombre>
                        <Identificacion>
                          <Tipo>""" + str(company_partner.identification_id.code or "01") + """</Tipo>
                          <Numero>""" + str(company_partner.ref or "") + """</Numero>
                        </Identificacion>
                        <NombreComercial>""" + str(company_partner.commercial_name or company_partner.name)[:80] + """</NombreComercial>"""
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
                identificacion = """<IdentificacionExtranjero>"""\
                                 + str(partner.ref).zfill(20)[:20] + """</IdentificacionExtranjero>"""
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
        else:
            plantilla += """<Receptor>
                        <Nombre>""" + str(partner.name or "")[:80] + """</Nombre>
                        </Receptor>
                        """
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
            plantilla += """<TotalServExonerado>""" + str(resumen['totalservicioexonerado']) + """</TotalServExonerado>"""

        plantilla += """<TotalMercanciasGravadas>""" + str(resumen['totalmercaderiagravado']) + """</TotalMercanciasGravadas>
                    <TotalMercanciasExentas>""" + str(resumen['totalmercaderiaexento']) + """</TotalMercanciasExentas>"""

        if self.tipo_doc != "facturaVentaExportacion":
            plantilla += """<TotalMercExonerada>""" + str(resumen['totalmercaderiaexonerado']) + """</TotalMercExonerada>"""

        plantilla += """<TotalGravado>""" + str(resumen['totalgravado']) + """</TotalGravado>
                    <TotalExento>""" + str(resumen['totalexento']) + """</TotalExento>"""

        if self.tipo_doc != "facturaVentaExportacion":
            plantilla += """<TotalExonerado>""" + str(resumen['totalexonerado']) + """</TotalExonerado>"""

        plantilla += """<TotalVenta>""" + str(resumen['totalventa']) + """</TotalVenta>
                    <TotalDescuentos>""" + str(resumen['totaldescuentos']) + """</TotalDescuentos>
                    <TotalVentaNeta>""" + str(resumen['totalventaneta']) + """</TotalVentaNeta>
                    <TotalImpuesto>""" + str(resumen['totalimpuestos']) + """</TotalImpuesto>
                    <TotalOtrosCargos>0.00000</TotalOtrosCargos>
                    <TotalComprobante>""" + str(resumen['totalcomprobante'] + resumen['totalimpuestos']) + """</TotalComprobante>
                  </ResumenFactura>"""

        plantilla += self.get_informacion_extra()

        return plantilla

    def generar_respuesta_xml(self):

        doc = """<?xml version="1.0" encoding="UTF-8"?>"""

        doc += cabeceras[self.tipo_doc]

        clave, numeroConsecutivo = self.generarClaveFactura()
        self.clave = clave
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
