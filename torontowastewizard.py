"""
Toronto Waste Wizard skill for Alexa
(c) 2018 Laumoda Inc
"""

from __future__ import print_function
import urllib.request
import csv
from datetime import datetime, timedelta
import json
from dateutil import tz
import calendar
import codecs
import re
import logging
import string
import shapefile
from shapely.geometry import Point
from shapely.geometry import shape
from shapely.geometry import Polygon
import pyproj
import requests

NOT_TORONTO = "Not Toronto"
PERMISSION_DENIED = "Permission Denied"
NOT_FOUND = "Not Found"
SITE_NOT_AVAILABLE = "Site not Available"
TRY_AGAIN = "Try Again"
OK = "OK"

# --------------- Helper functions ---------------------------------------------

def html_to_text(data):
    """ custom html to text parser
    """

    # unescape 
    data = data.replace("&lt;", "<")
    data = data.replace("&gt;", ">")
    data = data.replace("&amp;", "&")
    data = data.replace("&#x27;", "'")

    # remove the newlines
    data = data.replace("\n", " ")
    data = data.replace("&nbsp;", " ")

    # replace consecutive spaces into a single one
    data = " ".join(data.split())   

    # remove all the tags
    p = re.compile(r'<[^<]*?>')
    data = p.sub('', data)

    return data

def ssml_to_text(data):
    """ custom ssml to text parser
    """

    # remove all the tags
    p = re.compile(r'<[^<]*?>')
    data = p.sub('', data)

    return data

# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output_text, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output_text
        },
        'card': {
            'type': 'Simple',
            'title': title,
            'content': output_text
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_SSML_response(title, output_ssml, reprompt_ssml, should_end_session):
    return {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': output_ssml
        },
        'card': {
            'type': 'Simple',
            'title': title,
            'content': ssml_to_text(output_ssml)
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'SSML',
                'ssml': reprompt_ssml
            }
        },
        'shouldEndSession': should_end_session
    }


def build_permission_request(output_text):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output_text
        },
        'card': {
            'type': 'AskForPermissionsConsent',
            'permissions': [
                "read::alexa:device:all:address"
        ]
        },
        'shouldEndSession': True
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }



# --------------- Style guide --------------------------------------------------

# module_name, package_name, ClassName, method_name, ExceptionName
# function_name, GLOBAL_CONSTANT_NAME, global_var_name, instance_var_name
# function_parameter_name, local_var_name


# --------------- Custom functions ---------------------------------------------

def get_alexa_location(context):

    # https://developer.amazon.com/docs/custom-skills/device-address-api.html
    # https://data-dive.com/alexa-get-device-location-from-custom-skill
    
    # {'addressLine1': '5 Blong av', 'addressLine2': None, 'addressLine3': None, 
    # 'districtOrCounty': None, 'stateOrRegion': 'Ontario', 'city': 'Toronto', 
    # 'countryCode': 'CA', 'postalCode': 'M4M 1P1'}

    address_line_1 = NOT_FOUND
    
    if 'deviceId' not in context['System']['device']:
        print("Run from simulator")
        # return "5 Blong av"
        return NOT_FOUND

    if 'apiAccessToken' not in context['System']:
        print("No apiAccessToken")
        return PERMISSION_DENIED

    api_end_point = context['System']['apiEndpoint']
    device_id = context['System']['device']['deviceId']
    url = "{}/v1/devices/{}/settings/address".format(api_end_point, device_id) 
    print("url is {}".format(url))
    
    api_access_token = context['System']['apiAccessToken']
    header = {'Accept': 'application/json',
             'Authorization': 'Bearer {}'.format(api_access_token)}
    print("header is {}".format(header))
    
    r = requests.get(url, headers=header)
    print("status_code is {}".format(r.status_code))
    if r.status_code == 200:
        # 200 OK	Successfully got the address associated with this deviceId.
        # default postalCode value of “98109” may be returned
        print(r.json())
        location = r.json()
        if location["city"] == "Toronto":
            address_line_1 = location["addressLine1"]
        else:
            address_line_1 = NOT_TORONTO
    elif r.status_code == 204:
        # 204 No Content	The query did not return any results.
        print("No Content")
        address_line_1 = NOT_FOUND
    elif r.status_code == 403:
        # 403 Forbidden	The authentication token is invalid or doesn't have access to the resource.
        print("permission denied")
        address_line_1 = PERMISSION_DENIED
    else:
        # 405 Method Not Allowed	The method is not supported.
        # 429 Too Many Requests	The skill has been throttled due to an excessive number of requests.
        # 500 Internal Error	An unexpected error occurred
        print("other error")
        address_line_1 = TRY_AGAIN

    return address_line_1


