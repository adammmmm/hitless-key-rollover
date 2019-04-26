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

with open('temp.j2', mode="w") as twr:
    for i in range(52):
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
            conf.commit(timeout=120, comment=f"Created {data['KEYCHAIN-NAME']} keychain")
    except Exception as err:
        print(f"PyEZ configuration exception, {err}")
        sys.exit(1)
try:
    os.remove("temp.j2")
except OSError as err:
    print(f"Failed to delete temporary template, {err}")
