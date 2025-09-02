# -*- coding: utf-8 -*-
{
	'name': 'Facturación electrónica Costa Rica',
	'version': '0.1',
	'author': 'DelfixCR',
	'license': 'OPL-1',
	'website': 'https://www.delfixcr.com',
	'category': 'Account',
	'description':
		'''
		Facturación electronica Costa Rica.
		''',
	'depends': ['base', 'account','product','sales_team','l10n_cr_country_codes','account_cancel'],
	'data': ['views/account_journal_views.xml',
			 'views/electronic_invoice_views.xml',
	         #'data/data.xml',
	         'data/code.type.product.csv',
	         'data/identification.type.csv',
	         'data/payment.methods.csv',
	         'data/reference.code.csv',
	         'data/reference.document.csv',
	         'data/sale.conditions.csv',
	         'data/product.uom.csv',
		 	 'data/account.tax.cr.code.csv',
	         'security/ir.model.access.csv',
	         'security/groups.xml',
	         ],
	'installable': True,
	'post_init_hook': 'post_init_hook',
}


































