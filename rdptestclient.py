#!/usr/bin/env python
# |-----------------------------------------------------------------------------
# |            This source code is provided under the Apache 2.0 license      --
# |  and is provided AS IS with no warranty or guarantee of fit for purpose.  --
# |                See the project's LICENSE.md for details.                  --
# |           Copyright Refinitiv 2019. All rights reserved.                  --
# |-----------------------------------------------------------------------------

import argparse
import logging.config
import sys
import time

import market_data
import refinitiv.dataplatform as rdp

# Python example that uses the Refinitiv Data Platform library to demonstrate the consumption of realtime data.
# This example is meant to be a simplistic version of the 'rmdstestclient' tool
#  and illustrates a variety of scenarios such as:
#  RDP, ADS or Desktop connection, View Request, Streaming / Snapshot, Reuters Domain Models

# Global Variables
simple_rics = None
ext_rics = None
opts = None
rdp_mode = False
trep_mode = False
desktop_mode = False
my_session = None


# Read RICs from file '-f' option i.e. no domain specified
# so will be used in conjunction with Domain Model parameter
def read_simple_rics_file():
    global simple_rics
    try:
        with open(opts.ric_file, 'r') as f:  # Read one RIC per line from file
            simple_rics = [ric.strip(' \t\n\r') for ric in f]  # and strip any whitespace etc
    except FileNotFoundError as fnf_error:
        print(fnf_error)
        return

    print("RICs from file:", simple_rics)


# Read Domain + RIC from multi domain file '-ef' option
# File contains Domain Model Number and RIC separated by | - one per line e..g
# 6|VOD.L
# 7|BT.L
def read_ext_rics_file():
    global ext_rics
    try:
        with open(opts.ric_file_ext, 'r') as f:
            tmp_ext_rics = f.read().splitlines()  # using read.splitlines to strip \n on end of each RIC
        ext_rics = []
        for xRic in tmp_ext_rics:
            tmp = xRic.split("|")
            try:  # Add entry as Domain number, RIC
                ext_rics.append((int(tmp[0]), str(tmp[1]).strip(' \t\n\r')))  # strip any whitespaces
            except:
                pass
        ext_rics.sort()
        print("SORTED:", ext_rics)
    except FileNotFoundError as fnf_error:
        print(fnf_error)
        return

    # print("Read {} Multi Domain RICs from file: {}".format(len(ext_rics), ext_rics))


# Only one RIC list specifier allowed; -items OR -f OR -ef
def parse_rics():
    global simple_rics
    if opts.itemList:
        simple_rics = opts.itemList.split(',')
        print(simple_rics)
    elif opts.ric_file:
        read_simple_rics_file()
    elif opts.ric_file_ext:
        read_ext_rics_file()


# Do some basic validation of the command line parameters
def validate_options():
    global opts, rdp_mode, trep_mode, desktop_mode

    if not opts.appKey:
        print("AppKey required for all session types")
        return False

    # If password is specified then we are going to attempt RDP session
    if opts.password:
        # Must have a MachinedID/username and AppKey too
        if not opts.user:
            print("For RDP session, Password, MachinedID/username and AppKey are required")
            return False
        rdp_mode = True
        print("RDP mode")
    # If hostname is specified then we are going to attempt a TREP session
    elif opts.host:
        # Must have DACS username and AppKey too
        if not opts.user:
            print("For TREP/Deployed session, Host, DACS username and AppKey are required")
            return False
        trep_mode = True
        print("Deployed (TREP) mode")
    # If hostname or password not specified then go for  a Desktop session (Eikon or Workspace)
    elif not (rdp_mode or trep_mode):
        desktop_mode = True
        print('Desktop (Eikon/Workspace) mode')

    # Ensure only one RIC list /filename specified by user
    ric_lists = (opts.itemList, opts.ric_file, opts.ric_file_ext)
    ric_list_cnt = 0
    for rics in ric_lists:
        if rics is not None:
            ric_list_cnt += 1

    if ric_list_cnt > 1:
        print('Only one RIC list specifier allowed; -items, -f or -ef')
        return False
    elif not ric_list_cnt:
        print('Must specify some RICs using one of the following; -items, -f or -ef')
        return False
    else:
        parse_rics()
        # Check if we parsed some RICs to request. 
        if (not simple_rics) and (not ext_rics):
            print("Was not able to read any RICs from file or command line")
            return False

    # If stats interval is >  specified runtime then reduce interval
    if (opts.exit_time_mins > 0) and (opts.stats_time_secs > (opts.exit_time_mins * 60)):
        opts.stats_time_secs = opts.exit_time_mins * 60

    # Check if Domain has been specified as a numeric value rather than name
    if opts.domain and opts.domain.isdigit():
        print('Only String based Domain allowed e.g. MarketByPrice, MarketByOrder etc')
        return False

    return True


