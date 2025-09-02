# -*- coding: utf-8 -*-

import models
from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    plazos = env['account.payment.term']
    contado = env.ref('cr_electronic_invoice.SaleConditions_1')
    credito = env.ref('cr_electronic_invoice.SaleConditions_2')
    for payment_term in plazos.search([]):
        dias = payment_term.line_ids[0].days
        if dias == 0:
            payment_term.sale_conditions_id = contado.id
        elif dias > 0:
            payment_term.sale_conditions_id = credito.id
    cr.commit()