def build_coordinates_response(status, lat, lng):
    return {
        'coordinates': {
            'lat': lat,
            'lng': lng
        },
        'status': status
    }

def get_coordinates(address_line_1):

    # https://developers.google.com/maps/documentation/geocoding/intro
    # "lat": 43.66456248029149,
    # "lng": -79.33628841970848,

    # Clean up address_line_1 for URL
    special_chars = ' '
    permitted_chars = string.digits + string.ascii_letters + special_chars
    address_line_1 = "".join(c for c in address_line_1 if c in permitted_chars)
    address_line_1 = address_line_1.replace(" ", "+")

    # build maps.googleapi.com URL
    google_api_secret_key = "AIzaSyB8iIwZFu_POubyaqurWmeRTNx5PpF_o_0"
    url = "https://maps.googleapis.com/maps/api/geocode/json?address=" + \
          address_line_1 + \
          ",+Toronto,+ON&key=" + \
          google_api_secret_key
    print("googleapi url " + url)

    request = urllib.request.Request(url)
    try:
        response=urllib.request.urlopen(request)
        data = json.loads(response.read())

    except Exception as e:
        return build_coordinates_response(SITE_NOT_AVAILABLE, 0, 0)
            
    if data['status'] != "OK":
        return build_coordinates_response(NOT_FOUND, 0, 0)
        
    results = data['results']
    lat = results[0]['geometry']['location']['lat']
    lng = results[0]['geometry']['location']['lng']
    print("lat is {} and lng is {}".format(lat, lng))
    
    return build_coordinates_response(OK, lat, lng)
    

def get_area_name(location):

    # Get Curbside Collection Daytime shapefile
    url_shp = "http://www.laumoda.com/alexa/skills/torontowastewizard/cityprj_res_wastecollect_schedule_mtm3_b.shp"
    url_dbf = "http://www.laumoda.com/alexa/skills/torontowastewizard/cityprj_res_wastecollect_schedule_mtm3_b.dbf"
    request_shp = urllib.request.Request(url_shp)
    request_dbf = urllib.request.Request(url_dbf)
    
    try:
        response_shp=urllib.request.urlopen(request_shp)
        response_dbf=urllib.request.urlopen(request_dbf)
        shp = shapefile.Reader(shp=response_shp, dbf=response_dbf)
        print("read in both shp and dbf of shapefile")
        
    except Exception as e:
        print("error opening shapefile .shp")
        return SITE_NOT_AVAILABLE

    # Use coordinates to look up polygon in shapefile 
    wgs84 = pyproj.Proj("+init=EPSG:4326")
    cityprj = pyproj.Proj("+proj=tmerc +x_0=304800 +lon_0=-79.5 +k_0=0.9999 +ellps=clrk66")
    lng, lat = pyproj.transform(wgs84,cityprj,location["lng"],location["lat"])
    device_point = Point(lng, lat)
    print("device point {}".format(device_point))

    area_name = NOT_FOUND
    all_shapes = shp.shapes()
    all_records = shp.records()
    
    for index, my_shape in enumerate(all_shapes):
        if device_point.within(shape(my_shape)):
    	    print("we have a match")
    	    area_name = all_records[index][2]
    	    area_name = area_name.replace(" ","")
    	    print("name of record {} is {}".format(index, area_name))
    	    break
        
    return area_name
    
def build_collection_response(date, items):
    return {
        'date': date,
        'items': items
    }

def build_collection_date(query_date, tomorrow_date, next_collection_date):
    if next_collection_date == query_date:
        today_tomorrow = "today, "
    elif next_collection_date == tomorrow_date:
        today_tomorrow = "tomorrow, "
    else:
        today_tomorrow = ""

    date_output = today_tomorrow + \
                  next_collection_date.strftime("%A %B %d")
    return date_output

def build_collected_items(items):
    items_count = len(items)
    if items_count == 0:
        collected_items = "nothing"
    elif items_count == 1:
        collected_items = items[0]
    elif items_count == 2:
        collected_items = ' and '.join(items)
    else:
        collected_items = ', '.join(items[:-1]) + ', and ' + items[-1]
    return collected_items


