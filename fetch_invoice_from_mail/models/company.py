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

from odoo import models, fields, api
import logging
from emaillib2 import MailBox
import os
import re
import base64
from lxml import etree as ET
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from dateutil.parser import parse
from datetime import datetime, timedelta
import imaplib

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    host_imap_server_fe = fields.Char('Servidor IMAP')
    port_imap_server_fe = fields.Integer('Puerto IMAP')
    user_imap_server_fe = fields.Char('Usuario IMAP')
    pass_imap_server_fe = fields.Char('Contraseña IMAP')
    filter_by = fields.Selection([('date', 'Fecha'), ('unseen', 'No leidos')], 'Filtrar por', default='unseen')
    date_from = fields.Date('Fecha Inicio')

    def _default_journal(self, type, company_id):
        domain = [
            ('type', '=', type),
            '|',
            ('company_id', '=', company_id),
            ('company_id', '=', False),
        ]
        return self.env['account.journal'].search(domain, limit=1)

    def open_connection(self, user, password, hostname, port):
        # Connect to the server
        connection = imaplib.IMAP4_SSL(hostname, port)
        # Login to our account
        connection.login(user, password)
        connection.credentials = {
            'user': user,
            'password': password,
            'hostname': hostname,
            'port': port
        }

        def reconnect():
            return self.open_connection(user, password, hostname, port)

        connection.reconnect = reconnect
        connection.select("inbox")
        return connection

    def mark_unseen(self, connection, message_id, retry=True):
        try:
            connection.uid('STORE', message_id, '-FLAGS', '(\Seen)')
        except Exception as e:
            if retry:
                try:
                    new_connection = connection.reconnect()
                except Exception as e:
                    _logger.error('No se pudo re-abrir la conexion')
                    return True
                return self.mark_unseen(new_connection, message_id, False)

    @api.model
    def fetch_emails(self):
        companies = self.search([])
        companies_dict = {}
        num2month = {
            1: 'Jan',
            2: 'Feb',
            3: 'Mar',
            4: 'Apr',
            5: 'May',
            6: 'Jun',
            7: 'Jul',
            8: 'Aug',
            9: 'Sep',
            10: 'Oct',
            11: 'Nov',
            12: 'Dec'
        }

        for c in companies:
            if c.ref:
                companies_dict.update({
                    c.ref: {
                        'id': c.id,
                        'journal_id': self._default_journal('purchase', c.id),
                    }
                })

        for company in companies:
            if not company.host_imap_server_fe or not company.port_imap_server_fe or not company.user_imap_server_fe or not company.pass_imap_server_fe:
                _logger.error(
                    "FETCH MAIL ERROR. Hacen falta completar los parametros de la compannia: %s" % (company.name))
                continue

            mailbox = MailBox(company.host_imap_server_fe, company.port_imap_server_fe)
            connection = False
            try:
                mailbox.login(company.user_imap_server_fe, company.pass_imap_server_fe)
                connection = self.open_connection(company.user_imap_server_fe, company.pass_imap_server_fe,
                                                  company.host_imap_server_fe, company.port_imap_server_fe)
                _logger.info('Success login %s' % company.name)
            except Exception as e:
                _logger.info(
                    "FETCH MAIL ERROR. No se pudo conectar al correo en la compannia: %s %s" % (company.name, str(e)))
                continue

            if company.filter_by == 'date':
                fecha = parse(company.date_from)
                fecha2str = fecha.strftime("%d-") + num2month[int(fecha.strftime("%m"))] + fecha.strftime("-%Y")
                _logger.info('va a hacer fetch')
                new_emails = mailbox.fetch('(SINCE "%s")' % (fecha2str.upper(),))
            else:
                new_emails = mailbox.fetch('(UNSEEN)')

            xml2invoice = self.env['xml.invoice']
            _logger.info('nuevos emails %s '%new_emails)
            for message in new_emails:
                _logger.info('leyendo correo %s' % message.subject)
                attachments = list(message.get_attachments())
                for filename, payload in attachments:
                    if filename.split('.')[-1:][0].lower() == "xml":
                        try:
                            contenido = payload.replace('\n', '').replace('\t', '')
                            # contenido = payload.decode('utf-8').replace('\n', '').replace('\t', '')
                        except:
                            _logger.info("XML no valido1 %s" % (e.message,))
                            self.mark_unseen(connection, message.id)
                            continue
                        try:
                            root = ET.fromstring(
                                re.sub(' xmlns=(\'|\")([a-zA-Z]|\:|\/|\.|\d|\-)*(\'|\")', '', contenido, count=1)\
                                    .decode('utf-8', 'ignore').encode('utf-8', 'ignore'))
                            # quita el namespace de los elementos
                            if root.tag not in ('FacturaElectronica', 'TiqueteElectronico', 'NotaDebitoElectronica', 'NotaCreditoElectronica'):
                                continue
                        except Exception as e:
                            _logger.info("XML no valido2 %s" % (e.message,))
                            self.mark_unseen(connection, message.id)
                            continue
                        invoice_warning = ''
                        doc_type = {
                            'FacturaElectronica': 'in_invoice',
                            'TiqueteElectronico': 'in_invoice',
                            'NotaDebitoElectronica': 'in_invoice',
                            'NotaCreditoElectronica': 'in_refund',
                        }[root.tag]
                        if root.tag in ('TiqueteElectronico', 'NotaDebitoElectronica'):
                            invoice_warning += '***Cuidado, este documento es un ' + root.tag
                        xml_company = root.findall('Receptor')
                        if xml_company is not None:
                            try:
                                xml_company = xml_company[0].find('Identificacion')
                            except:
                                self.mark_unseen(connection, message.id)
                                continue #return False
                            if xml_company is not None:
                                xml_company = xml_company[1].text
                            else:
                                xml_company = company.ref

                        company2send = companies_dict.get(xml_company, False)

                        if not company2send:
                            company2send = company.ref
                            if invoice_warning != '':
                                invoice_warning += '\n'
                            invoice_warning += 'La cédula del XML es distinta a la suya'
                            # toma el id de la compañia del correo en caso que el del XML no coincida con ninguno de
                            # los actuales
                        else:
                            company2send = xml_company
                        result = xml2invoice.load_xml_file(root, attachments, {
                            'company_id': companies_dict[company2send]['id'],
                            'journal_id': companies_dict[company2send]['journal_id'].id,
                            'type': doc_type,
                            'invoice_warning': invoice_warning
                        })
                        if result:
                            try:
                                invoice_id = self.env['account.invoice'].sudo().create(result)
                                _logger.info('Factura creada de manera exitosa, num: %s id: %s' % (
                                root.find('Clave').text, invoice_id))
                            except Exception as e:
                                _logger.error('Hubo un error al intentar CREAR la factura, '
                                              'el correo es %s con la fecha %s ****ERROR: %s' % (
                                              message.subject, message.date, e))
                                self.mark_unseen(connection, message.id)
                        else:
                            _logger.error('Hubo un error al procesar el '
                                          'correo %s con la fecha %s' % (
                                          message.subject, message.date))
                            self.mark_unseen(connection, message.id)
                if not len(attachments):
                    self.mark_unseen(connection, message.id)
            company.date_from = datetime.now().date()
        return True


ResCompany()
