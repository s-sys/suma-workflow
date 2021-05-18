"""REST API Client for Salt."""

from pepper.libpepper import Pepper


class SaltClient:
    """Interface to communicate with Salt."""
    # pylint: disable=too-many-instance-attributes

    def __init__(self, host, username, password, eauth, ignore_ssl_errors=False):
        """Set variables while building class."""
        # pylint: disable=too-many-arguments
        self._host = host
        self._username = username
        self._password = password
        self._eauth = eauth
        self._pepper = Pepper(api_url=host, ignore_ssl_errors=ignore_ssl_errors)

    def __enter__(self):
        self.login()
        return self

    def login(self):
        """Log into the Salt master."""
        self._pepper.login(self._username, self._password, self._eauth)

    def send_ping(self, minion, timeout=None):
        """Check if a minion is alive."""
        result = self._pepper.local_async(minion, 'test.ping', timeout=timeout)
        for item in result['return']:
            if 'minions' in item and minion in item['minions']:
                return True
        return False

    def run_command(self, tgt, fun, **kwargs):
        """Run a Salt command."""
        result = self._pepper.local(tgt, fun, **kwargs)
        return result['return']

    def run_command_async(self, tgt, fun, **kwargs):
        """Run an async Salt command."""
        result = self._pepper.local_async(tgt, fun, **kwargs)
        return result['return']

    def run_command_master(self, fun, **kwargs):
        """Run a Salt command on the master."""
        result = self._pepper.runner(fun, **kwargs)
        return result['return']

    def check_job_status(self, jid):
        """Check if an async Salt command finished running."""
        result = self._pepper.runner('jobs.exit_success', jid=jid)
        return result['return']

    def get_job_status(self, jid):
        """Get the status of an async Salt command."""
        result = self._pepper.runner('jobs.lookup_jid', jid=jid)
        return result['return']
