import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastmcp.exceptions import ToolError

import security
from server import run_ssh_command


class GitHubAllowlistTests(unittest.TestCase):
    @patch.object(security, "get_access_token")
    def test_allows_only_the_configured_github_login(self, get_token):
        get_token.return_value = SimpleNamespace(claims={"login": "ismirnov_align"})
        security.require_allowed_github_user()

        get_token.return_value = SimpleNamespace(claims={"login": "someone-else"})
        with self.assertRaises(ToolError):
            security.require_allowed_github_user()

    @patch.object(security, "get_access_token")
    def test_denies_missing_or_malformed_identity(self, get_token):
        for token in (None, SimpleNamespace(claims={"login": None})):
            get_token.return_value = token
            with self.subTest(token=token), self.assertRaises(ToolError):
                security.require_allowed_github_user()


class RootCommandTests(unittest.TestCase):
    @patch("server.subprocess.run")
    def test_runs_the_requested_command_without_a_local_shell(self, run):
        run.return_value = SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

        self.assertEqual(run_ssh_command("id -u"), "ok\n")
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ["root@mcp.brewbytes.dev", "id -u"])
        self.assertNotIn("shell", kwargs)

    @patch("server.subprocess.run")
    def test_rejects_unrepresentable_or_empty_commands_before_ssh(self, run):
        for command in ("", "\0", "x" * 8193):
            with self.subTest(command=command[:8]), self.assertRaises(ToolError):
                run_ssh_command(command)
        run.assert_not_called()

    @patch("server.subprocess.run", side_effect=subprocess.TimeoutExpired("ssh", 120))
    def test_times_out_root_commands(self, run):
        with self.assertRaises(ToolError):
            run_ssh_command("sleep 999")


if __name__ == "__main__":
    unittest.main()
