# -*- coding: utf-8 -*-

import json
from os import getenv

from flask import Flask, request
from jinja2 import Environment

#for API requests
from urllib.request import Request, urlopen
import urllib.parse 
from datetime import datetime, timedelta

import structlog

from logger import configure_stdout_logging

# API request helper function
def request_url(url, data=None,headers={},origin_req_host=None,unverifiable=False,method=None,params={}):
    if params:
        query_string = urllib.parse.urlencode( params )
        url = url + "?" + query_string

    request = Request(url, data, headers,origin_req_host,unverifiable,method)
    response = urlopen(request)
    data = response.read()
    return json.loads(data)


def setup_logger():
    logger = structlog.get_logger(__name__)
    try:
        log_level = getenv("LOG_LEVEL", default="INFO")
        configure_stdout_logging(log_level)
        return logger
    except BaseException:
        logger.exception("exception during logger setup")
        raise


logger = setup_logger()
app = Flask(__name__)
environment = Environment()


def jsonfilter(value):
    return json.dumps(value)


environment.filters["json"] = jsonfilter
CURRENCY = ''

def error_response(message):
    response_template = environment.from_string("""
    {
      "status": "error",
      "message": {{message|json}},
      "data": {
        "version": "1.0"
      }
    }
    """)
    payload = response_template.render(message=message)
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending error response to TDM", response=response)
    return response


def query_response(value, grammar_entry):
    response_template = environment.from_string("""
    {
      "status": "success",
      "data": {
        "version": "1.1",
        "result": [
          {
            "value": {{value|json}},
            "confidence": 1.0,
            "grammar_entry": {{grammar_entry|json}}
          }
        ]
      }
    }
    """)
    payload = response_template.render(value=value, grammar_entry=grammar_entry)
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending query response to TDM", response=response)
    return response


def multiple_query_response(results):
    response_template = environment.from_string("""
    {
      "status": "success",
      "data": {
        "version": "1.0",
        "result": [
        {% for result in results %}
          {
            "value": {{result.value|json}},
            "confidence": 1.0,
            "grammar_entry": {{result.grammar_entry|json}}
          }{{"," if not loop.last}}
        {% endfor %}
        ]
      }
    }
     """)
    payload = response_template.render(results=results)
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending multiple query response to TDM", response=response)
    return response


def validator_response(is_valid):
    response_template = environment.from_string("""
    {
      "status": "success",
      "data": {
        "version": "1.0",
        "is_valid": {{is_valid|json}}
      }
    }
    """)
    payload = response_template.render(is_valid=is_valid)
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending validator response to TDM", response=response)
    return response
def lookup_currency_code(name):
    with open('currency_codes.json', 'r') as file:
        currency_codes = json.load(file)
        for currency_key in [name, name.upper()]:
          try:
            return currency_codes[currency_key]
          except KeyError:
            pass
def read_facts(predicate, payload, value='gr', default=""):
  facts = payload["context"]["facts"]
  if predicate not in facts:
    return default
  if value=='gr':
    predicate_value = facts[predicate]["grammar_entry"]
  elif value=='v':
    predicate_value = facts[predicate]["value"]
  return str(predicate_value)
def get_airport_id(city):
    '''Get a list of places that match a query string.'''
    
    url = f"https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/autosuggest/v1.0/SE/SEK/en-GB/"
    querystring = {"query":f"{city}"}

    headers = {
        'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
        'x-rapidapi-key': "085a3ad9afmshd9eee4320cbb30dp15f68cjsn6a30068652ff"
        }

    try:
        airport_data = request_url(url, headers=headers, params=querystring)
        airport_id = airport_data["Places"][0]["PlaceId"]
        return airport_id
    except Exception:
        return ''
def get_currency():
    # return 'SEK'
    try:
        with open('currency.txt', 'r') as f:
            currency = f.readline()
            if not currency:
              currency = 'EUR' 
    except Exception:
        currency = 'EUR'  
 
    return currency
