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
from datetime import datetime
from dateutil.parser import parse
import logging
_logger = logging.getLogger(__name__)

class SaleStages(models.Model):

    _name = 'sale.stages'
    _order = 'sequence'

    name = fields.Char(string='Nombre', required=True, )
    description = fields.Text('Descripción')
    sequence = fields.Integer(default=1)
    fold = fields.Boolean(string='Doblar en vista kanban')

SaleStages()


class SaleStageHistory(models.Model):

    _name = 'sale.stage.history'
    _order = 'sale, date'

    name = fields.Char(string='Descripción')
    init_date = fields.Datetime('Fecha Inicio')
    end_date = fields.Datetime('Fecha Final')
    order_id = fields.Many2one('sale.order', 'Orden')

SaleStageHistory()


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        #search_domain = [('id', 'in', stages.ids)]
        stage_ids = stages.search([])
        return stage_ids

    def _get_default_stage_id(self):
        """ Gives default stage_id """
        stage = self.env['sale.stages'].search([], limit=1)
        return stage.id if stage else False

    @api.depends('stage_history_ids')
    def _compute_time_process(self):
        time_process_text = ''
        for order in self:
            time_process = ''
            cr = self.env.cr
            cr.execute('select create_date, init_date, end_date from sale_stage_history where order_id=%s and init_date is not null order by 1' % (order.id,))
            dates = cr.dictfetchall()
            if len(dates) > 1:
                i_date = parse(dates[0]['init_date'])
                e_date = parse(dates[-1:][0]['end_date'])
                delta = e_date - i_date
                time_process = delta.days + ( delta.seconds / 86400.00 )
                days = int(time_process)
                hours = 24 * (time_process - days)
                mins = hours - int(hours)
                time_process_text = '%s días, %s horas, %s min.' % (days, int(hours), int(60 * mins))
            order.time_process = time_process_text

    stage_id = fields.Many2one('sale.stages', string='Etapa', track_visibility='onchange', index=True,
        default=_get_default_stage_id, group_expand='_read_group_stage_ids',
        copy=False)
    last_stage_update = fields.Datetime('Última actualización de etapa')
    stage_history_ids = fields.One2many('sale.stage.history', 'order_id', string='Historial de etapas')
    time_process = fields.Char('Tiempo en proceso', compute='_compute_time_process')

    @api.multi
    def write(self, vals):
        if 'stage_id' in vals:
            last_update = fields.Datetime.now()
            self.env['sale.stage.history'].create({'init_date': self.last_stage_update, 
                                                   'end_date': last_update,
                                                   'order_id': self.id,
                                                   'name': '%s --> %s'%(self.stage_id.name, self.stage_id.browse(vals['stage_id']).name)
            })
            vals['last_stage_update'] = last_update
        return super(SaleOrder, self).write(vals)

SaleOrder()
