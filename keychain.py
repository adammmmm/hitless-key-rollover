#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import logging
import os
import random
import string
import sys
from datetime import datetime, timedelta

import yaml
from jinja2 import Template
from jnpr.junos import Device
from jnpr.junos.utils.config import Config

lgr = logging.getLogger('keychain')
lgr.setLevel(logging.INFO)

logfh = logging.FileHandler('keychain.log')
logfh.setLevel(logging.INFO)

frmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logfh.setFormatter(frmt)
lgr.addHandler(logfh)

DATA = {}
used_id = []
ntp = []


def create_keychain_dict():
    for index in range(52):
        DATA["CKN" + str(index)] = generate_hex(64)
        DATA["CAK" + str(index)] = generate_hex(32)
        DATA["ROLL" + str(index)] = generate_time(index).strftime('%Y-%m-%d.%H:%M:%S')


def generate_hex(self):
    ''' Helper function to return a hex string of passed length'''
    rand = ''.join(random.SystemRandom().choice(string.hexdigits) for _ in range(self))
    return str.lower(rand)


def generate_time(self):
    ''' Helper function to return timedeltas from passed id '''
    next_time = datetime.now() + timedelta(hours=data["ROLLINTERVAL"])
    add_time = next_time + (timedelta(hours=data["ROLLINTERVAL"])*self)
    return add_time


def remove_template():
    try:
        os.remove('temp.j2')
    except OSError as exc:
        print(f'Failed to delete temporary template, {exc}')


def check_keychain():
    ''' Sanity checks and needed information for updating the keychain '''
    for router in data["HOSTS"]:
        print(f'Checking {router}')
        try:
            with Device(host=router, user=data["USER"], passwd=data["PASS"], port=22) as dev:
                uptime_info = dev.rpc.get_system_uptime_information({"format": "json"})
                time_source = uptime_info["system-uptime-information"][0]["time-source"]
                if time_source[0]["data"] == ' NTP CLOCK ':
                    ntp.append('yes')
                hakr_dict = dev.rpc.get_hakr_keychain_information({"format": "json"})
                if hakr_dict:
                    for keychains in hakr_dict["hakr-keychain-information"]:
                        for key_id in keychains["hakr-keychain"]:
                            if key_id["hakr-keychain-name"][0]["data"] == data["KEYCHAIN-NAME"]:
                                hkask = key_id["hakr-keychain-active-send-key"][0]["data"]
                                hkark = key_id["hakr-keychain-active-receive-key"][0]["data"]
                                hknsk = key_id["hakr-keychain-next-send-key"][0]["data"]
                                hknrk = key_id["hakr-keychain-next-receive-key"][0]["data"]
                                hknkt = key_id["hakr-keychain-next-key-time"][0]["data"]
                                if hkask == hkark:
                                    if hknsk and hknrk and hknkt == 'None':
                                        used_id.append(hkask)
                                    else:
                                        print(f'Next send key {hknsk}, next receive key {hknrk}, rolling over in {hknkt}')
                                        sys.exit(0)
                                else:
                                    print(f'Send key: {hkask}, Receive key: {hkark}')
                                    sys.exit(1)
        except KeyError:
            print(f'PyEZ checking exception, a keychain is not configured, try init.py')
            sys.exit(1)
        except Exception as exc:
            print(f'PyEZ checking exception, {exc}')
            sys.exit(1)

    if len(used_id) == len(data["HOSTS"]):
        if len(set(used_id)) == 1:
            print(f'All routers replied with the same key id: {used_id[0]}')
        else:
            print(f'Router key id sync issue, got: {set(used_id)}')
            sys.exit(1)
    else:
        print(f'Only got an id from {len(used_id)} out of {len(data["HOSTS"])} devices, make sure KEYCHAIN-NAME is correct.')
        sys.exit(1)

    if len(ntp) == len(data["HOSTS"]):
        print('NTP Configured on all hosts')
    else:
        print('NTP Not configured on all hosts')
        if data["NTP"]:
            sys.exit(1)


def create_keychain():
    ''' Create the keychain without any previous checks or input '''
    with open('temp.j2', mode='w') as twr:
        for index in range(51):
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} secret {{{{CAK{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} key-name {{{{CKN{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} start-time "{{{{ROLL{index}}}}}"\n')

    with open('temp.j2') as t_fh:
        t_format = t_fh.read()

    template = Template(t_format)

    if data["LOGGING"]:
        lgr.info(template.render(DATA))

    for router in data["HOSTS"]:
        print(f'Configuring {router}')
        try:
            with Device(host=router, user=data["USER"], passwd=data["PASS"], port=22) as dev:
                conf = Config(dev)
                conf.load(template.render(DATA), format='set')
                conf.commit(timeout=120, comment=f'Created {data["KEYCHAIN-NAME"]} keychain')
        except Exception as exc:
            print(f'PyEZ configuration exception, {exc}')
            sys.exit(1)


def update_keychain():
    ''' Update the keychain with information from the checks '''
    with open('temp.j2', mode='w') as twr:
        for index in range(51):
            if index >= int(used_id[0]):
                twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index+1} secret {{{{CAK{index}}}}}\n')
                twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index+1} key-name {{{{CKN{index}}}}}\n')
                twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index+1} start-time "{{{{ROLL{index}}}}}"\n')
                continue
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} secret {{{{CAK{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} key-name {{{{CKN{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {index} start-time "{{{{ROLL{index}}}}}"\n')

    with open('temp.j2') as t_fh:
        t_format = t_fh.read()

    template = Template(t_format)

    if data["LOGGING"]:
        lgr.info(template.render(DATA))

    for router in data["HOSTS"]:
        print(f'Configuring {router}')
        try:
            with Device(host=router, user=data["USER"], passwd=data["PASS"], port=22) as dev:
                conf = Config(dev)
                conf.load(template.render(DATA), format='set')
                conf.commit(timeout=120, comment=f'Updated {data["KEYCHAIN-NAME"]} keychain')
        except Exception as exc:
            print(f'PyEZ configuration exception, {exc}')
            sys.exit(1)


if __name__ == '__main__':
    with open('data.yml') as fh:
        data = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    if data["ROLLINTERVAL"] <= 1:
        print('Increase the ROLLINTERVAL in data.yml')
        sys.exit(0)

    if len(sys.argv) == 2:
        if sys.argv[1] == 'init':
            create_keychain_dict()
            create_keychain()
            remove_template()
        else:
            print('Use no arguments to update the keychain or "init" to create an initial keychain')
    else:
        check_keychain()
        create_keychain_dict()
        update_keychain()
        remove_template()