def get_quotes(from_airport,to_airport,start_date,end_date=''):
    country_code, currency = 'SE', get_currency() # Read the currency, EUR by default 
    url = f"https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/browsequotes/v1.0/{country_code}/{currency}/en-US/{from_airport}/{to_airport}/{start_date}"

    querystring = {"inboundpartialdate":{end_date}} # "" for one-way trip, or “yyyy-mm-dd”, “yyyy-mm” or “anytime”

    headers = {
        'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
        'x-rapidapi-key': "085a3ad9afmshd9eee4320cbb30dp15f68cjsn6a30068652ff"
        }

    return request_url(url, headers=headers, params=querystring)
def str_to_date(date_time_str):
    # parse eg '2021-12-03T00:00:00' to '3rd December'
    this_year = datetime.now().year
    ymd = date_time_str.split('T')[0]
    date_time_obj = datetime.strptime(ymd, '%Y-%m-%d') # Parsed from string
    year = date_time_obj.date().year 
    
    # ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
    day = date_time_obj.date().day
    # day = ordinal(int(day))
    month = date_time_obj.date().strftime("%B")
    
    out = f"{day} {month}" if year==this_year else f"{day} {month} {year}"
    return out
def quote_flights(from_city_id, to_city_id, from_date, to_date='', max_price=None, direct_only=False):
    
    quotes_data = get_quotes( 
        from_city_id, 
        to_city_id, 
        from_date, to_date)
    
    if not quotes_data['Quotes']:
        return None
    
    airlines_dict = {a['CarrierId']:a['Name'] for a in quotes_data['Carriers']} # eg {1090: 'Ryanair', 1707: 'SAS'}

    lo_price = [ quote['MinPrice'] for quote in quotes_data['Quotes'] ][0]
    currency_sign = quotes_data['Currencies'][0]['Symbol']

    is_direct = lambda x : 'direct' if x else 'non-direct'
    airway = lambda a_list : airlines_dict[a_list[0]]

    flights = [{'direct':is_direct(q['Direct']), 
                'price':q['MinPrice'],
                'symbol':currency_sign,
                'airline':airway(q['OutboundLeg']['CarrierIds']),
                'date':str_to_date(q['OutboundLeg']['DepartureDate'])}
               for q in quotes_data['Quotes']]
        
    
    if max_price:
        flights = [f for f in flights if f['price']<=max_price]
    if direct_only:
        flights = [f for f in flights if f['direct']=='direct']
    

    return flights
def preds_to_datestr(D,MorP,Y):
    date_items = []
    for item in (D,MorP,Y):
        if item in ('anytime','tomorrow','next month', 'next_month'):
            return item
        if item:
            date_items.append(item)

    return ' '.join(date_items)
def parse_said_date(date):
    
    # date = Dec, Dec 2021, 25 Dec, Dec 25, Dec 25 2021, 25 Dec 2021, or anytime/tomorrow/next month
    # returns: yyyy-mm, yy-mm, anytime, or None
    if date in ['anytime','tomorrow','next month', 'next_month']:
        today = datetime.today()
        if date == 'tomorrow':
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        if date in ['next month', 'next_month']:
            return ((today.replace(day=1) + timedelta(days=32)).replace(day=1)).strftime("%Y-%m")
        if date == 'anytime':
            return 'anytime'
    
    for fmt in ('%B', '%B %Y', '%d %B', '%B %d', '%B %d %Y', '%d %B %Y'):
        try:
            date_obj = datetime.strptime(date, fmt)
            
            # Assume year to be this year if not given; 
            if '%Y' not in fmt:
                today = datetime.today()
                this_year, this_month = today.year, today.month 
                date_obj = date_obj.replace(year=this_year) # change y to this year
                
                # assume next year if date already passed
                if date_obj<datetime.today() and date_obj.month!=this_month: 
                    date_obj = date_obj.replace(year=this_year+1)
                
            # return yyyy-mm or yyyy-mm-dd
            if '%d' in fmt:
                return date_obj.strftime("%Y-%m-%d")
            else:
                return date_obj.strftime("%Y-%m")
        except ValueError:
            pass
        
    return ""
def read_the_flight(flights, i=0, show_date=False):
    f = flights[i]
    if show_date:
        info = f"a {f['direct']} flight for {f['price']}{f['symbol']} with {f['airline']} on {f['date']}"
    else:
        info = f"a {f['direct']} flight for {f['price']}{f['symbol']} with {f['airline']}"
    return info
