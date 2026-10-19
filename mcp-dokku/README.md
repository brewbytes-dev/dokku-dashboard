# Dokku root MCP

The MCP endpoint is `https://mcp.brewbytes.dev/mcp`. It uses GitHub OAuth and only the GitHub account `brewbytes-dev` may run tools. Its one tool, `run_root_command`, executes an arbitrary command as root on the Dokku host.

Root commands can read every secret and file on the host. Command output is returned to the connected agent, so GitHub OAuth restricts who can connect but cannot prevent secret disclosure by a root command. Do not attach this server to agents or workflows that should not have full host access.

## Runtime configuration

Create a GitHub OAuth App with homepage `https://mcp.brewbytes.dev` and callback `https://mcp.brewbytes.dev/auth/callback`. Configure its client ID and secret in the Dokku app along with a stable random `JWT_SIGNING_KEY`. Request only the `read:user` scope.

The Dokku app also needs a read-only mount of a dedicated SSH private key at `/run/secrets/dokku/id_ed25519`. Install its public key in root's `authorized_keys` with `restrict` so SSH forwarding and PTY access stay disabled while remote commands remain available. The MCP container has no Docker socket or Dokku host-directory mounts.

The OAuth proxy stores its encrypted registration data under the container's home directory. It is not persisted, so clients may need to authorize again after a redeploy or restart.
