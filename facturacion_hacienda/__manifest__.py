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
    "name": "Módulo para conectar odoo con hacienda",
    'version': '1.0',
    'category': 'Accounting',
    'description': """
        
    """,
    'author': 'bryanjs@outlook.es',
    'website': 'https://www.facebook.com/VinnyJS',
    'license': 'AGPL-3',
    'depends': ['web', 'account', 'l10n_cr_country_codes', 'web_tour', 'base',
                'product', 'sales_team', 'l10n_cr_country_codes', 'account_cancel', 'currency_rate_update', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',

        'data/code.type.product.csv',
        'data/identification.type.csv',
        'data/payment.methods.csv',
        'data/reference.code.csv',
        'data/reference.document.csv',
        'data/sale.conditions.csv',
        'data/unit.measure.code.csv',
        #'data/product.uom.csv',
        'data/account.tax.cr.code.csv',
        'data/codigo.actividad.csv',

        'views/assets.xml',
        'views/params.xml',
        'views/miscellaneous_views.xml',
        'views/base_res.xml',
        'views/product_views.xml',
        'views/account_journal_views.xml',
        'views/account_view.xml',
        'views/electronic_invoice_views.xml',
        #'views/invoice_template.xml',
        'views/menu.xml',

        'data/data.xml',
        'data/mail.template.csv',
        #'reports/download_xml_report.xml',
    ],
    'external_dependencies': {
        'python': [
            'yattag' #sudo -H pip install yattag
        ],
    },
    'qweb': ["static/src/xml/ace.xml"],
    'post_init_hook': 'post_init_hook',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
