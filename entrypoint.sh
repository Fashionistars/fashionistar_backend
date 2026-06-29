#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status.
set -o errexit
# Exit if any pipe command fails.
set -o pipefail
# Exit if trying to use an uninitialized variable.
set -o nounset

echo "FASHIONISTAR AI Container Entrypoint Initialized"

# Execute the CMD passed to the docker run command
exec "$@"
