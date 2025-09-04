# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
import random
from dateutil.parser import parse
from datetime import timedelta, datetime
from odoo import _, models, fields
import re, logging
import phonenumbers
from babel.dates import get_timezone, format_datetime as format_dt

_logger = logging.getLogger(__name__)
DEFAULT_FACTURA_CR_DATETIME_FORMAT = '%Y-%m-%dT%H:%m:%s-06:00'

def format_datetime(env, dt, tz='UTC', dt_format=DEFAULT_FACTURA_CR_DATETIME_FORMAT):
    # Format the date in the CR standard.
    dt = dt or datetime.now()
    if dt and isinstance(dt, str):
        dt = parse(dt)
    now = format_dt(
        dt, format='Y-MM-ddTH:mm:s-06:00',
        tzinfo=get_timezone('America/Costa_Rica'), locale='es_CR'
    )

    return now

class InvoiceXMLGenerator:
    """
    Clase para generar XML de facturas electrónicas de Costa Rica
    Reemplaza las plantillas QWeb por métodos Python
    """

    def __init__(self, values):
        """
        Inicializa el generador con los valores de _prepare_invoice_values()

        Args:
            values: Diccionario con las variables generadas por _prepare_invoice_values()
        """
        self.FEC = False
        self.record = values['record']
        self.o = values['o']
        self.format_date = values['format_date']
        self.format_datetime = values['format_datetime']
        self.parse_phone = values['parse_phone']
        self.parse_email = values['parse_email']
        self.round_fe = values['round_fe']
        self.round_currency = values['round_currency']
        self.refund_type_doc = values['refund_type_doc']
        self.convert2datetime = values['convert2datetime']
        self.invoice_lines = values['invoice_lines']
        self.clave = self.generarClaveFactura()


    def getConsecutivo(self):
        invoice = self.record
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
        return sucursal + punto_de_venta + tipo + invoice.number.zfill(10)#str(int(random.random() *123123)).zfill(10)

    def get_clave(self):
        return self.clave

    def generarClaveFactura(self):
        clave = "506"
        invoice = self.record
        fecha = parse(self.record.date_invoice or fields.Date.context_today(self))
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

    # --- Helpers v4.4 (ZF únicamente emite <Exoneracion>) ---
    def _is_zf(self):
        """True si corresponde tratar la factura como Zona Franca."""
        t = str(getattr(self.o, 'tipo_documento_pf', '') or '').strip()
        return t in ('05', '08')  # 05 (legacy) y 08 (ZF en v4.4)

    def _tipo_documento_ex_v44(self):
        """Mapea 05 -> 08 al emitir el XML v4.4."""
        t = str(getattr(self.o, 'tipo_documento_pf', '') or '').strip()
        return '08' if t == '05' else (t or '08')

    def account_invoice_cr_partner_phone(self, tel):
        """Genera información de teléfono"""
        if tel:
            return """
            <Telefono>
                <CodigoPais>{}</CodigoPais>
                <NumTelefono>{}</NumTelefono>
            </Telefono>""".format(tel['phone_code'], tel['phone_number'])
        return ""

    def account_invoice_cr_partner_email(self, emails):
        """Genera información de emails"""
        if emails:
            email_xml = ""
            for email in emails[:4]:  # Máximo 4 correos
                email_xml += "<CorreoElectronico>{}</CorreoElectronico>\n".format(email)
            return email_xml
        return ""

    def account_invoice_cr_partner_body(self, partner, receptor=False):
        """Genera el cuerpo de información del partner"""
        xml = "<Nombre>{}</Nombre>\n".format(partner.name[:99].replace('&', '&amp;'))

        # Identificación normal
        if partner.identification_id and partner.ref and partner.identification_id.code != '05':
            xml += """
            <Identificacion>
                <Tipo>{}</Tipo>
                <Numero>{}</Numero>
            </Identificacion>""".format(partner.identification_id.code, partner.ref)

        # Identificación extranjero
        if partner.identification_id and partner.ref and partner.identification_id.code == '05':
            xml += "<IdentificacionExtranjero>{}</IdentificacionExtranjero>\n".format(partner.ref)

        # Nombre comercial
        if partner.commercial_name:
            xml += "<NombreComercial>{}</NombreComercial>\n".format(partner.commercial_name.replace('&', '&amp;'))

        # Ubicación
        if partner.state_id and partner.county_id and partner.district_id and partner.neighborhood_id:
            xml += """
            <Ubicacion>
                <Provincia>{}</Provincia>
                <Canton>{}</Canton>
                <Distrito>{}</Distrito>
                <OtrasSenas>{}</OtrasSenas>
            </Ubicacion>""".format(
                partner.state_id.code,
                partner.county_id.code.zfill(2),
                partner.district_id.code.zfill(2),
                (partner.street or 'No Especificado').replace('&', '&amp;')
            )

        # Teléfono - equivale a t-call="account_invoice_cr_partner_phone"
        tel = self.parse_phone(partner.phone)
        xml += self.account_invoice_cr_partner_phone(tel)

        # Email - equivale a t-call="account_invoice_cr_partner_email" (solo si no es receptor)
        if not receptor:
            emails = self.parse_email(partner.email)
            xml += self.account_invoice_cr_partner_email(emails)

        return xml

    def account_invoice_cr_partner(self, partner_type):
        """Genera Emisor o Receptor según el tipo"""
        if partner_type == 'company':
            # Emisor - equivale a t-call="account_invoice_cr_partner_body" con partner company
            if self.FEC:
                partner = self.o.partner_id
            else:
                partner = self.o.company_id.partner_id
            receptor = False
            return """
            <Emisor>
                {}
            </Emisor>""".format(self.account_invoice_cr_partner_body(partner, receptor))
        else:
            # Receptor - solo si no es ticket
            if not self.o.check_if_ticket():
                if self.FEC:
                    partner = self.o.company_id.partner_id
                else:
                    partner = self.o.partner_id
                receptor = True
                return """
                <Receptor>
                    {}
                </Receptor>""".format(self.account_invoice_cr_partner_body(partner, receptor))
        return ""

    def account_invoice_cr_FE_tax_template(self, tax):
        """Genera template de impuestos"""
        cod_tarifa = ""
        if tax.get('cod_tarifa', False):
            cod_tarifa = "<CodigoTarifaIVA>{}</CodigoTarifaIVA>".format(tax['cod_tarifa'])
        return """
        <Codigo>{}</Codigo>
        {}
        <Tarifa>{}</Tarifa>
        <Monto>{}</Monto>""".format(
            tax['tax_code'],
            cod_tarifa,
            self.round_fe(tax['rate']),
            self.round_currency(tax['amount'])
        )

    def account_invoice_cr_FE_tax_line(self, taxes_data):
        """Genera líneas de impuestos"""
        xml = ""
        # ¿Aplica exoneración? Solo si: hay posición fiscal + exoneración válida + NO cliente_exento + es ZF
        exo_enabled = (
                bool(self.o.fiscal_position_id) and
                bool(getattr(self.o, "exoneration_id", False)) and
                not getattr(self.o.exoneration_id, "cliente_exento", False) and
                self._is_zf()
        )

        for tax in taxes_data:
            xml += """
            <Impuesto>
                {}
            """.format(self.account_invoice_cr_FE_tax_template(tax))

            if tax['exoneration']:
                exoneration = tax['exoneration']
                xml += """
                <Exoneracion>
                    <TipoDocumentoEX1>{}</TipoDocumentoEX1>
                    <NumeroDocumento>{}</NumeroDocumento>""".format(
                    exoneration['tipo_documento'],
                    exoneration['numero_documento']
                )

                # Artículo/Inciso obligatorios para 02,03,06,07,08 si existen en el registro
                if exoneration.get('articulo', False):
                    xml += """
                    <Articulo>{}</Articulo>
                    <Inciso>{}</Inciso>
                    """.format(exoneration['articulo'], exoneration['inciso'])

                xml += """
                    <NombreInstitucion>{}</NombreInstitucion>
                    <FechaEmisionEX>{}</FechaEmisionEX>
                    <TarifaExonerada>{}</TarifaExonerada>
                    <MontoExoneracion>{}</MontoExoneracion>
                </Exoneracion>""".format(
                    exoneration['nombre_institucion'],
                    self.format_datetime(self.convert2datetime(exoneration['fecha_emision']), tz='UTC',
                                         dt_format="yyyy-MM-dd'T'HH:mm:ss-06:00"),
                    exoneration['tarifa_exoneracion'],
                    exoneration['monto_exoneracion']
                )

            xml += "</Impuesto>"
        return xml

    def account_invoice_terms_condition(self, date_due=None, payment_term=None):
        """Genera condiciones de venta"""
        if payment_term:
            if payment_term.sale_conditions_id:
                return """
                <CondicionVenta>{}</CondicionVenta>
                <PlazoCredito>{}</PlazoCredito>""".format(
                    payment_term.sale_conditions_id.sequence,
                    payment_term.line_ids[0].days
                )
            else:
                return """
                <CondicionVenta>01</CondicionVenta>
                <PlazoCredito>0</PlazoCredito>"""
        else:
            if date_due:
                term_days = self.o.get_term_days()
                if term_days > 0:
                    return """
                    <CondicionVenta>02</CondicionVenta>
                    <PlazoCredito>{}</PlazoCredito>""".format(term_days)
                else:
                    return """
                    <CondicionVenta>01</CondicionVenta>
                    <PlazoCredito>0</PlazoCredito>"""
            else:
                return """
                <CondicionVenta>01</CondicionVenta>
                <PlazoCredito>0</PlazoCredito>"""

    def account_invoice_cr_FE_line(self, l, line_counter):
        """Genera líneas de detalle de factura"""
        xml = """
        <LineaDetalle>
            <NumeroLinea>{}</NumeroLinea>
            <CodigoCABYS>{}</CodigoCABYS>
            <CodigoComercial>
                <Tipo>01</Tipo>
                <Codigo>{}</Codigo>
            </CodigoComercial>
            <Cantidad>{}</Cantidad>""".format(
            line_counter,
            l['codigo'],
            (l['obj_linea'].product_id.default_code or l['codigo'])[:20],
            l['cantidad']
        )

        # Unidad de medida
        if l['obj_linea'].product_id.type == 'service':
            xml += "<UnidadMedida>Sp</UnidadMedida>"
        else:
            xml += "<UnidadMedida>{}</UnidadMedida>".format(l['unidad_medida'])

        xml += """
            <UnidadMedidaComercial>{}</UnidadMedidaComercial>
            <Detalle>{}</Detalle>
            <PrecioUnitario>{}</PrecioUnitario>
            <MontoTotal>{}</MontoTotal>""".format(
            l['unidad_medida'],
            l['detalle'][:199].replace('&', '&amp;'),
            self.round_fe(l['precio_unitario']),
            self.round_fe(l['monto_total'])
        )

        # Descuento
        if l['monto_descuento'] > 0:
            xml += """
            <Descuento>
                <MontoDescuento>{}</MontoDescuento>
                <CodigoDescuento>07</CodigoDescuento>
                <NaturalezaDescuento>Acuerdos comerciales</NaturalezaDescuento>
            </Descuento>""".format(self.round_fe(l['monto_descuento']))

        subtotal = l['sub_total']
        imp_asumido = ""
        if not self.FEC:
            # # en caso de aplicarse una exoneración se
            # # calculará como la resta entre el Monto del Impuesto menos el
            # # Monto Exonerado
            # monto_imp_asumido = l['impuesto_neto'] - l['impuesto_exonerado']
            # imp_asumido = "<ImpuestoAsumidoEmisorFabrica>{}</ImpuestoAsumidoEmisorFabrica>".format(monto_imp_asumido)
            imp_asumido = "<ImpuestoAsumidoEmisorFabrica>0</ImpuestoAsumidoEmisorFabrica>"
            pass  # TODO CHECK

        inv_line = l['obj_linea']
        # base_line = inv_line.move_id._prepare_product_base_line_for_taxes_computation(inv_line)
        # self.o.env['account.tax']._add_tax_details_in_base_line(base_line, inv_line.company_id)
        # taxes_data = base_line['tax_details']['taxes']

        base_imponible_adicionales = 0.0
        # for t in taxes_data:
        #     if t['tax'].tax_code in ['02', '04', '05', '12']:
        #         base_imponible_adicionales += t['raw_tax_amount']
        # TODO: puede ser que se necesite para ISC

        xml += """
            <SubTotal>{}</SubTotal>
            <BaseImponible>{}</BaseImponible>
            {}
            {}
            <ImpuestoNeto>{}</ImpuestoNeto>
            <MontoTotalLinea>{}</MontoTotalLinea>
        </LineaDetalle>""".format(
            self.round_fe(subtotal),
            self.round_fe(l['base_imponible']),
            self.account_invoice_cr_FE_tax_line(l['impuestos']),
            imp_asumido,
            self.round_fe(l['impuesto_neto']),
            self.round_fe(l['monto_total_linea'])
        )

        return xml

    def get_all_taxes(self, lines):
        all_taxes = {}
        for l in lines:
            for tax in l['impuestos']:
                if tax['tax_code'] not in all_taxes:
                    all_taxes[tax['tax_code']] = {
                        'code': tax['tax_code'],
                        'rate': tax.get('cod_tarifa', False),
                        'amount': 0.0,
                    }
                all_taxes[tax['tax_code']]['amount'] += tax['amount']
                all_taxes[tax['tax_code']]['amount'] -= tax.get('exoneration', {}).get('monto_exoneracion', 0)
        return all_taxes.values()


    def generate_resumen_factura(self):
        """Genera el resumen de factura"""
        # Inicializar totales
        t_serv_gravados = t_serv_exentos = t_serv_exonerados = t_serv_no_sujetos = 0
        t_merc_gravados = t_merc_exentos = t_merc_exonerados = t_merc_no_sujetos = 0
        t_gravados = t_exentos = t_exonerados = t_no_sujetos = 0
        t_descuentos = t_impuesto = 0

        # Calcular totales por cada línea
        for l in self.invoice_lines:
            # Verificar si es servicio
            if l['obj_linea'].product_id.type == 'service' and int(l['obj_linea'].product_id.codigo_cabys) < 5:
                raise UserError(
                    _("El código CABYS {} es inválido para un servicio. Los códigos CABYS para servicios deben comenzar con 5, 6, 7, 8 o 9.").format(
                        l['obj_linea'].product_id.codigo_cabys))

            if l['obj_linea'].product_id.type == 'service' or l['obj_linea'].uom_id.code == 'Sp':
                t_serv_gravados += l['monto_gravado']
                t_serv_exentos += l['monto_exento']
                t_serv_exonerados += l['monto_exonerado']
                t_serv_no_sujetos += l['monto_no_sujeto']
            else:
                t_merc_gravados += l['monto_gravado']
                t_merc_exentos += l['monto_exento']
                t_merc_exonerados += l['monto_exonerado']
                t_merc_no_sujetos += l['monto_no_sujeto']

            t_gravados += l['monto_gravado']
            t_exentos += l['monto_exento']
            t_exonerados += l['monto_exonerado']
            t_no_sujetos += l['monto_no_sujeto']

            t_descuentos += l['monto_descuento']
            t_impuesto += l['impuesto_neto']

        # Generar desglose de impuestos
        # TODO: use self.invoice_lines to get all taxes applied
        all_taxes = self.get_all_taxes(self.invoice_lines)
        taxes_xml = ""
        for tax_detail in all_taxes:
            cod_tarifa = "<CodigoTarifaIVA>{}</CodigoTarifaIVA>".format(tax_detail['rate']) if tax_detail[
                'rate'] else ""
            taxes_xml += """
            <TotalDesgloseImpuesto>
                <Codigo>{}</Codigo>
                {}
                <TotalMontoImpuesto>{}</TotalMontoImpuesto>
            </TotalDesgloseImpuesto>""".format(
                tax_detail['code'],
                cod_tarifa,
                self.round_currency(tax_detail['amount'])
            )

        total_comprobante = self.round_fe(
            ((t_gravados + t_exentos + t_exonerados + t_no_sujetos) - t_descuentos) + t_impuesto)
        medio_pago = ""
        if not self.FEC:
            medio_pago = """<MedioPago>
                <TipoMedioPago>{}</TipoMedioPago>
                <TotalMedioPago>{}</TotalMedioPago>
            </MedioPago>""".format(self.o.payment_methods_id.sequence, total_comprobante)
        return """
        <ResumenFactura>
            <CodigoTipoMoneda>
                <CodigoMoneda>{}</CodigoMoneda>
                <TipoCambio>{}</TipoCambio>
            </CodigoTipoMoneda>
            <TotalServGravados>{}</TotalServGravados>
            <TotalServExentos>{}</TotalServExentos>
            <TotalServExonerado>{}</TotalServExonerado>
            <TotalServNoSujeto>{}</TotalServNoSujeto>
            <TotalMercanciasGravadas>{}</TotalMercanciasGravadas>
            <TotalMercanciasExentas>{}</TotalMercanciasExentas>
            <TotalMercExonerada>{}</TotalMercExonerada>
            <TotalMercNoSujeta>{}</TotalMercNoSujeta>
            <TotalGravado>{}</TotalGravado>
            <TotalExento>{}</TotalExento>
            <TotalExonerado>{}</TotalExonerado>
            <TotalNoSujeto>{}</TotalNoSujeto>
            <TotalVenta>{}</TotalVenta>
            <TotalDescuentos>{}</TotalDescuentos>
            <TotalVentaNeta>{}</TotalVentaNeta>
            {}
            <TotalImpuesto>{}</TotalImpuesto>
            <TotalOtrosCargos>0</TotalOtrosCargos>
            {}
            <TotalComprobante>{}</TotalComprobante>
        </ResumenFactura>""".format(
            self.o.currency_id.name,
            round(1/self.o.currency_id.rate, 2),
            self.round_fe(t_serv_gravados),
            self.round_fe(t_serv_exentos),
            self.round_fe(t_serv_exonerados),
            self.round_fe(t_serv_no_sujetos),
            self.round_fe(t_merc_gravados),
            self.round_fe(t_merc_exentos),
            self.round_fe(t_merc_exonerados),
            self.round_fe(t_merc_no_sujetos),
            self.round_fe(t_gravados),
            self.round_fe(t_exentos),
            self.round_fe(t_exonerados),
            self.round_fe(t_no_sujetos),
            self.round_fe(t_gravados + t_exentos + t_exonerados + t_no_sujetos),
            self.round_fe(t_descuentos),
            self.round_fe((t_gravados + t_exentos + t_exonerados + t_no_sujetos) - t_descuentos),
            taxes_xml,
            self.round_fe(t_impuesto),
            medio_pago,
            total_comprobante
        )

    def account_invoice_cr_FE_body(self):
        """Genera el cuerpo principal de la factura"""
        if self.FEC:
            if self.o.receiver_activity_id:
                actividad_receptor = "<CodigoActividadEmisor>{}</CodigoActividadEmisor>".format(
                    self.o.receiver_activity_id.code)
            else:
                actividad_receptor = ""
            actividad_emisor = "<CodigoActividadReceptor>{}</CodigoActividadReceptor>".format(self.o.actividad_id.code)
        else:
            actividad_emisor = "<CodigoActividadEmisor>{}</CodigoActividadEmisor>".format(self.o.actividad_id.code)
            if self.o.receiver_activity_id:
                actividad_receptor = "<CodigoActividadReceptor>{}</CodigoActividadReceptor>".format(
                    self.o.receiver_activity_id.code)
            else:
                actividad_receptor = ""

        xml = """
        <Clave>{}</Clave>
        <ProveedorSistemas>{}</ProveedorSistemas>
        {}
        {}
        <NumeroConsecutivo>{}</NumeroConsecutivo>
        <FechaEmision>{}</FechaEmision>
        {}
        {}
        {}
        <DetalleServicio>""".format(
            self.o.clave_envio_hacienda,
            self.o.company_id.cod_proveedor_fe or '3102830739',
            actividad_emisor,
            actividad_receptor,
            self.record.clave_envio_hacienda[21:41],
            self.format_datetime(self.o.fecha_envio_hacienda, tz='UTC', dt_format="yyyy-MM-dd'T'HH:mm:ss-06:00"),
            self.account_invoice_cr_partner('company'),
            self.account_invoice_cr_partner('customer'),
            self.account_invoice_terms_condition(self.o.date_due, self.o.payment_term_id)
        )

        # Generar líneas de factura
        line_counter = 1
        for l in self.invoice_lines:
            xml += self.account_invoice_cr_FE_line(l, line_counter)
            line_counter += 1

        xml += "</DetalleServicio>"

        # Generar resumen
        xml += self.generate_resumen_factura()

        # Información de referencia para notas de crédito
        if self.o.type == 'out_refund':
            xml += """
            <InformacionReferencia>
                <TipoDocIR>{}</TipoDocIR>
                <Numero>{}</Numero>
                <FechaEmisionIR>{}</FechaEmisionIR>
                <Codigo>{}</Codigo>
                <Razon>{}</Razon>
            </InformacionReferencia>""".format(
                self.refund_type_doc,
                self.o.invoice_id and self.o.invoice_id.clave_envio_hacienda or self.o.invoice_id.name or self.o.ref,
                self.format_datetime(self.convert2datetime(self.o.issue_date), tz='UTC',
                                     dt_format="yyyy-MM-dd'T'HH:mm:ss"),
                self.o.reference_code_id.code,
                self.o.refund_reason
            )

        return xml

    def generate_mensaje_receptor(self):
        """Genera el XML para Mensaje Receptor"""
        body = """
            <Clave>{}</Clave>
            <NumeroCedulaEmisor>{}</NumeroCedulaEmisor>
            <FechaEmisionDoc>{}</FechaEmisionDoc>
            <Mensaje>{}</Mensaje>

            {}
            {}
            <Mensaje>{}</Mensaje>
            <DetalleMensaje>{}</DetalleMensaje>
            <Estado>{}</Estado>
            <CondicionImpuesto>{}</CondicionImpuesto>
        """.format(
            self.o.clave_envio_hacienda,
            self.o.clave_envio_hacienda[21:41],
            self.format_datetime(self.o.fecha_envio_hacienda, tz='UTC', dt_format="yyyy-MM-dd'T'HH:mm:ss"),
            self.format_datetime(self.o.fecha_envio_hacienda, tz='UTC', dt_format="yyyy-MM-dd'T'HH:mm:ss"),
            self.account_invoice_cr_partner('company'),
            self.account_invoice_cr_partner('customer'),
            self.o.mensaje_receptor[:300],
            self.o.detalle_mensaje_receptor[:300],
            self.o.estado_mensaje_receptor or '01',
            self.o.condicion_impuesto_mensaje_receptor or '01'
        )
        return body

    def account_invoice_cr_FE(self):
        """Template principal que decide el tipo de documento y genera el XML completo"""

        body = self.account_invoice_cr_FE_body()

        if self.o.type == 'out_invoice':
            if self.o.journal_id.exportacion:
                return """<FacturaElectronicaExportacion xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaExportacion"
                                                        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                                        xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                                                        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                                        {}
                                    </FacturaElectronicaExportacion>""".format(body)
            else:
                if self.o.check_if_ticket():
                    return """<TiqueteElectronico xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/tiqueteElectronico"
                                        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                        xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                                        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                        {}
                    </TiqueteElectronico>""".format(body)
                else:
                    return """<FacturaElectronica xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
                                        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                        xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                                        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                        {}
                    </FacturaElectronica>""".format(body)
        elif self.o.type == 'out_refund':
            return """<NotaCreditoElectronica xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/notaCreditoElectronica"
                    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                {}
            </NotaCreditoElectronica>""".format(body)
        elif self.o.type == 'in_invoice':
            self.FEC = True
            body = self.account_invoice_cr_FE_body()
            return """<FacturaElectronicaCompra xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronicaCompra"
                                xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
                                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                            {}
                        </FacturaElectronicaCompra>""".format(body)

        return ""

    def generate_xml(self):
        """
        Método principal para generar el XML completo de la factura
        Equivale a la plantilla principal account_invoice_cr_FE

        Returns:
            str: XML completo de la factura electrónica
        """
        return self.account_invoice_cr_FE()


