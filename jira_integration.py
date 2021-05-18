#/usr/bin/env python3
"""Flask app for Jira integration."""

import json
import logging
import os

from flask import Flask, request

from jira_client.client import JiraClient
from jira_client import plugin
from susemanager_client.client import SuseManagerClient
from salt_client.client import SaltClient
from threading import Thread

from utils import sync_option_cascading, get_list_package, sync_option, set_package_config, start_db_config


JIRA_HOST = os.getenv('JIRA_HOST', 'http://127.0.0.1')
JIRA_USER = os.getenv('JIRA_USER', 'jira')
JIRA_PASSWORD = os.getenv('JIRA_PASSWORD', 'jira')

SUSEMANAGER_HOST = os.getenv('SUSEMANAGER_HOST', 'http://127.0.0.1')
SUSEMANAGER_USER = os.getenv('SUSEMANAGER_USER', 'susemanager')
SUSEMANAGER_PASSWORD = os.getenv('SUSEMANAGER_PASSWORD', 'susemanager')
SUSEMANAGER_CHANNELS = os.getenv('SUSEMANAGER_CHANNELS', '').split()

SALT_HOST = os.getenv('SALT_HOST', 'http://127.0.0.1')
SALT_USER = os.getenv('SALT_USER', 'susemanager')
SALT_PASSWORD = os.getenv('SALT_PASSWORD', 'susemanager')

if os.getenv('MODE', 'development') == 'production':
    LOG_FILE = '/var/log/jira_integration/jira_integration.log'
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)

LOGGER = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/')
def hello_world():
    """Hello world endpoint."""
    start_db_config()
    return 'Hello, Susecon!\n'


@app.route('/jira', methods=['POST'])
def send_database():
    """Jira login endpoint."""
    try:
        hosts = []
        data = json.loads(request.data)
        software = data['fields'].get('customfield_10080').get('value')
        version = data['fields'].get('customfield_10080').get('child').get('value')
        for host in data['fields'].get('customfield_10082'):
            hosts.append(host.get('value'))
        LOGGER.info('Software: %s', software)
        LOGGER.info('Version: %s', version)
        LOGGER.info('Host: %s', hosts)
        set_package_config(software, version, hosts)
    except Exception:
        return 'Invalid parameters\n'
    return 'Included\n'


@app.route('/jira/force_update', methods=['POST'])
def force_update():
    """Force update endpoint."""
    response = ""
    LOGGER.info('Start Salt comunication...')
    LOGGER.info('Start Salt comunication... %s , %s, %s', SALT_HOST, SALT_USER, SALT_PASSWORD)
    salt_client = SaltClient(SALT_HOST, SALT_USER, SALT_PASSWORD, 'file')
    salt_client.login()
    try:
        hosts = []
        data = json.loads(request.data)
        for host in data['fields'].get('customfield_10082'):
            hosts.append(host.get('value'))
        LOGGER.info('Host: %s', hosts)
    except Exception:
        return 'Invalid parameters\n'
    for host in hosts:
        response += str(salt_client.run_command_async(host, 'state.apply', arg=['install_packages',]))
        LOGGER.info('RESPONSE: %s', response)

    return str(response)


@app.route('/update/packages')
def update_packages():
    thread = Thread(target=update_package_list,)
    thread.daemon = True
    thread.start()
    return "Process started!"


def update_package_list():
    """Update package list endpoint."""
    jira_client = JiraClient(JIRA_HOST, JIRA_USER, JIRA_PASSWORD)

    suse_client = SuseManagerClient(host=SUSEMANAGER_HOST, user=SUSEMANAGER_USER, passwd=SUSEMANAGER_PASSWORD)
    if suse_client.login() != SuseManagerClient.STATUS_SUCCESS:
        raise suse_client.get_error()
    if SUSEMANAGER_CHANNELS:
        packages = get_list_package(suse_client, SUSEMANAGER_CHANNELS)
    else:
        packages = get_list_package(suse_client)
    suse_client.logout()

    response = jira_client.create_field(
        name='SuseManager Software',
        type=plugin.CustomFieldTypes.CASCADINGSELECT,
        searcherKey=plugin.CustomFieldTypesSearcher.CASCADINGSELECTSEARCHER,
        description='Choose a package and version available in SuseManager',
        unique=True
    )
    field_id = response[1]['id']
    response = jira_client.get_field(field_id)
    context_id = response[1]['context'][0]['id']

    sync_option_cascading(jira_client, packages, field_id, context_id)
    return 'Updated\n'


@app.route('/update/hosts')
def update_hosts():
    thread = Thread(target=update_susemanager_hosts,)
    thread.daemon = True
    thread.start()
    return "Process started!"


def update_susemanager_hosts():
    """Update SuseManager hosts endpoint."""
    jira_client = JiraClient(JIRA_HOST, JIRA_USER, JIRA_PASSWORD)

    suse_client = SuseManagerClient(host=SUSEMANAGER_HOST, user=SUSEMANAGER_USER, passwd=SUSEMANAGER_PASSWORD)
    if suse_client.login() != SuseManagerClient.STATUS_SUCCESS:
        raise suse_client.get_error()

    results = suse_client.run_command('system', 'listSystems')
    if results is not None:
        hosts = {result['name']: {} for result in results}
    LOGGER.info("Create Jira Field")
    response = jira_client.create_field(
        name='SuseManager Machine',
        type=plugin.CustomFieldTypes.MULTISELECT,
        searcherKey=plugin.CustomFieldTypesSearcher.MULTISELECTSEARCHER,
        description='Choose a host or host group available in SuseManager',
        unique=True
    )
    field_id = response[1]['id']

    response = jira_client.get_field(field_id)
    context_id = response[1]['context'][0]['id']
    LOGGER.info("Sync values")
    sync_option(jira_client, hosts, field_id, context_id)

    response = jira_client.get_field_option(field_id, context_id)
    total = response[1]['total']
    LOGGER.info(f'Updated {total} hosts\n')


if __name__ == '__main__':
    app.run()
