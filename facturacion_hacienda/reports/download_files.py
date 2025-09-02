# -*- encoding: utf-8 -*-
from odoo import fields, models
from odoo.report.report_sxw import report_sxw
from odoo.api import Environment
import time
import shutil
import os

class ir_actions_report_xml(models.Model):
    _inherit = 'ir.actions.report.xml'

    report_type = fields.Selection(selection_add=[("zip", "ZIP")])

ir_actions_report_xml()


class ReportZIP(report_sxw):

    def create(self, cr, uid, ids, data, context=None):
        self.env = Environment(cr, uid, context)
        report_obj = self.env['ir.actions.report.xml']
        report = report_obj.search([('report_name', '=', self.name[7:])])
        if report.ids:
            self.title = report.name
            if report.report_type == 'zip':
                return self.create_zip_report(ids, data, report)
        return super(ReportZIP, self).create(cr, uid, ids, data, context)

    def create_zip_report(self, ids, data, report):
        self.parser_instance = self.parser(
            self.env.cr, self.env.uid, self.name2, self.env.context)
        objs = self.getObjects(
            self.env.cr, self.env.uid, ids, self.env.context)
        self.parser_instance.set_context(objs, data, ids, 'zip')
        result = self.generate_zip_report(data, objs)
        return result, 'zip'

    def generate_zip_report(self, data, objs):
        raise NotImplementedError()



class XMLHacienda(ReportZIP):

    def generate_zip_report(self, data, invoices):
        epoch = str(time.time())
        folder_path = '/tmp/' + epoch
        os.mkdir(folder_path, 0755)
        invoices_ids = invoices.ids
        invoices_ids += [0]
        attachment = self.env['ir.attachment']
        cr = self.env.cr
        cr.execute("select store_fname, ai.clave_envio_hacienda as name, res_field, res_id from ir_attachment left join account_invoice ai on ai.id=res_id where res_model='account.invoice' \
                    and res_field in ('xml_respuesta_tributacion', 'xml_comprobante') and res_id in %s order by 4, 3;" % (tuple(invoices_ids),))

        parent_path = attachment._filestore()


        last_name = ""
        for r in cr.dictfetchall():
            full_path = os.path.join(parent_path, r['store_fname'])
            filename = r['name']
            if r['res_field'] == 'xml_respuesta_tributacion':
                filename = filename + "-respuesta" #las respuestas vienen sin nombre, por lo tanto se les asigna
                                                         # el de los comprobantes
            subcarpeta = folder_path + '/' + r['name']
            if not os.path.exists(subcarpeta):
                os.makedirs(subcarpeta)
            shutil.copy2(full_path, subcarpeta + "/" + filename  + ".xml")
            #last_name = r['name'].replace(".xml", "")

        shutil.make_archive(folder_path, 'zip', folder_path, base_dir=None) #crea el archivo
        zipFile = open(folder_path + '.zip', "rb").read() #lee el archivo
        shutil.rmtree(folder_path, ignore_errors=True)
        os.remove(folder_path + '.zip')
        return zipFile


XMLHacienda('report.facturacion_hacienda.archivos_xml', 'account.invoice')

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