class Invoice(models.Model):
    _inherit = 'account.invoice'

    def _prepare_invoice_values(self):
        self.ensure_one()

        def format_date(dt):
            # Format the date in the CR standard.
            dt = dt or datetime.now()
            return dt.strftime(DEFAULT_FACTURA_CR_DATETIME_FORMAT)

        # Create file content.
        types4refund = {
            'out_refund': '01',
            'out_invoice': '02',
            'in_refund': '03'
        }

        decimal_places = self.env['decimal.precision'].sudo().search([('name', '=', 'Product Price')], limit=1).digits
        redondear = lambda value: round(value, decimal_places)
        redondear_currency = lambda value: round(self.currency_id.round(value), self.currency_id.decimal_places)

        def parse_phone(phone):
            if not phone:
                return False
            if phone:
                try:
                    new_phone = phonenumbers.parse(phone, "CR")
                except:
                    return False
                return {
                    'phone_code': new_phone.country_code,
                    'phone_number': str(new_phone.national_number)[:20]
                }
            return False

        porc_exoneracion = 0
        if self.exoneration_id:
            porc_exoneracion = self.exoneration_id.percentage

        def parse_email(email):
            if not email:
                return []
            emails = [e.strip() for e in email.split(',')]
            emails += [e.strip() for e in email.split(' ')]
            emails += [e.strip() for e in email.split(';')]
            new_emails = []
            for e in emails:
                if not re.match("^\s*\w+([-+.']\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*\s*$", e):
                    continue
                if len(e) > 160:
                    continue
                if e not in new_emails:
                    new_emails.append(e)
            return new_emails[:1]

        def generate_line_values(lines):
            new_lines = []
            for idx, line in enumerate(lines):

                precio_unitario = line.price_unit

                monto_total = redondear_currency(line.quantity * line.price_unit)

                discount = redondear_currency(monto_total * (line.discount / 100))
                iva_cobrado_fabricante = 0
                base_imponible = 0
                subtotal = 0
                monto_gravado = 0
                monto_exento = 0
                monto_exonerado = 0
                monto_no_sujeto = 0

                class TaxInfo:
                    def __init__(self, tax, line_tax_amount, exoneration={}):
                        self.tax = tax
                        self.exoneration = exoneration
                        self.amount = line_tax_amount

                    def to_dict(self):
                        exoneration = {}
                        exento = False
                        no_sujeto = False
                        if self.exoneration:
                            exoneration_obj = self.exoneration['exoneration']  # customer.exoneration
                            if exoneration_obj.cliente_exento or exoneration_obj.no_sujeto:
                                exoneration = False
                                if exoneration_obj.cliente_exento:
                                    exento = True
                                elif exoneration_obj.no_sujeto:
                                    no_sujeto = True
                            else:
                                exoneration = {
                                    'tipo_documento': exoneration_obj.ttype,
                                    'numero_documento': exoneration_obj.name,
                                    'nombre_institucion': exoneration_obj.institution_id.code or '01',
                                    'fecha_emision': exoneration_obj.date or fields.Date.today(),
                                    'tarifa_exoneracion': self.exoneration.get('rate', 0),
                                    'monto_exoneracion': redondear_currency(self.exoneration['amount']) or 0,
                                }
                                if exoneration_obj.ttype in ['02', '03', '06', '07', '08']:
                                    exoneration.update({
                                        'articulo': exoneration_obj.article or '0',
                                        'inciso': exoneration_obj.subsection or '0',
                                    })
                        return {
                            'tax_code': self.tax.tax_code.code or '01',
                            'cod_tarifa': self.tax.cod_tarifa,
                            'rate': self.tax.amount,
                            'exoneration': exoneration,
                            'exento': exento,
                            'no_sujeto': no_sujeto,
                            'amount': redondear_currency(self.amount) or 0,
                        }

                impuestos = []

                def get_total_tax_amount(taxes, details=False):
                    result = taxes.compute_all(precio_unitario * ((100 - line.discount) / 100), self.currency_id,
                                               line.quantity)
                    return result

                line_tax_amount = 0
                product_taxes = []
                if self.exoneration_id:
                    # get the original tax of the product without exoneration which is the one matching in the fiscal position
                    fiscal_position = self.fiscal_position_id
                    product_tax = line.product_id.taxes_id[0] if line.product_id.taxes_id else self.env['account.tax']

                    line_taxes = fiscal_position.tax_ids.filtered(lambda lt: lt.tax_src_id.id == product_tax.id)
                    if line_taxes:
                        for t in line.invoice_line_tax_ids:
                            no_sujeto = self.exoneration_id.no_sujeto
                            if not no_sujeto:
                                t = line_taxes.tax_src_id
                            tax_amount_details = get_total_tax_amount(t)
                            # product_taxes.append(TaxInfo(t, line_tax_amount))
                            total_tax_included = tax_amount_details['total_included']
                            total_tax_excluded = tax_amount_details['total_excluded']
                            base_imponible = redondear_currency(tax_amount_details['total_included'])
                            subtotal = redondear_currency(tax_amount_details['total_excluded'])
                            line_tax_amount = redondear_currency(total_tax_included - total_tax_excluded)
                            if no_sujeto:
                                amount = redondear_currency((base_imponible * (product_tax.amount / 100)) - (
                                            base_imponible * (porc_exoneracion / 100)))
                                monto_no_sujeto = monto_total
                            else:
                                amount = redondear_currency(base_imponible * (porc_exoneracion / 100))
                                monto_exonerado = monto_total / t.amount * porc_exoneracion
                                monto_gravado = monto_total - monto_exonerado
                            product_taxes = [TaxInfo(t, line_tax_amount, {
                                'exoneration': self.exoneration_id,
                                'rate': porc_exoneracion,
                                'amount': amount
                            })]
                    else:
                        product_taxes = []

                    taxes = line.invoice_line_tax_ids
                    if not taxes:
                        monto_no_sujeto = monto_total
                else:
                    tax_amount_details = get_total_tax_amount(line.invoice_line_tax_ids, True)
                    base_imponible = redondear_currency(tax_amount_details['total_included'])
                    subtotal = redondear_currency(tax_amount_details['total_excluded'])
                    taxes = line.invoice_line_tax_ids
                    if taxes:
                        monto_gravado = monto_total
                        for t in taxes:
                            line_tax_amount = list(filter(lambda x: x['id'] == t.id, tax_amount_details['taxes']))[0][
                                'amount']
                            product_taxes.append(TaxInfo(t, line_tax_amount))
                    else:
                        monto_no_sujeto = monto_total

                for tax in product_taxes:
                    result = tax.to_dict()

                    if result['tax_code'] == '01':
                        iva_cobrado_fabricante = 0  # redondear_currency((base_imponible * tax.amount) / (1 + tax.amount))
                    tax_amount = redondear_currency(base_imponible * tax.amount)

                    impuestos.append(result)

                impuesto_neto = 0
                for t in impuestos:
                    impuesto_neto += t['amount'] - (t['exoneration'] and t['exoneration']['monto_exoneracion'] or 0)

                subtotal_final = redondear_currency(subtotal)
                base_imponible_final = redondear_currency(base_imponible)

                new_lines.append(dict(
                    obj_linea=line,

                    codigo=line.product_id.codigo_cabys[:13],
                    cantidad=line.quantity,
                    unidad_medida=line.uom_id.code,
                    detalle=line.name or line.product_id.name,

                    precio_unitario=redondear(precio_unitario),
                    monto_total=monto_total,
                    monto_descuento=redondear(discount),
                    sub_total=subtotal_final,
                    base_imponible=base_imponible_final,
                    impuestos=impuestos,
                    impuesto_neto=redondear(impuesto_neto),
                    monto_total_linea=redondear(subtotal_final + impuesto_neto + iva_cobrado_fabricante),
                    monto_gravado=redondear(monto_gravado),
                    monto_exento=redondear(monto_exento),
                    monto_exonerado=redondear(monto_exonerado),
                    monto_no_sujeto=redondear(monto_no_sujeto)
                ))
            return new_lines

        template_values = {
            'record': self,
            'format_date': format_date,
            'o': self,

            'format_datetime': lambda value, tz, dt_format: format_datetime(self.env, value, tz, dt_format),
            'parse_phone': parse_phone,
            'parse_email': parse_email,
            'round_fe': redondear,
            'round_currency': redondear_currency,
            'refund_type_doc': types4refund.get(self.type or 'out_refund', '01'),
            'convert2datetime': lambda value: fields.Datetime.from_string(str(value)),
            'invoice_lines': generate_line_values(
                self.invoice_line_ids),
        }
        return template_values

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