# Parse command line arguments
def parse_args(args=None):
    parser = argparse.ArgumentParser(description='python websocket test client',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-S', dest='service',
                        help='service name to request data from')
    parser.add_argument('-H', dest='host',
                        help='ADS server hostname:port')
    parser.add_argument('-ap', dest='appKey',
                        help='AppKey / ClientID')
    parser.add_argument('-u', dest='user',
                        help='MachinedID/Dacs username for RDP/TREP')
    parser.add_argument('-pw', dest='password',
                        help='RDP user password')
    parser.add_argument('-items', dest='itemList',
                        help='comma-separated list of RICs')
    parser.add_argument('-fields', dest='view_names',
                        help='comma-separated list of Field Names for View')
    parser.add_argument('-md', dest='domain',
                        help='domain model - server defaults to MarketPrice.\
                            Name - MarketPrice, MarketByOrder, MarketByPrice etc')
    parser.add_argument('-f', dest='ric_file',
                        help='simple file of RICs - one per line')
    parser.add_argument('-ef', dest='ric_file_ext',
                        help='multi domain file of numeric domain|RIC - e.g. MarketByPrice|VOD.L')
    parser.add_argument('-t', dest='snapshot',
                        help='Snapshot request',
                        default=False,
                        action='store_true')
    parser.add_argument('-X', dest='dump',
                        help='Output Received Data to console',
                        default=False,
                        action='store_true')
    parser.add_argument('-l', dest='log_filename',
                        help='Redirect console to filename',
                        default=None)
    parser.add_argument('-e', dest='auto_exit',
                        help='Auto Exit after all items retrieved',
                        default=False,
                        action='store_true')
    parser.add_argument('-et', dest='exit_time_mins',
                        help='Exit after time in minutes (0=indefinite)',
                        type=int,
                        default=0)
    parser.add_argument('-st', dest='stats_time_secs',
                        help='Show Statistics interval in seconds',
                        type=int,
                        default=5)
    parser.add_argument('-sos', dest='show_status_msgs',
                        help='Output received Status messages',
                        default=False,
                        action='store_true')
    parser.add_argument('-dbg', dest='enable_debug',
                        help='Output low level debug trace',
                        default=False,
                        action='store_true')

    return parser.parse_args(args)


# Determine Session type and create/open session
def get_session(appkey, host, user, password):
    if desktop_mode:
        return rdp.DesktopSession(
            appkey,
            on_state=lambda session, state, message: print("Desktop session state: ", state, message),
            on_event=lambda session, event, message: print("Desktop session event: ", event, message))
    elif trep_mode:
        return rdp.PlatformSession(
            app_key=appkey,
            grant=None,
            deployed_platform_host=host,
            deployed_platform_username=user,
            on_state=lambda session, state, message: print("Deployed session state: ", state, message),
            on_event=lambda session, event, message: print("Deployed session event: ", event, message))
    else:
        return rdp.PlatformSession(
            appkey,
            rdp.GrantPassword(
                username=user,
                password=password),
            on_state=lambda session, state, message: print("Platform session state: ", state, message),
            on_event=lambda session, event, message: print("Platform session event: ", event, message))


if __name__ == '__main__':
    opts = parse_args(sys.argv[1:])
    # print("Invoked with:", opts)
    if not validate_options():
        print('Exit due to invalid arguments')
        sys.exit(2)

    #  Redirect console to file if log_filename specified
    orig_stdout = sys.stdout
    if opts.log_filename is not None:
        try:
            print('Redirecting console to file "{}"'.format(opts.log_filename))
            sys.stdout = open(opts.log_filename, "w")
        except IOError:
            print('Could not redirect console to file "{}"'.format(opts.log_filename))
            sys.stdout = orig_stdout
            sys.exit(2)

    my_session = get_session(opts.appKey, opts.host, opts.user, opts.password)
    if opts.enable_debug:
        my_session.set_log_level(logging.DEBUG)
    my_session.open()

    market_data.dump_rcvd = opts.dump
    market_data.dump_status = opts.show_status_msgs
    market_data.auto_exit = opts.auto_exit

    # User wants to exit once all item responded to by server
    # So switch to Snapshot mode.
    if opts.auto_exit:
        opts.snapshot = True
        print("AutoExit selected so enabling Snapshot mode too")

    market_data.set_request_attr(opts.service, simple_rics, opts.domain, opts.snapshot, ext_rics)

    if opts.view_names is not None:
        view_list = opts.view_names.split(',')
        market_data.set_view_list(view_list)

    print("Request Data")
    market_data.request_data(my_session)

    try:
        # Determine how often to output basic stats
        stat_time = time.time() + opts.stats_time_secs

        # When should we stop looping and exit
        end_time = None
        if opts.exit_time_mins > 0:  # Are we looping for limited time
            end_time = time.time() + 60 * opts.exit_time_mins
            print("Run for", opts.exit_time_mins, "minute(s)")
        else:
            print("Run indefinitely - CTRL+C to break")

        # Loop forever or until specified end time or shutdown signalled
        while (((opts.exit_time_mins == 0) or (time.time() < end_time))
               and (not market_data.shutdown_app)):

            time.sleep(1)
            # Is is time to print some basic stats?
            if time.time() >= stat_time:
                market_data.print_stats()
                stat_time = time.time() + opts.stats_time_secs

    except KeyboardInterrupt:
        pass
    finally:
        my_session.close()
        market_data.print_stats()

    sys.stdout = orig_stdout
#
#
#
