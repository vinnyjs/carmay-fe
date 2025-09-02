# -*- encoding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2017 Ciris Informatic Solution. S.A.
#    (http://wwww.ciriscr.com)
#    bryan.jimenez@ciriscr.com
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Plantilla de CxC',
    'version': '10.0',
    'category': '',
    'description': """
        Plantilla para impresion de facturas
    """,
    'author': 'Bryan JS',
    'website': 'http://www.facebook.com/VinnyJS',
    'depends': ['web', 'base', 'account', 'account_report_tools'],
    'data': [
        "views/invoice_report.xml",
        "data/report.paperformat.csv",
    ],
    'qweb': [],
    'installable': True,
    'auto_install': True,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
