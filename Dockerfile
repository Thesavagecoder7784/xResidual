# Reproducible analysis environment for xResidual.
# Captures the ANALYSIS runtime (rebuilding result JSONs -> macros -> paper numbers).
# It does NOT run the live capture (that needs venue credentials; see logger/).
#
# For bit-for-bit reproducibility, pin the base image by digest — replace the tag with
# the digest you build against, e.g.:
#   FROM python:3.12-slim@sha256:<digest>
FROM python:3.12-slim

# 'make' for the reproduce targets; 'git' for provenance stamping (content-hash).
RUN apt-get update && apt-get install -y --no-install-recommends make git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /xresidual

# Install deps first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt pytest

COPY . .

# Default: verify the paper numbers are in sync and the suite passes.
CMD ["make", "check"]
