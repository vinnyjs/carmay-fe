# -*- coding: utf-8 -*-
# © 2015 Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


from odoo import api, fields, models, _
from odoo.exceptions import Warning
from odoo.addons.report_xlsx.report.report_xlsx import ReportXlsx
from datetime import datetime
from dateutil.parser import parse

class ReporteAccountInvoice(models.Model):
    _name = 'reporte.account.invoice'

    date_start = fields.Date('Fecha Inicial', required=True)
    date_end = fields.Date('Fecha Fin', required=True)

    @api.multi
    def print_report(self):
        if parse(self.date_start) > parse(self.date_end):
            raise Warning('Fecha inicial no puede ser mayor a la final')
        action = self.env['report'].get_action(False, 'reportes_facturas.report_account_invoice_report.xlsx')
        return action


class ReportAccountInvoiceParser(ReportXlsx):

    def get_num(self, val):
        num = ""
        begin_num = False
        fin = False
        for i in val:
            if i.isdigit() and not fin:
                begin_num = True
                num += i
            else:
                if begin_num:
                    fin = True
                    break
        try:
            num = int( num )
        except:
            pass

        return num



    def split_presentacion(self, val):
        new_val = []
        splited = val.split('+')

        new_val.append(self.get_num(splited[0]))

        if len(splited) == 1:
            new_val.append(0)
        else:
            new_val.append(self.get_num(splited[1]))
            
        return new_val

    global select
    select = """WITH currency_rate as ( SELECT
        r.currency_id,
        COALESCE(r.company_id, c.id) as company_id,
        r.rate,
        r.name AS date_start,
        (SELECT name FROM res_currency_rate r2
            WHERE r2.name > r.name AND
                r2.currency_id = r.currency_id AND
                (r2.company_id is null or r2.company_id = c.id)
            ORDER BY r2.name ASC
            LIMIT 1) AS date_end
    FROM res_currency_rate r
    JOIN res_company c ON (r.company_id is null or r.company_id = c.id) )
    SELECT 
    rp.ref as cedula, 
    rp.name as nombre_cliente, 
    CASE 
        WHEN (ai.type = 'out_invoice') 
            THEN 'Factura Cliente' 
        WHEN (ai.type = 'out_refund') 
            THEN 'NC Cliente' 
        WHEN (ai.type = 'in_invoice') 
            THEN 'Factura Proveedor' 
        WHEN (ai.type = 'in_refund') 
            THEN 'NC Proveedor' 
        ELSE '-' 
    END AS tipo_factura, 
    ai.number as numero,
    ai.reference as referencia,
    ai.date_invoice as fecha_factura,
    pt.name as nombre_producto,
    ail.name as descripcion,
    ail.quantity as cantidad,
    ail.price_unit as precio_unitario,
    aa.name as nombre_cuenta,
    rc.name as moneda,
    rc.id as id_moneda,
    cr.rate as tipo_cambio,
    CASE 
        WHEN (ai.currency_id != 40) 
            THEN 1/cr.rate
        ELSE 1
    END AS tasa,
    ail.price_subtotal as monto_gravado,
    ail.tax_amount as total_impuesto,
    (ail.price_subtotal + ail.tax_amount) as total,
    ail.discount::varchar || '%' as descuento,
    (SELECT array_to_string( ARRAY(select at.amount::varchar||'%' from account_invoice_line_tax ailt left join account_tax at on at.id=ailt.tax_id where ailt.invoice_line_id =ail.id), ', ')) as impuestos,
    CASE 
        WHEN (ai.state = 'open') 
            THEN 'Abierto/Pendiente Pago' 
        WHEN (ai.state = 'draft') 
            THEN 'Borrador' 
        WHEN (ai.state = 'paid') 
            THEN 'Pagado' 
        WHEN (ai.state = 'cancel') 
            THEN 'Cancelado' 
        ELSE '-' 
    END AS estado_factura, 
    rp.phone as telefono,
    rp.email as correo,
    CASE 
        WHEN (ai.status_hacienda = 'generado') 
            THEN 'Generado' 
        WHEN (ai.status_hacienda = 'aceptado') 
            THEN 'Aceptado' 
        WHEN (ai.status_hacienda = 'procesando') 
            THEN 'Procesando' 
        WHEN (ai.status_hacienda = 'rechazado') 
            THEN 'Rechazado' 
        ELSE '-' 
    END AS estado_hacienda,
    ai.fecha_envio_hacienda 
    from account_invoice_line ail 
    left join account_invoice ai on ai.id=ail.invoice_id 
    left join res_partner rp on ai.partner_id=rp.id 
    left join product_product pp on pp.id=ail.product_id 
    left join product_template pt on pt.id=pp.product_tmpl_id 
    left join account_account aa on aa.id=ail.account_id 
    left join res_currency rc on rc.id=ai.currency_id 
    left join currency_rate cr on (cr.currency_id = 3 and
                            cr.date_start <= coalesce(   TO_TIMESTAMP(ai.date_invoice::varchar || ' 06:00:00', 'YYYY/MM/DD HH24:MI:SS'), now()) and
                            (cr.date_end is null or cr.date_end > coalesce(TO_TIMESTAMP(ai.date_invoice::varchar || ' 06:00:00', 'YYYY/MM/DD HH24:MI:SS'), now())))

    where ai.state in ('open', 'paid')
    """
    global select2
    select2 = """WITH currency_rate as ( SELECT
        r.currency_id,
        COALESCE(r.company_id, c.id) as company_id,
        r.rate,
        r.name AS date_start,
        (SELECT name FROM res_currency_rate r2
            WHERE r2.name > r.name AND
                r2.currency_id = r.currency_id AND
                (r2.company_id is null or r2.company_id = c.id)
            ORDER BY r2.name ASC
            LIMIT 1) AS date_end
    FROM res_currency_rate r
    JOIN res_company c ON (r.company_id is null or r.company_id = c.id) )
    SELECT 
    rp.ref as cedula, 
    rp.name as nombre_cliente, 
    CASE 
        WHEN (ai.type = 'out_invoice') 
            THEN 'Factura Cliente' 
        WHEN (ai.type = 'out_refund') 
            THEN 'NC Cliente' 
        WHEN (ai.type = 'in_invoice') 
            THEN 'Factura Proveedor' 
        WHEN (ai.type = 'in_refund') 
            THEN 'NC Proveedor' 
        ELSE '-' 
    END AS tipo_factura, 
    (SELECT array_to_string( ARRAY(select at.amount::varchar||'%' from account_invoice_tax ait left join account_tax at on at.id=ait.tax_id where ait.invoice_id =ai.id), ', ')) as impuestos,
    ai.number as numero,
    ai.reference as referencia,
    ai.date_invoice as fecha_factura,
    rc.name as moneda,
    rc.id as id_moneda,
    cr.rate as tipo_cambio,
    CASE 
        WHEN (ai.currency_id != 40) 
            THEN 1/cr.rate
        ELSE 1
    END AS tasa,
    ai.amount_untaxed as monto_gravado,
    ai.amount_tax as total_impuesto,
    ai.amount_total as total,
    CASE 
        WHEN (ai.state = 'open') 
            THEN 'Abierto/Pendiente Pago' 
        WHEN (ai.state = 'draft') 
            THEN 'Borrador' 
        WHEN (ai.state = 'paid') 
            THEN 'Pagado' 
        WHEN (ai.state = 'cancel') 
            THEN 'Cancelado' 
        ELSE '-' 
    END AS estado_factura, 
    rp.phone as telefono,
    rp.email as correo,
    CASE 
        WHEN (ai.status_hacienda = 'generado') 
            THEN 'Generado' 
        WHEN (ai.status_hacienda = 'aceptado') 
            THEN 'Aceptado' 
        WHEN (ai.status_hacienda = 'procesando') 
            THEN 'Procesando' 
        WHEN (ai.status_hacienda = 'rechazado') 
            THEN 'Rechazado' 
        ELSE '-' 
    END AS estado_hacienda,
    ai.fecha_envio_hacienda 
    from account_invoice ai  
    left join res_partner rp on ai.partner_id=rp.id 
    left join res_currency rc on rc.id=ai.currency_id 
    left join currency_rate cr on (cr.currency_id = 3 and
                            cr.date_start <= coalesce(   TO_TIMESTAMP(ai.date_invoice::varchar || ' 06:00:00', 'YYYY/MM/DD HH24:MI:SS'), now()) and
                            (cr.date_end is null or cr.date_end > coalesce(TO_TIMESTAMP(ai.date_invoice::varchar || ' 06:00:00', 'YYYY/MM/DD HH24:MI:SS'), now())))

    where ai.state in ('open', 'paid')
    """

    def generate_xlsx_report(self, workbook, data, lines):


        sheet = workbook.add_worksheet('Detalle por lineas de facturas')
        sheet2 = workbook.add_worksheet('Resumen por facturas provedores')

        cabeceras = ["Cedula cliente/proveedor", "Nombre", "Tipo Doc",
                     "No. Factura", "Referencia", "Fecha Factura", "Producto", "Descripcion", "Cantidad", "Precio Unitario",
                     "Cuenta Contable", "Moneda", "Monto gravado en colones", "Impuesto colones", "Monto total en colones",
                     "Monto gravado en dolares", "Impuesto dolares", "Monto total en dolares",
                     "Porcentaje de impuesto utilizado", "Descuento", "Tipo de cambio del dia recepcion",
                     "Estado Pago", "Referencia de Pago", "Fecha de Pago",
                     "Telefono", "Correo electronico ", "Estado en tributacion",
                     "Fecha recepcion en sistema"]

        cabeceras2 = ["Cedula cliente/proveedor", "Nombre", "Tipo Doc",
                     "No. Factura", "Referencia", "Fecha Factura", "Moneda", "Monto gravado en colones", "Impuesto colones",
                      "Monto total en colones", "Monto gravado en dolares", "Impuesto dolares", "Monto total en dolares",
                     "Porcentaje de impuesto utilizado", "Tipo de cambio del dia recepcion",
                     "Telefono", "Correo electronico", "Estado en tributacion",
                     "Fecha recepcion Tributacion"]

        def escribir_cabeceras(hoja, data):
            columna = 0
            hoja.set_column(0, 26, 35)
            for head in data:
                hoja.write(0, columna, head)
                columna += 1
        escribir_cabeceras(sheet, cabeceras)

        record = lines
        where = ""
        if record.date_start:
            where = " and ai.date_invoice >= '" + str(record.date_start) + "'"
            if record.date_end:
                where += " AND ai.date_invoice <= '" + str(record.date_end) + "'"
        orderby = " order by tipo_factura, numero"
        global select
        query = select + where + orderby
        cr = lines.env.cr
        main_query = """
        SELECT 
        cedula, 
        nombre_cliente, 
        tipo_factura, 
        numero,
        referencia,
        fecha_factura,
        nombre_producto,
        descripcion,
        cantidad,
        precio_unitario,
        nombre_cuenta,
        moneda,
        
        CASE WHEN (id_moneda=40) THEN monto_gravado ELSE (1/tipo_cambio) * monto_gravado END AS monto_gravado,
        CASE WHEN (id_moneda=40) THEN total_impuesto ELSE (1/tipo_cambio) * total_impuesto END AS total_impuesto,
        CASE WHEN (id_moneda=40) THEN total ELSE (1/tipo_cambio) * total END AS total,
        
        CASE WHEN (id_moneda=40) THEN (monto_gravado/(1/tipo_cambio))  ELSE monto_gravado END AS monto_gravado_usd,
        CASE WHEN (id_moneda=40) THEN (total_impuesto/(1/tipo_cambio)) ELSE total_impuesto END AS total_impuesto_usd,
        CASE WHEN (id_moneda=40) THEN (total/(1/tipo_cambio))          ELSE total END AS total_usd,
        impuestos as impuesto_utilizado,
        descuento,
        (1/tipo_cambio) as tipo_cambio_final,
        estado_factura,
        '-' as ref_pago,
        '-' as fec_pago, 
        
        telefono,
        correo,
        estado_hacienda,
        fecha_envio_hacienda
        from (%s) subtable
        """ % (query,)
        cr.execute(main_query)
        print cr.query

        def escribir_hoja(hoja, data):
            fila = 1
            for line in data:
                columna = 0
                for column_val in line:
                    """if columna == 1: #columna con la fecha
                        date_time = datetime.strptime(column_val, '%Y-%m-%d %H:%M:%S')
                        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
                        hoja.write(fila, columna, date_time, date_format)
                    else:"""
                    if type(column_val) in (float, int):
                        hoja.write_number(fila, columna, round(column_val, 3))
                    else:
                        hoja.write(fila, columna, column_val)

                    """if columna == 8: #columna con el nombre de la presentación
                        columna += 1
                        presentacion = self.split_presentacion(column_val)
    
                        hoja.write(fila, columna, presentacion[0])
                        columna += 1
                        hoja.write(fila, columna, presentacion[1])
                    """
                    columna += 1
                fila += 1
        escribir_hoja(sheet, cr.fetchall())

        global select2
        query2 = select2 + where + orderby
        cr = lines.env.cr
        main_query2 = """
        SELECT 
        cedula, 
        nombre_cliente, 
        tipo_factura, 
        numero,
        referencia,
        fecha_factura,
        
        moneda,

        CASE WHEN (id_moneda=40) THEN monto_gravado ELSE (1/tipo_cambio) * monto_gravado END AS monto_gravado,
        CASE WHEN (id_moneda=40) THEN total_impuesto ELSE (1/tipo_cambio) * total_impuesto END AS total_impuesto,
        CASE WHEN (id_moneda=40) THEN total ELSE (1/tipo_cambio) * total END AS total,

        CASE WHEN (id_moneda=40) THEN (monto_gravado/(1/tipo_cambio))  ELSE monto_gravado END AS monto_gravado_usd,
        CASE WHEN (id_moneda=40) THEN (total_impuesto/(1/tipo_cambio)) ELSE total_impuesto END AS total_impuesto_usd,
        CASE WHEN (id_moneda=40) THEN (total/(1/tipo_cambio))          ELSE total END AS total_usd,
        impuestos as impuesto_utilizado,
        (1/tipo_cambio) as tipo_cambio_final,
        telefono,
        correo,
        estado_hacienda,
        fecha_envio_hacienda
        from (%s) subtable
        """ % (query2,)
        cr.execute(main_query2)
        print cr.query
        escribir_cabeceras(sheet2, cabeceras2)
        escribir_hoja(sheet2, cr.fetchall())


ReportAccountInvoiceParser('report.reportes_facturas.report_account_invoice_report.xlsx', 'reporte.account.invoice')
