# |-----------------------------------------------------------------------------
# |            This source code is provided under the Apache 2.0 license      --
# |  and is provided AS IS with no warranty or guarantee of fit for purpose.  --
# |                See the project's LICENSE.md for details.                  --
# |           Copyright Refinitiv 2019. All rights reserved.                  --
# |-----------------------------------------------------------------------------

# !/usr/bin/env python
""" Example of requesting Reuters domain Models using RDP Library with Views / Streaming / Snapshot """

import json
import time
from collections import defaultdict

import refinitiv.dataplatform as rdp

# Global default variables
simple_ric_list = []  # List of RICs to request
domain_ric_list = []  # List of RICs with Domain specified
view_list = []  # List of Fields (FIDs or Names) to use in View Request
domain_model = None  # Websocket interface defaults to MarketPrice if not specified
service_name = None  # EDP or ADS typically has a default service configured
snapshot = False  # Make Snapshot request (rather than the default streaming)
dump_rcvd = False  # Dump messages received from server
dump_status = False  # Dump out any Status Msgs received from server
auto_exit = False  # Exit once Refresh (or Status closed) received for all requests

start_time = 0  # Time when first Market Data request made
request_cnt = 0  # Number of Data Items requested
image_cnt = 0  # Data Refresh messages received
update_cnt = 0  # Update messages received
status_cnt = 0  # Status messages received
closed_cnt = 0  # Specifically Closed status message (e.g. item not found)
shutdown_app = False  # flag to indicate shutdown


# Dump some basic stats to console
def print_stats():
    global image_cnt, update_cnt, status_cnt, pingCnt, start_time
    elapsed = 0
    if start_time != 0:
        elapsed = time.time() - start_time
    print("Stats; Refresh: {} \tUpdates: {} \tStatus: {} \tElapsed Time: {:.2f}secs"
          .format(image_cnt, update_cnt, status_cnt, elapsed))


# Data request related parameters
def set_request_attr(service, ric_list, rdm, snap, domain_list):
    global simple_ric_list, domain_model, snapshot, domain_ric_list, service_name
    service_name = service
    simple_ric_list = ric_list
    if rdm:
        domain_model = rdm
    else:
        domain_model = 'MarketPrice'
    snapshot = snap
    domain_ric_list = domain_list


# View used to request Field filtering by the server
def set_view_list(v_list):
    global view_list
    view_list = v_list
    # print("Set view_list to", view_list, "from", v_list)


# Attempt clean shutdown
def cleanup():
    global shutdown_app
    shutdown_app = True  # signal to main loop to exit


# Process the JSON message received from server
def process_message(message_json):
    global image_cnt, update_cnt, status_cnt, closed_cnt, shutdown_app

    if dump_rcvd:
        print("RCVD: ")
        print(json.dumps(message_json, sort_keys=True, indent=2, separators=(',', ':')))

    message_type = message_json['Type']
    message_domain = "MarketPrice"  # Default - we don't get Domain in MarketPrice message
    if 'Domain' in message_json:
        message_domain = message_json['Domain']

    # Process different Message Types
    if message_type == "Refresh":
        if not (('Complete' in message_json) and  # Default value for Complete is True
                (not message_json['Complete'])):  # Only count Refresh If 'Complete' not present or True
            image_cnt += 1
    elif message_type == "Update":
        update_cnt += 1
    elif message_type == 'Error':  # Oh Dear - server did not like our Request
        print("ERR: ")
        print(json.dumps(message_json, sort_keys=True, indent=2, separators=(',', ':')))
        cleanup()

    # Cleanup and exit - if auto_exit and we have received response to all requests
    if auto_exit and (request_cnt == image_cnt + closed_cnt):
        cleanup()


def on_status(item, status_msg):
    global status_cnt, closed_cnt
    if dump_status:  # if dumpRCVD set then Status will be dumped elsewhere
        print(item.name, status_msg)
    status_cnt += 1
    # Was the item request rejected by server & stream Closed?
    if item.state == rdp.StreamState.Closed:
        closed_cnt += 1
    if auto_exit and (request_cnt == image_cnt + closed_cnt):
        cleanup()


# Invoked from __main__ method
def request_data(req_session):
    global start_time

    start_time = time.time()
    """ Send items request """
    if domain_ric_list:
        send_multi_domain_data_request(req_session)
    else:
        send_single_domain_data_request(req_session, domain_model, simple_ric_list)


# User specified '-ef' and file with multiple domain types
# So I group RICs by Domain before requesting
def send_multi_domain_data_request(req_session):
    """ Group Market Data request by Domain type """
    # Note: that I dont need to group by domain, I could just
    # iterate through the file and request each one individually
    # but I felt this was neater!
    grouped = defaultdict(list)
    # Create lists grouped by Domain Type
    for domain, ric in domain_ric_list:
        grouped[domain].append(ric)

    # For each Domain type group, call the data request method
    for i, (domain, rics) in enumerate(grouped.items()):
        send_single_domain_data_request(req_session, domain, rics)


# Make a request for all the RICs in ric_list
# with any specified Views and Domains etc. 
def send_single_domain_data_request(req_session, req_domain, ric_list):
    global request_cnt
    """ Create and send Market Data request for a single Domain type"""
    # increment the data items requested count
    request_cnt += len(ric_list)
    for ric in ric_list:
        stream = rdp.ItemStream(session=req_session,
                                domain=req_domain,
                                name=ric,
                                fields=view_list,
                                service=service_name,
                                on_refresh=lambda s, msg: process_message(msg),
                                on_update=lambda s, msg: process_message(msg),
                                on_status=lambda s, msg: on_status(s, msg))
        # Streaming or snapshot?
        stream.open(with_updates=not snapshot)

