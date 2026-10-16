# Official stable CPython, multiarchitecture index (amd64 and arm64).
FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53

# Native build tools are needed by core dependencies without cp315 wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash build-essential ca-certificates curl git jq libffi-dev pkg-config \
    postgresql-client sudo util-linux zsh \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 vscode \
    && useradd --uid 1000 --gid vscode --create-home --shell /bin/bash vscode \
    && echo 'vscode ALL=(root) NOPASSWD:ALL' > /etc/sudoers.d/vscode \
    && chmod 0440 /etc/sudoers.d/vscode

# Helm/jq are required by repository chart and OCI regression tests.
ARG TARGETARCH
ARG HELM_VERSION=4.3.1
RUN case "$TARGETARCH" in \
        amd64) helm_sha=0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b ;; \
        arm64) helm_sha=8cf8f66ecbc252ac8f7f06cca68aba88508ddfde3a6a34feb1678ad1694b4f88 ;; \
        *) exit 1 ;; \
    esac \
    && curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" -o /tmp/helm.tar.gz \
    && echo "$helm_sha  /tmp/helm.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/helm.tar.gz -C /tmp \
    && install "/tmp/linux-${TARGETARCH}/helm" /usr/local/bin/helm \
    && rm -rf /tmp/helm.tar.gz "/tmp/linux-${TARGETARCH}"

USER vscode
ARG RUST_VERSION=1.95.0
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh \
    && sh /tmp/rustup-init.sh -y --profile minimal --default-toolchain "$RUST_VERSION" \
    && rm /tmp/rustup-init.sh
ENV PATH="/workspace/.venv/bin:/home/vscode/.cargo/bin:${PATH}"
WORKDIR /workspace
