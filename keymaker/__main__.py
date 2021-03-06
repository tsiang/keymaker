import click

import os
import time
import asyncio
import boto
import boto.utils
import logging

from datetime import datetime
from daemon import runner

LOG = logging.getLogger(__name__)
logging.basicConfig(filename='/var/log/keymaker/keymakerlog.log', level=logging.DEBUG)

ssh_dir = '/home/scopely/.ssh'
authorized_keys_path = '/home/scopely/.ssh/authorized_keys'
pubkey_table = 'AA_Keys'

class Keymaker():
    def __init__(self):
        self.iam_role = None
        self.group_name = None
        self.user_list= None
        self.pubkey_list = None

    # get the iam role of the current instance
    def get_iam_role(self):
        inst_metadata = boto.utils.get_instance_metadata()
        iam_role = [role for role in inst_metadata['iam']['security-credentials']][0]
        return iam_role

    def get_group_name(self):
        inst_metadata = boto.utils.get_instance_metadata()
        inst_id = inst_metadata['instance-id']
        # retrieve tags based on instance-id
        conn = boto.connect_ec2()
        tags = conn.get_all_tags(filters={'resource-id': inst_id, 'key': 'Group'})
        if tags:
            group_name = tags[0].value
            return group_name
        else:
            LOG.error('No "Group" tag for instance-id: {}'.format(inst_id))

    # get the list of users from the iam group
    def get_users_list(self):
        user_list = []
        conn = boto.connect_iam()
        g = conn.get_group(self.group_name)
        for user in g.users:
            user_list.append(user.user_name)
        return user_list

    # returns a list of pubkeys
    def get_all_pubkeys(self):
        pubkey_list = []
        conn = boto.connect_dynamodb()
        table = conn.get_table(pubkey_table)
        for username in self.user_list:
            item = table.get_item(username)
            pubkey_list.append(item['pubkey'])
        return pubkey_list

    # make sure that the /home/scopely/.ssh/ directory exists
    # make sure that /home/scopely/.ssh/authorized_keys exists
    def create_paths(self):
        try:
            os.makedirs(ssh_dir, exist_ok=True)
            os.chmod(ssh_dir, 0o700)
            return True
        except OSError:
            raise

    def add_keys(self):
        try:
            with open(authorized_keys_path, 'w') as f:
                for key in self.pubkey_list:
                    f.write(key + "\n\n")
                    os.chmod(authorized_keys_path, 0o600)
            return True
        except OSError:
            raise


@asyncio.coroutine
def run_keymaker():
    while True:
        keymaker = Keymaker()

        # find out which iam group should have access to this box
        # can listen on a queue
        keymaker.iam_role = keymaker.get_iam_role()
        keymaker.group_name = keymaker.get_group_name()

        # get the emails from the iam group
        # first check if group exists
        keymaker.user_list = keymaker.get_users_list()

        # for each username in the list, query dynamo table for the public key
        keymaker.pubkey_list = keymaker.get_all_pubkeys()

        res_paths = keymaker.create_paths()
        res_add = keymaker.add_keys()

        LOG.debug('iam role: {}'.format(keymaker.iam_role))
        LOG.debug('group name: {}'.format(keymaker.group_name))
        LOG.debug('user list: {}'.format(keymaker.user_list))
        LOG.debug('pubkey list: {}'.format(keymaker.pubkey_list))

        time.sleep(5)
    pass


@click.command()
#@click.argument('group')
def main():
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(run_keymaker())
    finally:
        loop.close()

if __name__ == '__main__':
    main()