def summarize_flights(flights):
    f_first = flights[0]
    f_last = flights[-1]
    symbol = f_first['symbol']
    min_p, max_p = f_first['price'], f_last['price']
    n_direct = len([f for f in flights if f['direct']=='direct'])
    n_nondirect = len([f for f in flights if f['direct']=='non-direct'])
    
    if n_direct==0:
        n_flights = f'{n_nondirect} non-direct flights'
    elif n_nondirect==0:
        n_flights = f'{n_direct} direct flights'
    else:
        n_flights = f'{n_direct} direct and {n_nondirect} non-direct flights'
        
    summary = f"{len(flights)} flights from {min_p}{symbol} to {max_p}{symbol}, including {n_flights}"
    return summary   
def save_flights(flights, fn='flights.json'):
    '''saves a list of dicts to a file'''
    with open(fn, 'w', encoding='utf8') as file:
        json.dump(flights, file)
def load_saved_flights():
    '''retrieves and returns a saved file to dict'''
    with open("flights.json", "r") as file:
        flights = json.load(file)
    return flights
def get_iata_code(city):
    '''Get a list of places that match a query string.'''
    
    url = f"https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/autosuggest/v1.0/SE/SEK/en-GB/"
    querystring = {"query":f"{city}"}

    headers = {
        'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
        'x-rapidapi-key': "085a3ad9afmshd9eee4320cbb30dp15f68cjsn6a30068652ff"
        }

    try:
        airport_data = request_url(url, headers=headers, params=querystring)
        airport_ids = [place["PlaceId"] for place in airport_data["Places"]] #list of XXXX-sky and XXX-sky
        for an_id in airport_ids:
            code = an_id.rstrip('-sky')
            if len(code)==3:
                return code
    except Exception:
        return ''
def covid_info(city, info_choice):
    
  url = "https://covid-api.thinklumo.com/data"

  headers = {'x-api-key': "04fb6415636b4d72b37096978a678f28"}

  try:
    airport_code = get_iata_code(city)
    querystring = {"airport": airport_code}

    data = request_url(url, headers=headers, params=querystring)
  except:
    return f"no information found for {city}"

  city = data['airport']['city']
  country = data['airport']['country_name']

  travel_info_latest = data['covid_info']['entry_exit_info'][-1] # the last dict/item is the latest

  if info_choice == 'entry':
    info = f"{info_choice} requirement for {city}, {country}: "
    info += travel_info_latest['travel_restrictions']
      
  if info_choice == 'quarantine':
    info = f"{info_choice} requirement for {city}, {country}: "
    info += travel_info_latest['quarantine']
      
  if info_choice == 'testing':
    info = f"{info_choice} requirement for {city}, {country}: "
    info += travel_info_latest['testing']

  if "No summary available - please follow the link to learn more." in info:
        info += '  '+travel_info_latest['source']

  return info

@app.route("/search_flights", methods=['POST'])
def search_flights():

    # Read predicates from TDM
    payload = request.get_json()

    city_from = read_facts("city_from", payload)
    city_to = read_facts("city_to", payload)
    month_or_phrase = read_facts("month_or_phrase_from", payload, 'v' )
    day = read_facts("day_from", payload, 'v') # daystr or ""
    if day:
      day = day.strip('d0')
    year = read_facts("year_from", payload, 'v') # yearstr or ""
    if year:
      year = year.strip('y')

    max_price = read_facts('max_price', payload) # number_str
    max_price = None if (not max_price or max_price=='no limit') else float(max_price) # convert to float/None
    direct_choice = read_facts('direct_choice', payload, 'v') # direct_only/non_direct_only/both/""
    direct_only = True if direct_choice=='direct_only' else False 

    # testout = ' | '.join((city_from, city_to, day, month_or_phrase, year))
    # return query_response(value=testout, grammar_entry=None)

    # check cities
    city_id_from, city_id_to = get_airport_id(city_from), get_airport_id(city_to) # airport code or ""
    if not city_id_from or not city_id_to:
      out = f"no airport near {city_from} or {city_to}"
      return query_response(value=out, grammar_entry=None)

    #check dates
    datestr = preds_to_datestr(day, month_or_phrase, year) # predicates => '(d) Month (yyyy)' or phrase
    date_from_fmt = parse_said_date(datestr) # string => 'yyyy-mm-dd'/None
    if not date_from_fmt: # wrong date_from fmt, or date_to given but in wrong fmt
      return query_response(value='no result because of wrong date format', grammar_entry=None)

    # Get list of searched flights and save to a file
    flights = quote_flights(city_id_from, city_id_to, date_from_fmt, 
                            max_price=max_price, direct_only=direct_only)
    save_flights(flights)

    if not flights: # if []
      out = "None"
    else:
      summary = summarize_flights(flights)
      show_date = True if len(date_from_fmt.split('-'))!=3 else False # False if given a yyyy-mm-dd
      first = '; the cheapest is ' + read_the_flight(flights, show_date=show_date)
      out = summary+first
    return query_response(value=out, grammar_entry=None)

