# -*- coding: utf-8 -*-
# © 2009 Camptocamp
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from .currency_getter_interface import CurrencyGetterInterface

from odoo import _
from odoo.exceptions import except_orm
import time
import logging
_logger = logging.getLogger(__name__)


class BACGetter(CurrencyGetterInterface):
    """Implementation of Curreny_getter_factory interface
    for Bank of Canada RSS service

    """
    # Bank of Canada is using RSS-CB
    # http://www.cbwiki.net/wiki/index.php/Specification_1.1
    # This RSS format is used by other national banks
    #  (Thailand, Malaysia, Mexico...)

    code = 'BAC'
    name = 'BAC Credomatic de Costa Rica'

    codes = {
        "USD": 318,
        "EUR": 333
    }

    supported_currency_array = codes.keys()

    # Parse url
    def get_url(self, url):
        """Return a string of a get url query"""
        try:
            import urllib
            objfile = urllib.urlopen(url)
            rawfile = objfile.read()
            objfile.close()
            return rawfile
        except ImportError:
            raise Exception('Error !\n' + 'Unable to import urllib !')
        except IOError:
            raise Exception('Error !\n' + 'Web Service does not exist !')

    def get_updated_currency(self, currency_array, main_currency,
                             max_delta_days):
        """implementation of abstract method of Curreny_getter_interface"""

        # as of Jan 2014 BOC is publishing noon rates for about 60 currencies
        today = time.strftime('%d/%m/%Y')
        url1 = 'https://www.baccredomatic.com/es-cr/bac/exchange-rate-ajax/es-cr'
        # closing rates are available as well (please note there are only 12
        # currencies reported):
        # http://www.bankofcanada.ca/stats/assets/rates_rss/closing/en_%s.xml

        # We do not want to update the main currency
        if main_currency in currency_array:
            currency_array.remove(main_currency)

        import feedparser
        import pytz
        from dateutil import parser
        from xml.dom.minidom import parseString
        
        for curr in currency_array:

            last_rate_date = today
            last_rate_datetime = time.strftime('%Y-%m-%d %H:%M:%S')
            url = url1 + last_rate_date + url2

            # =======Get code for rate

            url = url + str(self.codes[curr])

            _logger.debug("BCCR currency rate service : connecting...")
            _logger.info(url)
            rawstring = self.get_url(url)
            dom = parseString(rawstring)
            nodes = dom.getElementsByTagName('INGC011_CAT_INDICADORECONOMIC')
            for node in nodes:
                num_valor = node.getElementsByTagName('NUM_VALOR')
                if len(num_valor):
                    rate = num_valor[0].firstChild.data
                else:
                    continue
                des_fecha = node.getElementsByTagName('DES_FECHA')
                if len(des_fecha):
                    date_str = des_fecha[0].firstChild.data.split('T')[0]
                else:
                    continue
                if float(rate) > 0:
                    self.updated_currency[curr] = float(1)/ float(rate)
        #Esto de abajo se hace para convertir las otras monedas que no sean dolares a colones, ya que el bccr tiene
        #todas las demas monedas convertidas a dolares y no a colones
        usd = self.updated_currency.get('USD', False)
        if usd:
            for c in self.updated_currency:
                if c != 'USD':
                    self.updated_currency[c] = 1 / ((1/usd) * (float(1)/ float(self.updated_currency[c])))
            
        _logger.info(self.updated_currency)
        return self.updated_currency, self.log_info