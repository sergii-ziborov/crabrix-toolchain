# The amd64 Ubuntu 24.04 manifest is pinned independently of the mutable tag.
# This prepares a local candidate build environment. A release lock still needs
# the digest of the completed image and a successful source build.
FROM ubuntu@sha256:496754492fb28b4d3049432f2ca787449331e23fb14f0dd3fffea86bf5a93eb4

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
       build-essential \
       ca-certificates \
       cmake \
       curl \
       file \
       git \
       libssl-dev \
       libzstd-dev \
       ninja-build \
       pkg-config \
       python3 \
       unzip \
       xz-utils \
       zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
