# The image every agent-initiated command runs inside.
#
# Deliberately minimal: a language runtime and git, no build toolchain, no package manager
# credentials, no network tooling. Nothing in here is trusted with anything - the container is
# started with no network, no capabilities, a read-only root, and only the project's workspace
# mounted writable.
#
# git is present because git commands must run *contained*: the repository is agent-controlled,
# and git executes hooks from inside it, so running git on the host would let a written hook
# escape the sandbox.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git procps \
    && rm -rf /var/lib/apt/lists/*

# Agents commit through the gateway, so git needs an identity that is obviously not a person.
RUN git config --system user.email "agent@phoenix-forge.local" \
    && git config --system user.name "Phoenix Forge Agent" \
    && git config --system --add safe.directory /workspace

WORKDIR /workspace
