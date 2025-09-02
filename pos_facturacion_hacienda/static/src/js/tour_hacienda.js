odoo.define('tour.facturacion', function(require) {
"use strict";
//#https://es.wordpress.org/plugins/tawkto-live-chat/
var core = require('web.core');
var tour = require('web_tour.tour');

var _t = core._t;

tour.register('tour_facturacion', {
	    url: "/web",
	}, [tour.STEPS.MENU_MORE, {
	    trigger: '.o_app[data-menu-xmlid="account.menu_finance"]',
	    content: _t('Quieres comenzar a <b>facturar</b>?<br/><i>Has click aquí para configurar tus datos.</i>'),
	    position: 'bottom',
	}, {
	    trigger: 'li a[data-menu-xmlid="account.menu_finance_configuration"], div[data-menu-xmlid="account.menu_finance_configuration"]',
	    content: _t('Vamos a configurar los datos de tu empresa'),
	    position: 'bottom',
	}, {
	    trigger: 'li a[data-menu-xmlid="account.menu_account_config"], div[data-menu-xmlid="account.menu_account_config"]',
	    content: _t('Click para ir a la configuración'),
	    position: 'bottom',
	}, {
	    trigger: 'table.o_inner_group:eq(1) tbody tr:eq(1) td:eq(1) div div button',
	    content: _t('Click para ir a la configuración'),
	    position: 'bottom',
	}]);
});





