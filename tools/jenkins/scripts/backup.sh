#!/usr/bin/env bash

set -euxo pipefail

OPENSHIFT_DEPLOYMENT=${OPENSHIFT_DEPLOYMENT:-false}

# -- Start
#
# shellcheck source=lib/common
source "$(dirname "${0}")"/lib/common

if [[ "${OPENSHIFT_DEPLOYMENT}" == "true" ]]; then
    ./setup/setup_openshift.sh -b -e @vars.yml -e ansible_become=true -e openshift_password="${OPENSHIFT_PASS}"
else
    INVENTORY=$(retrieve_inventory_file)
    INSTALL_NODE=$(retrieve_tower_server_from_inventory "${INVENTORY}")
    INSTALL_USER=$(ansible tower -i "${INVENTORY}" -m debug -a 'msg={{ ansible_ssh_user }}' | tail -n 2 | awk 'NR==1{print $2}' | sed -e 's/"//g')

    ansible "${INSTALL_NODE}" \
        -i "${INVENTORY}" \
        -a 'chdir=/tmp/setup ./setup.sh -b -e @vars.yml -e ansible_become=true' \
        -e ansible_become=true

    rsync -e 'ssh -o StrictHostKeyChecking=no' -L "${INSTALL_USER}"@"${INSTALL_NODE}":/tmp/setup/tower-backup-latest.tar.gz .
fi
