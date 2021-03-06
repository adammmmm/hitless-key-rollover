#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import random
import sys
from datetime import datetime, timedelta

import yaml
from jinja2 import Template
from jnpr.junos import Device
from jnpr.junos.exception import CommitError, ConfigLoadError, ConnectError
from jnpr.junos.utils.config import Config
from loguru import logger

logger.add("keychain.log", rotation="monthly", enqueue=True)

HEX = "0123456789abcdef"
committed = []
keychain_data = {}
keychain_set = set()
used_id = []
ntp = []


def create_keychain_dict():
    """ Fills the dictionary with CAK/CKN/ROLL values """
    for index in range(32):
        keychain_data["CKN" + str(index)] = generate_hex(64)
        keychain_data["CAK" + str(index)] = generate_hex(64)
        keychain_data["ROLL" + str(index)] = generate_time(index).strftime("%Y-%m-%d.%H:%M:%S")


def check_for_duplicates():
    """ Checks for duplicate CKN/CAK values """
    for entries in keychain_data.values():
        keychain_set.add(entries)
    if len(keychain_data) != len(keychain_set):
        logger.warnning("Duplicate CAK/CKN value, aborting")
        sys.exit(1)


def generate_hex(length):
    """ Helper function to return a hex string of passed length """
    rand = "".join(random.SystemRandom().choice(HEX) for _ in range(length))
    return rand


def generate_time(index):
    """ Helper function to return timedeltas from passed id """
    next_time = datetime.now() + timedelta(hours=config_data["ROLLINTERVAL"])
    add_time = next_time + (timedelta(hours=config_data["ROLLINTERVAL"]) * index)
    return add_time


def remove_template():
    """ Removes the template file """
    try:
        os.remove("temp.j2")
    except OSError as exc:
        logger.error(f"Failed to delete temporary template, {exc}")
        sys.exit(2)


def check_keychain():
    """ Sanity checks and needed information for updating the keychain """
    for router in config_data["HOSTS"]:
        logger.info(f"Checking {router}")
        try:
            with Device(
                host=router,
                user=config_data["USER"],
                ssh_private_key_file=config_data["KEY"],
                port=22,
            ) as dev:
                uptime_info = dev.rpc.get_system_uptime_information({"format": "json"})
                time_source = uptime_info["system-uptime-information"][0]["time-source"]
                if time_source[0]["data"] == " NTP CLOCK ":
                    ntp.append("yes")
                hakr_dict = dev.rpc.get_hakr_keychain_information({"format": "json"})
                if hakr_dict:
                    for keychains in hakr_dict["hakr-keychain-information"]:
                        for key_id in keychains["hakr-keychain"]:
                            if key_id["hakr-keychain-name"][0]["data"] == config_data["KEYCHAIN-NAME"]:
                                hkask = key_id["hakr-keychain-active-send-key"][0]["data"]
                                hkark = key_id["hakr-keychain-active-receive-key"][0]["data"]
                                hknsk = key_id["hakr-keychain-next-send-key"][0]["data"]
                                hknrk = key_id["hakr-keychain-next-receive-key"][0]["data"]
                                hknkt = key_id["hakr-keychain-next-key-time"][0]["data"]
                                if hkask == hkark:
                                    if hknsk and hknrk and hknkt == "None":
                                        used_id.append(hkask)
                                    else:
                                        logger.info(f"Next send key {hknsk}, next receive key {hknrk}, rolling over in {hknkt}")
                                        sys.exit(0)
                                else:
                                    logger.warning(f"Send key: {hkask}, Receive key: {hkark}")
                                    sys.exit(1)
        except KeyError:
            logger.error("PyEZ checking exception, a keychain is not configured, try init")
            sys.exit(2)
        except Exception as exc:
            logger.error(f"PyEZ checking exception, {exc}")
            sys.exit(2)

    if len(used_id) == len(config_data["HOSTS"]):
        if len(set(used_id)) == 1:
            logger.info(f"All routers replied with the same key id: {used_id[0]}")
        else:
            logger.error(f"Router key id sync issue, got: {set(used_id)}")
            sys.exit(2)
    else:
        logger.error(f'Only got an id from {len(used_id)} out of {len(config_data["HOSTS"])} devices, make sure KEYCHAIN-NAME is correct.')
        sys.exit(1)

    if len(ntp) == len(config_data["HOSTS"]):
        logger.info("NTP Configured on all hosts")
    else:
        logger.warning("NTP Not configured on all hosts")
        if config_data["NTP"]:
            logger.warning("Aborting")
            sys.exit(1)


