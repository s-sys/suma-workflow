"""Jira integration utils."""

import datetime
import logging
import os
from time import sleep

import psycopg2


LOGGER = logging.getLogger('JiraIntegration')


PSQL_AUTH = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
    'database': os.getenv('POSTGRES_DATABASE', 'postgres'),
}


def split(items, buckets):
    """Split items in buckets."""
    buckets = buckets if buckets > 0 else 1
    div, mod = divmod(len(items), buckets)
    LOGGER.info('CHEGOU AQUI:  final')
    LOGGER.info((items[i * div + min(i, mod):(i + 1) * div + min(i + 1, mod)] for i in range(buckets)))
    return (items[i * div + min(i, mod):(i + 1) * div + min(i + 1, mod)] for i in range(buckets))


def sync_option_cascading(client, packages, field_id, context_id):
    """Sync option cascading."""
    # pylint: disable=too-many-locals,too-many-branches
    # packages = []
    version = {}
    option_delete = []
    sub_options = []
    start_at = 0
    while True:
        LOGGER.info('Fetching options...')
        response = client.get_field_option(field_id, context_id, startAt=start_at)
        for option in response[1].get('values', []):
            if 'optionId' in option:
                sub_options.append(option)
            elif option['value'] in packages:
                packages[option['value']]['id'] = option['id']
                version[option['id']] = {'options': packages[option['value']]['options']}
            else:
                option_delete.append(option['id'])
        start_at = response[1]['startAt'] + response[1]['maxResults']
        if response[1]['isLast']:
            break

    for sub_option in sub_options:
        if sub_option['optionId'] in option_delete:
            option_delete.append(sub_option['id'])
        elif sub_option['value'] in version[sub_option['optionId']]['options']:
            version[sub_option['optionId']]['options'][sub_option['value']]['id'] = sub_option['id']
        else:
            option_delete.append(sub_option['id'])

    while option_delete:
        LOGGER.info('Deleting...')
        client.del_field_option(field_id, context_id, option_delete.pop(-1))

    options = [{'disabled': False, 'value': k} for k, v in packages.items() if 'id' not in v]
    LOGGER.info('Options to be added: %d', len(options))

    split_count = int(len(options)/900)
    split_count = split_count if split_count > 0 else 1
    LOGGER.info('Slip of: %d', split_count)
    options_splitted = split(options, split_count)

    LOGGER.info(options_splitted)

    for item in options_splitted:
        LOGGER.info('Sending the software in bulk...')
        response = client.add_field_option(
            field_id,
            context_id,
            options=item
        )
        if not response[0]:
            LOGGER.info('Response: %s', response[1])

    for option in response[1].get('options', []):
        packages[option['value']]['id'] = option['id']
        version[option['id']] = {'options': packages[option['value']]['options']}

    LOGGER.info('oi')

    sub_options = []
    for key, value in version.items():
        for sub_option in value['options'].keys():
            if 'id' not in value['options'][sub_option]:
                sub_options.append({
                    'optionId': key,
                    'disabled': False,
                    'value': sub_option
                })

    LOGGER.info('Adding...')
    sub_options_splitted = split(sub_options, int(len(sub_options)/900))
    for item in sub_options_splitted:
        LOGGER.info('Sending the software version in bulk...')
        response = client.add_field_option(
            field_id,
            context_id,
            options=item
        )
        if not response[0]:
            LOGGER.info('Response: %s', response[1])


def sync_option(client, option_to_sync, field_id, context_id):
    """Sync option."""
    # option_to_sync = []
    option_delete = []
    start_at = 0
    while True:
        LOGGER.info('Fetching options...')
        response = client.get_field_option(field_id, context_id, startAt=start_at)
        for option in response[1].get('values', []):
            if option['value'] in option_to_sync:
                option_to_sync[option['value']]['id'] = option['id']
            else:
                option_delete.append(option['id'])
        start_at = response[1]['startAt'] + response[1]['maxResults']
        if response[1]['isLast']:
            break

    while option_delete:
        LOGGER.info('Deleting...')
        client.del_field_option(field_id, context_id, option_delete.pop(-1))

    options = [{'disabled': False, 'value': k} for k, v in option_to_sync.items() if 'id' not in v]
    count = len(options)
    LOGGER.info('Options to be added: %d', count)

    split_count = int(len(options)/900)
    split_count = split_count if split_count > 0 else 1
    options_splitted = split(options, split_count)

    if count > 0:
        for item in options_splitted:
            LOGGER.info('Sending the software in bulk...')
            response = client.add_field_option(
                field_id,
                context_id,
                options=item
            )
            if not response[0]:
                LOGGER.info('Response: %s', response[1])


def get_list_package(client, channels=None):
    """Get list of packages."""
    # Fetch channels
    results = client.run_command('channel', 'listAllChannels')
    if results is None:
        raise client.get_error()
    all_channels = list({result['label'] for result in results})
    LOGGER.info(all_channels)
    if channels is None:
        channels = all_channels
    elif isinstance(channels, list):
        for channel in channels:
            if channel not in all_channels:
                raise ValueError(f'Channel \'{channel}\' not found')
    else:
        raise ValueError('\'channels\' must be a list or None')

    packages = dict()
    for channel in channels:
        results = client.run_command('channel.software', 'listAllPackages', [channel])
        if results is not None:
            for result in results:
                if not result['name'] in packages:
                    packages[result['name']] = {'options': {}}
                packages[result['name']]['options'][result['version']] = {}
    return packages


def start_db_config():
    """Setup database config."""
    with psycopg2.connect(**PSQL_AUTH) as connection:
        cursor = connection.cursor()
        cursor.execute('DROP TABLE IF EXISTS packages')
        cursor.execute('CREATE TABLE packages (id serial PRIMARY KEY, software VARCHAR ( 150 ) NOT NULL, version VARCHAR ( 20 ) NOT NULL, minion VARCHAR ( 150 ) UNIQUE NOT NULL,install_after TIMESTAMP NOT NULL)')
        connection.commit()


def set_package_config(software, version, minions, install_after=None):
    """Set package config in the database."""
    if install_after is None:
        install_after = datetime.datetime.now()
    install_after = install_after.strftime('%Y-%m-%d %H:%M:%S')

    with psycopg2.connect(**PSQL_AUTH) as connection:
        cursor = connection.cursor()
        for minion in minions:
            cursor.execute(f'INSERT INTO Packages(Software, Version, Minion, Install_After) VALUES(\'{software}\', \'{version}\', \'{minion}\', \'{install_after}\')')
        connection.commit()
