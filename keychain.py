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
from jnpr.junos.utils.start_shell import StartShell

lgr = logging.getLogger('keychain')
lgr.setLevel(logging.INFO)

logfh = logging.FileHandler('keychain.log')
logfh.setLevel(logging.INFO)

frmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logfh.setFormatter(frmt)
lgr.addHandler(logfh)


def generate_hex(self):
    ''' Helper function to create hex string of passed length'''
    rand = ''.join(random.SystemRandom().choice(string.hexdigits) for _ in range(self))
    return str.lower(rand)

def generate_time(self):
    ''' Helper function to calculate timedeltas '''
    nexttime = datetime.now() + timedelta(hours=data['ROLLINTERVAL'])
    addtime = nexttime + (timedelta(hours=data['ROLLINTERVAL']) * self)
    return addtime

with open("data.yml") as fh:
    data = yaml.load(fh.read(), Loader=yaml.SafeLoader)

if data['ROLLINTERVAL'] <= 1:
    print("Increase the ROLLINTERVAL in data.yml")
    sys.exit(0)

DATA = {}
for i in range(52):
    DATA["CKN" + str(i)] = generate_hex(64)
    DATA["CAK" + str(i)] = generate_hex(32)
    DATA["ROLL" + str(i)] = generate_time(i).strftime('%Y-%m-%d.%H:%M:%S')

usedid = []

for router in data['HOSTS']:
    print(f"Checking {router}")
    try:
        with Device(host=router, user=data['USER'], passwd=data['PASS'], port=22) as dev:
            with StartShell(dev) as ss:
                tupledata = ss.run('cli -c "show security keychain | display json | no-more"')
                listdata = list(tupledata)
                liststr = listdata[1]
                # As shell mode shows both the command as first line and a prompt as last, both non-json, we need to remove them
                nofirstorlastline = '\n'.join(liststr.split('\n')[1:-1])
                jsoned = json.loads(nofirstorlastline)
                jsonedkeychain = jsoned['hakr-keychain-information'][0]['hakr-keychain']
                for keyid in jsonedkeychain:
                    if keyid['hakr-keychain-name'][0]['data'] == data['KEYCHAIN-NAME']:
                        hkask = keyid['hakr-keychain-active-send-key'][0]['data']
                        hkark = keyid['hakr-keychain-active-receive-key'][0]['data']
                        hknsk = keyid['hakr-keychain-next-send-key'][0]['data']
                        hknrk = keyid['hakr-keychain-next-receive-key'][0]['data']
                        hknkt = keyid['hakr-keychain-next-key-time'][0]['data']
                        if hkask == hkark:
                            if hknsk and hknrk and hknkt == "None":
                                usedid.append(hkask)
                            else:
                                print(f"Next send key {hknsk}, next receive key {hknrk}, rolling over in {hknkt}")
                                sys.exit(0)
                        else:
                            print(f"Send key: {hkask}, Receive key: {hkark}")
                            sys.exit(1)
                    else:
                        print(f"Keychain {data['KEYCHAIN-NAME']} not found")
                        sys.exit(1)
    except Exception as err:
        print(f"PyEZ checking exception, {err}")
        sys.exit(1)

if len(usedid) == len(data['HOSTS']):
    if len(set(usedid)) == 1:
        print(f"All routers replied with the same key id: {usedid[0]}")
    else:
        print(f"Router key id sync issue, got: {set(usedid)}")
        sys.exit(1)
else:
    print(f"Only got a reply from {len(usedid)} out of {len(data['HOSTS'])} devices")
    sys.exit(1)

with open('temp.j2', mode="w") as twr:
    for i in range(52):
        if i == int(usedid[0]):
            continue
        twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {i} secret {{{{CAK{i}}}}}\n')
        twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {i} key-name {{{{CKN{i}}}}}\n')
        twr.write(f'set security authentication-key-chains key-chain {data["KEYCHAIN-NAME"]} key {i} start-time "{{{{ROLL{i}}}}}"\n')

with open('temp.j2') as t_fh:
    t_format = t_fh.read()

template = Template(t_format)
if data['LOGGING']:
    lgr.info(template.render(DATA))

for router in data['HOSTS']:
    print(f"Configuring {router}")
    try:
        with Device(host=router, user=data['USER'], passwd=data['PASS'], port=22) as dev:
            conf = Config(dev)
            conf.load(template.render(DATA), format='set')
            conf.commit(comment=f"Updated {data['KEYCHAIN-NAME']} keychain")
    except Exception as err:
        print(f"PyEZ configuration exception, {err}")
        sys.exit(1)
try:
    os.remove("temp.j2")
except OSError as err:
    print(f"Failed to delete temporary template, {err}")