def rollback_changed(devices, failed):
    for router in devices:
        logger.error(f"Rolling back {router}")
        try:
            with Device(
                host=router,
                user=config_data["USER"],
                ssh_private_key_file=config_data["KEY"],
                port=22,
            ) as dev:
                conf = Config(dev, mode="private")
                conf.rollback(rb_id=1)
                conf.commit(comment=f"Rolled back, failure on {failed}")
        except Exception as exc:
            logger.critical(f"PyEZ configuration exception while rolling back, {exc}")
            sys.exit(2)


def create_keychain():
    """ Create the keychain without any previous checks or input """
    with open("temp.j2", mode="w") as twr:
        for index in range(31):
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} secret {{{{CAK{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} key-name {{{{CKN{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} start-time "{{{{ROLL{index}}}}}"\n')

    with open("temp.j2") as t_fh:
        t_format = t_fh.read()

    template = Template(t_format)

    if config_data["DEBUG"]:
        logger.info(template.render(keychain_data))

    for router in config_data["HOSTS"]:
        logger.info(f"Configuring {router}")
        try:
            with Device(
                host=router,
                user=config_data["USER"],
                ssh_private_key_file=config_data["KEY"],
                port=22,
            ) as dev:
                conf = Config(dev, mode="private")
                conf.load(template.render(keychain_data), format="set")
                conf.commit(
                    timeout=120,
                    comment=f'Created {config_data["KEYCHAIN-NAME"]} keychain',
                )
                committed.append(router)
        except (ConfigLoadError, CommitError, ConnectError) as exc:
            logger.error(f"PyEZ configuration exception, {exc}")
            if committed:
                rollback_changed(committed, router)
            else:
                sys.exit(2)
        except Exception as exc:
            logger.critical(f"PyEZ configuration exception, {exc}")
            sys.exit(2)


def update_keychain():
    """ Update the keychain with information from the checks """

    # Check that no private or exclusive configs are in use
    for router in config_data["HOSTS"]:
        logger.info(f"Checking configuration lock on {router}")
        try:
            with Device(
                host=router,
                user=config_data["USER"],
                ssh_private_key_file=config_data["KEY"],
                port=22,
            ) as dev:
                conf = Config(dev, mode="exclusive")
                conf.commit_check()
        except CommitError as exc:
            logger.error(f"Configuration lock error, {exc}")
            sys.exit(2)
        except Exception as exc:
            logger.error(f"Error, {exc}")
            sys.exit(2)

    with open("temp.j2", mode="w") as twr:
        for index in range(31):
            if index >= int(used_id[0]):
                twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index+1} secret {{{{CAK{index}}}}}\n')
                twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index+1} key-name {{{{CKN{index}}}}}\n')
                twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index+1} start-time "{{{{ROLL{index}}}}}"\n')
                continue
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} secret {{{{CAK{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} key-name {{{{CKN{index}}}}}\n')
            twr.write(f'set security authentication-key-chains key-chain {config_data["KEYCHAIN-NAME"]} key {index} start-time "{{{{ROLL{index}}}}}"\n')

    with open("temp.j2") as t_fh:
        t_format = t_fh.read()

    template = Template(t_format)

    if config_data["DEBUG"]:
        logger.info(template.render(keychain_data))

    for router in config_data["HOSTS"]:
        logger.info(f"Configuring {router}")
        try:
            with Device(
                host=router,
                user=config_data["USER"],
                ssh_private_key_file=config_data["KEY"],
                port=22,
            ) as dev:
                conf = Config(dev, mode="private")
                conf.load(template.render(keychain_data), format="set")
                conf.commit(
                    timeout=120,
                    comment=f'Updated {config_data["KEYCHAIN-NAME"]} keychain',
                )
                committed.append(router)
        except (ConfigLoadError, CommitError, ConnectError) as exc:
            logger.error(f"PyEZ configuration exception, {exc}")
            if committed:
                rollback_changed(committed, router)
            else:
                sys.exit(2)
        except Exception as exc:
            logger.critical(f"PyEZ configuration exception, {exc}")
            sys.exit(2)


if __name__ == "__main__":
    with open("data.yml") as fh:
        config_data = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    if config_data["ROLLINTERVAL"] <= 1:
        logger.info("Increase the ROLLINTERVAL in data.yml")
        sys.exit(1)

    if len(sys.argv) == 2:
        if sys.argv[1] == "init":
            create_keychain_dict()
            check_for_duplicates()
            create_keychain()
            remove_template()
        else:
            logger.info('Use no arguments to update the keychain or "init" to create an initial keychain')
    else:
        check_keychain()
        create_keychain_dict()
        check_for_duplicates()
        update_keychain()
        remove_template()