def get_collection_info(collection_area):

    # Assume device timezone is EST
    utc_now = datetime.utcnow()
    query_date = (utc_now - timedelta(hours=5)).date()
    tomorrow_date = (utc_now + timedelta(hours=19)).date()

    # for testing
    # test_collection_date = (datetime.strptime('Feb 20 2018  1:33PM', '%b %d %Y %I:%M%p')).date()
    # Feb22_date = (datetime.strptime('Feb 22 2018  1:33PM', '%b %d %Y %I:%M%p')).date()

    # Get schedule data from Toronto Open Data
    # Solid Waste Daytime Curbside Collection Areas
    url = "https://www.toronto.ca/ext/open_data/catalog/data_set_files/Pickup_Schedule_2018.csv"
    request = urllib.request.Request(url)

    try:
        response=urllib.request.urlopen(request)
        contents = csv.reader(codecs.iterdecode(response, 'utf-8'))

    except Exception as e:
        return build_collection_response(SITE_NOT_AVAILABLE, SITE_NOT_AVAILABLE)

    items = []
    next_collection_date = NOT_FOUND
    for row in contents:
        if collection_area in row[0]:
            week_starting = (datetime.strptime(row[1], "%m/%d/%y")).date()
            #if week_starting == Feb22_date:
            #    week_starting = test_collection_date
            if week_starting >= query_date:
                next_collection_date = week_starting
                print("next collection date {}".format(next_collection_date))
                if row[2] != "0":
                    items.append("green bin")
                if row[3] != "0":
                    items.append("garbage")
                if row[4] != "0":
                    items.append("recycling")
                if row[5] != "0":
                    items.append("yard waste")
                if row[6] != "0":
                    items.append("christmas tree")
                break

    if next_collection_date == NOT_FOUND:
        return build_collection_response(NOT_FOUND, NOT_FOUND)

    collected_items = build_collected_items(items)
    date_output = build_collection_date(query_date, tomorrow_date, next_collection_date)

    return build_collection_response(date_output, collected_items)


def get_waste_material(intent):

    waste_material = NOT_FOUND
    if 'slots' in intent:
        if 'WasteMaterial' in intent['slots']:
            if 'value' in intent['slots']['WasteMaterial']:
                waste_material = intent['slots']['WasteMaterial']['value'].strip()

    print("request intent for {}".format(waste_material))
    if waste_material == "":
        waste_material = NOT_FOUND
            
    return waste_material

def build_disposal_response(item, instructions, status):
    return {
        'item': item,
        'instructions': instructions,
        'status': status
    }

def get_disposal_instructions(waste_material):

    # Get disposal instructions from toronto.ca Garbage and Recycling Data Catalogue
    url = "https://secure.toronto.ca/cc_sr_v1/data/swm_waste_wizard_APR?limit=1000"
    request = urllib.request.Request(url)
    try:
        response=urllib.request.urlopen(request)
        data = json.loads(response.read())
    except Exception as e:
        print("error occurred getting waste wizard catalogue {}".format(str(e)))
        return build_disposal_response(None, None, SITE_NOT_AVAILABLE)

    close_match = False
    for d in data:
        category = d['category']
        keywords = d['keywords'].split(",")
        body = d['body']
        for keyword in keywords:
            keyword = keyword.lower().strip()
            if keyword == waste_material:
                print("exact match found")
                return build_disposal_response(waste_material, html_to_text(body), OK)

            elif keyword.find(waste_material) != -1:
                print("close item=<{}> keyword=<{}>".format(waste_material, keyword))
                close_instructions = html_to_text(body)
                close_item = keyword
                close_match = True # continue iterating to search for exact match

    if close_match == True:
        return build_disposal_response(close_item, close_instructions, OK)

    return build_disposal_response(None, None, NOT_FOUND)
    
    
# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """

    session_attributes = {}
    card_title = "Welcome"
    should_end_session = False
    
    output_ssml = "<speak>" \
                  "<p>Welcome to the Toronto Waste Wizard! </p>" \
                  "<p>You can find out about your collection schedule by asking </p>" \
                  "<p>'Is it recycling this week?' </p>"\
                  "<p>Or, you can ask about waste materials, for example, </p>" \
                  "<p>'Look up aluminum foil' </p>" \
                  "<p>Go ahead and give it a try!</p>" \
                  "</speak>"
                  
    reprompt_ssml = "<speak>" \
                    "<p>I'm sorry, I didn't understand.  Why don't you try asking, </p>" \
                    "<p>'Is it recycling this week?'</p>" \
                    "</speak>"

    return build_response(session_attributes, build_SSML_response(
        card_title, output_ssml, reprompt_ssml, should_end_session))


def handle_session_end_request():
    card_title = "Session Ended"
    output_text = "Thanks for being green!"
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(
        card_title, output_text, None, should_end_session))


