odoo.define('facturacion.ace_xml', function (require) {
"use strict";

var ajax = require('web.ajax');
var core = require('web.core');
var _t = core._t;
var QWeb = core.qweb;

var ListView = require('web.ListView');
var FormView = require('web.FormView');
var Model = require('web.Model');
var formats = require('web.formats');

var common = require('web.form_common');
var AceXml = common.AbstractField.extend(common.ReinitializeFieldMixin, {
    template: "AceXml",
    willStart: function() {
        if (!window.ace && !this.loadJS_def) {
            this.loadJS_def = ajax.loadJS('/web/static/lib/ace/ace.odoo-custom.js').then(function () {
                return $.when(ajax.loadJS('/web/static/lib/ace/mode-xml.js'));
            });
        }
        return $.when(this._super(), this.loadJS_def);
    },
    render_value: function() {
	var txt = this.get("value") || false;
	if(txt === false){
		return;
	}
	this.$el.text(txt);
	var aceEditor = false;
	try {
		var aceEditor = window.ace.edit(this.$el[0]);
	}
	catch(err) {
	    return;
	}
	aceEditor.setOptions({"maxLines": Infinity, readOnly: true});
	var aceSession = aceEditor.getSession();
        aceSession.setMode("ace/mode/xml");
    }
});


function get_tipo_cambio(self){
    new Model("res.currency")
        .call("get_tipo_cambio", [])
        .then(function (result) {
            if(!result){
                self.$buttons.find('#cambio').parent().remove();
                return;
            }
            var monedas = [];
            _.forEach(result, function(r){
                monedas.push(r.name+ ": "+ formats.format_value(1/r.rate, {type: "float"}));
            });
            self.$buttons.find('#cambio').text(monedas.join(' / '));
        });
}

ListView.include({
    render_buttons: function($node) {
        this._super($node);
        var self = this;
        get_tipo_cambio(self);
    },
});

FormView.include({
    render_buttons: function($node) {
        this._super($node);
        var self = this;
        get_tipo_cambio(self);
    },
});



core.form_widget_registry.add('ace_xml', AceXml);

});