@app.route("/filter_flights", methods=['POST'])
def filter_flights():
    payload = request.get_json()
    
    max_price = read_facts('max_price', payload, 'gr') # number_str
    max_price = None if (not max_price or max_price=='no limit') else float(max_price) # convert to float/None
    direct_choice = read_facts('direct_choice', payload, 'v') # direct_only/non_direct_only/both/""

    try:
      flights = load_saved_flights() # load from previously saved results
      if not flights: # if []
        out = "None"
        return query_response(value=out, grammar_entry=None)
      
      # filter
      if max_price:
        flights = [f for f in flights if f['price']<=max_price]
      if direct_choice:
        if direct_choice=='direct_only':
          flights = [f for f in flights if f['direct']=='direct']
        elif direct_choice=='non_direct_only':
          flights = [f for f in flights if f['direct']=='non-direct']
      
      # summerize
      on_same_date = len(set([f['date'] for f in flights]))==1
      summary = summarize_flights(flights)
      show_date = not on_same_date # True if flights are on various dates
      first = '; the first is ' + read_the_flight(flights, show_date=show_date)
      out = summary+first
    
    except Exception:
      out = "None"
    
    return query_response(value=out, grammar_entry=None)

@app.route("/set_currency", methods=['POST'])
def set_currency():
    payload = request.get_json()
    
 
    currency_now = get_currency()
    new_currency = read_facts('currency_to_set', payload, 'v')
    # msg = f'currency to be set from "{currency_now}"" to "{new_currency}"'
    # logger.info(msg)
    # try: # eg (Swedish Krona)=>'SEK' and save to file
    new_currency = lookup_currency_code(new_currency)
    with open('currency.txt', 'w') as f:
      f.write(new_currency)
    # except KeyError:
    #   msg = f'cannot find "{new_currency}"'
    #   pass
    

    # msg = f'currency set from {currency_now} to {get_currency()}'
    # logger.info(msg)
    return action_success_response()


@app.route("/get_covid_info", methods=['POST'])
def get_covid_info():
    payload = request.get_json()
    
    city = read_facts('city_to', payload, 'gr') 
    info_choice = read_facts('info_choice', payload, 'v') 

    out = covid_info(city, info_choice) # entry/qurantine/testing info of place or 'no information found'
    return query_response(value=out, grammar_entry=None)

@app.route("/dummy_query_response", methods=['POST'])
def dummy_query_response():
    response_template = environment.from_string("""
    {
      "status": "success",
      "data": {
        "version": "1.1",
        "result": [
          {
            "value": "dummy",
            "confidence": 1.0,
            "grammar_entry": null
          }
        ]
      }
    }
     """)
    payload = response_template.render()
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending dummy query response to TDM", response=response)
    return response


@app.route("/action_success_response", methods=['POST'])
def action_success_response():
    response_template = environment.from_string("""
   {
     "status": "success",
     "data": {
       "version": "1.1"
     }
   }
   """)
    payload = response_template.render()
    response = app.response_class(
        response=payload,
        status=200,
        mimetype='application/json'
    )
    logger.info("Sending successful action response to TDM", response=response)
    return response