def get_schedule_response(intent, context):
    """ Looks up the collection schedule on toronto.ca based on device address
    and prepares the speech to reply to the user.
    """
    session_attributes = {}
    card_title = "Curbside Collection Schedule"
    should_end_session = True

    # Get device address from Device Address API
    device_address_line_1 = get_alexa_location(context)
    if device_address_line_1 == NOT_TORONTO:
        output_text = "I'm sorry, I can only look up collection schedules " \
                      "for Toronto residents." 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif device_address_line_1 == PERMISSION_DENIED:
        output_text = "I'm sorry, I'll need access to your address " \
                      "to look up your collection schedule.  Please see your Alexa app " \
                      "to enable permission."
        return build_response({}, build_permission_request(output_text))
    elif device_address_line_1 == NOT_FOUND:
        output_text = "I'm sorry, I'm having trouble with your address.  I can only " \
                      "look up collection schedules for Toronto residents.  Please " \
                      "check the device location settings in your Alexa app"
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif device_address_line_1 == TRY_AGAIN:
        output_text = "I'm sorry, I'm having trouble looking up your address " \
                      "to check your collection schedule.  Please try again later"
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))

    # Geocode device address using Google Maps Geocoding API
    response = get_coordinates(device_address_line_1)
    if response['status'] == SITE_NOT_AVAILABLE:
        output_text = "I'm sorry, I am having trouble getting coordinates for " \
                      "your address to look up your collection schedule. " \
                      "Please try again later" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif response['status'] == NOT_FOUND:
        output_text = "I'm sorry, I am having trouble getting coordinates for " \
                      "your address to look up your collection schedule. " \
                      "Please check your address in your Alexa app" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    coordinates = response['coordinates']

    # Get area_name using coordinates and Curbside Collection Daytime shapefile
    area_name = get_area_name(coordinates)
    if area_name == SITE_NOT_AVAILABLE:
        output_text = "I'm sorry, I am having trouble accessing the City of Toronto " \
                	  "website to look up your collection area. " \
                      "Please try again later" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif area_name == NOT_FOUND:
        output_text = "I'm sorry, I could not match your address to a collection area. " \
                      "Please check your address in your Alexa app"
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))

    # Use area_name to look up Calendar
    collection_info = get_collection_info(area_name)
    if collection_info['date'] == SITE_NOT_AVAILABLE:
        output_text = "I'm sorry, I am having trouble accessing the City of Toronto " \
                      "website to look up your collection schedule. " \
                      "Please try again later" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif collection_info['date'] == NOT_FOUND:
        output_text = "I'm sorry, I can't find the next collection date. " \
                      "Please try again later" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))

    output_text = "The next collection date is " + \
                  collection_info['date'] + \
                  " which includes " + \
                  collection_info['items'] + "."

    return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))


def get_material_response(intent):
    """ Looks up the waste material using the Waste Wizard on toronto.ca
    and prepares the speech to reply to the user.
    """
    session_attributes = {}
    card_title = "Waste Disposal"
    should_end_session = True

    # Get the waste material from the request intent
    waste_material = get_waste_material(intent)
    if waste_material == NOT_FOUND:
        output_text = "I'm sorry, I didn't understand the material you are asking " \
                      "about.  Can you please repeat your request?"
        should_end_session = False
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))

    # Get disposal instructions from toronto.ca Garbage and Recycling Data Catalogue
    response = get_disposal_instructions(waste_material)
    if response['status'] == SITE_NOT_AVAILABLE:
        output_text = "I'm sorry, I am having trouble accessing the City of Toronto " \
                      "website to look up " + waste_material + ". " + \
                      "Please try again later" 
        return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))
    elif response['status'] == NOT_FOUND:
        output_ssml = "<speak>" \
                      "<p>I'm sorry, I couldn't find " + waste_material + \
                      " on the City of Toronto website.  You can try calling " \
                      "<say-as interpret-as='digits'>311</say-as> and ask the city</p>" \
                      "</speak>"
        return build_response(session_attributes, build_SSML_response(
        card_title, output_ssml, None, should_end_session))

    output_text = "Here's what the City of Toronto says about " + \
                    response['item'] + ". " + \
                    response['instructions'] 
    
    return build_response(session_attributes, build_speechlet_response(
        card_title, output_text, None, should_end_session))



# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """

    print("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they
    want
    """

    print("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session, context):
    """ Called when the user specifies an intent for this skill """

    print("on_intent requestId=" + intent_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    if intent_name == "TWWScheduleIntent":
        return get_schedule_response(intent, context)
    elif intent_name == "TWWMaterialIntent":
        return get_material_response(intent)
    elif intent_name == "AMAZON.HelpIntent":
        return get_welcome_response()
    elif intent_name == "AMAZON.CancelIntent" or intent_name == "AMAZON.StopIntent":
        return handle_session_end_request()
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here


# --------------- Main handler ------------------

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

    # Prevent unwanted access to this Lambda function
    event_app_id = event['session']['application']['applicationId']
    my_app_id = "amzn1.ask.skill.080bc076-a3bb-45c7-a5d6-1028434a9860"
    if event_app_id != my_app_id:
        raise ValueError("Invalid Application ID: {}".format(event_app_id))


    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'], event['context'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])
