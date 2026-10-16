# Official stable CPython, multiarchitecture index (amd64 and arm64).
FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53

# Native build tools are needed by core dependencies without cp315 wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash build-essential ca-certificates curl git libffi-dev pkg-config \
    postgresql-client sudo util-linux zsh \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 vscode \
    && useradd --uid 1000 --gid vscode --create-home --shell /bin/bash vscode \
    && echo 'vscode ALL=(root) NOPASSWD:ALL' > /etc/sudoers.d/vscode \
    && chmod 0440 /etc/sudoers.d/vscode

USER vscode
ARG RUST_VERSION=1.95.0
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh \
    && sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain "$RUST_VERSION" \
    && rm /tmp/rustup-init.sh
ENV PATH="/workspace/.venv/bin:/home/vscode/.cargo/bin:${PATH}"
WORKDIR /workspace
