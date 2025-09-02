# -*- coding: utf-8 -*-
##############################################################################
#    Copyright 2018 Bryan
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

{
    "name": "Módulo para conectar odoo POS con hacienda",
    'version': '1.0',
    'category': 'Sales',
    'description': """
        
    """,
    'author': 'bryanjs@outlook.es',
    'website': 'https://www.facebook.com/VinnyJS',
    'license': 'AGPL-3',
    'depends': ['web', 'account', 'point_of_sale', 'facturacion_hacienda'],
    'data': [
        'views/assets.xml',
        'views/account_journal_views.xml',
    ],
    'qweb': ["static/src/xml/ace.xml"],
    'post_init_hook': 'post_init_hook',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
