#!/bin/bash
# Copyright (c) 2014 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

# Error trapping first
#---------------------
set -o errexit

function trap_handler() {
    echo "Got error in '$1' on line '$2', error code '$3'"
}
trap 'trap_handler ${0} ${LINENO} ${?}' ERR
#---------------------


CI_ROOT_DIR=$(cd $(dirname "$0") && cd .. && pwd)

#Include of the common functions library file:
INC_FILE="${CI_ROOT_DIR}/scripts/common.inc"
if [ -f "$INC_FILE" ]; then
    source "$INC_FILE"
else
    echo "'$INC_FILE' - file not found, exiting!"
    exit 1
fi

#Basic parameters:
PYTHON_CMD=$(which python)
NOSETESTS_CMD=$(which nosetests)
GIT_CMD=$(which git)
NTPDATE_CMD=$(which ntpdate)
PIP_CMD=$(which pip)
SCREEN_CMD=$(which screen)
FW_CMD=$(which iptables)
DISPLAY_NUM=22
STORE_AS_ARTIFACTS="/tmp/murano-artifacts ${WORKSPACE}/murano-dashboard/functionaltests/screenshots /tmp/murano*.log"

get_os

### Add correct Apache log path
if [ $distro_based_on == "redhat" ]; then
    STORE_AS_ARTIFACTS+=" /var/log/httpd/error_log"
else
    STORE_AS_ARTIFACTS+=" /var/log/apache2/error.log"
fi


#This file is generated by Nodepool while building snapshots
#It contains credentials to access RabbitMQ and an OpenStack lab
source ~/credentials

ZUUL_URL=${ZUUL_URL:-'https://github.com'}
ZUUL_REF=${ZUUL_REF:-'master'}

#Functions:

function get_ip_from_iface() {
    local iface_name=$1

    found_ip_address=$(ifconfig $iface_name | awk -F ' *|:' '/inet addr/{print $4}')

    if [ $? -ne 0 ] || [ -z "$found_ip_address" ]; then
        echo "Can't obtain ip address from interface $iface_name!"
        return 1
    else
        readonly found_ip_address
    fi

    return 0
}


function prepare_incubator_at() {
    local retval=0
    local git_url="https://github.com/murano-project/murano-app-incubator"
    local start_dir=$1
    local clone_dir="${start_dir}/murano-app-incubator"

    $GIT_CMD clone $git_url $clone_dir

    if [ $? -ne 0 ]; then
        echo "Error occured during git clone $git_url $clone_dir!"
        return 1
    fi

    cd $clone_dir
    local pkg_counter=0
    for package_dir in io.murano.*
    do
        if [ -d "$package_dir" ]; then
            if [ -f "${package_dir}/manifest.yaml" ]; then
                bash make-package.sh $package_dir
                pkg_counter=$((pkg_counter + 1))
            fi
        fi
    done

    cd ${start_dir}
    bash murano-app-incubator/make-package.sh MockApp
    if [ $pkg_counter -eq 0 ]; then
        echo "Warning: $pkg_counter packages was built at $clone_dir!"
        return 1
    fi

    return $retval
}


function prepare_tests() {
    local retval=0
    local tests_dir=$TESTS_DIR

    if [ ! -d "$tests_dir" ]; then
        echo "Directory with tests isn't exist"
        return 1
    fi

    sudo chown -R $USER ${tests_dir}/functionaltests

    cd $tests_dir

    local tests_config=${tests_dir}/functionaltests/config/config_file.conf
    local horizon_suffix="horizon"

    if [ "$distro_based_on" == "redhat" ]; then
        horizon_suffix="dashboard"
    fi

    horizon_suffix=''

    iniset 'common' 'keystone_url' "$(shield_slashes http://${KEYSTONE_URL}:5000/v2.0/)" "$tests_config"
    iniset 'common' 'horizon_url' "$(shield_slashes http://${found_ip_address}/${horizon_suffix})" "$tests_config"
    iniset 'common' 'murano_url' "$(shield_slashes http://${found_ip_address}:8082)" "$tests_config"
    iniset 'common' 'user' "$ADMIN_USERNAME" "$tests_config"
    iniset 'common' 'password' "$ADMIN_PASSWORD" "$tests_config"
    iniset 'common' 'tenant' "$ADMIN_TENANT" "$tests_config"

    cd $tests_dir/functionaltests

    prepare_incubator_at $(pwd) || retval=$?

    cd $WORKSPACE

    mkdir -p /tmp/murano-artifacts
    chmod -R 777 /tmp/murano-artifacts

    return $retval
}


function run_tests() {
    local retval=0
    local tests_dir=$TESTS_DIR

    sudo rm -f /tmp/parser_table.py

    cd ${tests_dir}/functionaltests
    PYTHONPATH=/opt/stack/murano-dashboard $NOSETESTS_CMD sanity_check --nologcapture |:

    if [ ${PIPESTATUS[0]} -ne 0 ]; then
        collect_artifacts $STORE_AS_ARTIFACTS
        retval=1
    else
        collect_artifacts $STORE_AS_ARTIFACTS
    fi

    cd $WORKSPACE

    return $retval
}


function collect_artifacts() {
    local sources=$@
    local destination=${WORKSPACE}/artifacts

    sudo mkdir -p $destination

    for src in $sources; do
        if [ -e "${src}" ]; then
            if [ -d "${src}" ]; then
                sudo cp -R ${src}/* ${destination}/
            else
                sudo cp -R ${src} ${destination}/
            fi
        fi
    done

    sudo cp /opt/stack/logs/*.log ${destination}/

    sudo chown -R jenkins:jenkins ${destination}/*
}


function deploy_devstack() {
    # Assuming the script is run from 'jenkins' user
    local git_dir=/opt/git

    sudo mkdir -p "$git_dir/openstack-dev"
    sudo chown -R jenkins:jenkins "$git_dir/openstack-dev"
    cd "$git_dir/openstack-dev"
    git clone https://github.com/openstack-dev/devstack

    sudo mkdir -p "$git_dir/stackforge"
    sudo chown -R jenkins:jenkins "$git_dir/stackforge"
    cd "$git_dir/stackforge"
    git clone https://github.com/stackforge/murano-api

    # NOTE: Source path MUST end with slash char!
    rsync --recursive --exclude README.* "$git_dir/stackforge/murano-api/contrib/devstack/" "$git_dir/openstack-dev/devstack/"

    cd "$git_dir/openstack-dev/devstack"
    cat << EOF > local.conf
[[local|localrc]]
HOST_IP=${KEYSTONE_URL}             # IP address of OpenStack lab
ADMIN_PASSWORD=.                    # This value doesn't matter
MYSQL_PASSWORD=swordfish            # Random password for MySQL installation
SERVICE_PASSWORD=${ADMIN_PASSWORD}  # Password of service user
SERVICE_TOKEN=.                     # This value doesn't matter
SERVICE_TENANT_NAME=${ADMIN_TENANT}
MURANO_ADMIN_USER=${ADMIN_USERNAME}
RABBIT_HOST=localhost
RABBIT_PASSWORD=guest
MURANO_RABBIT_VHOST=/
RECLONE=True
SCREEN_LOGDIR=/opt/stack/log/
LOGFILE=\$SCREEN_LOGDIR/stack.sh.log
MURANO_DASHBOARD_REPO=${ZUUL_URL}/stackforge/murano-dashboard
MURANO_DASHBOARD_BRANCH=${ZUUL_REF}
ENABLED_SERVICES=
enable_service mysql
enable_service rabbit
enable_service horizon
enable_service murano
enable_service murano-api
#enable_service murano-engine
enable_service murano-dashboard
EOF

    sudo ./tools/create-stack-user.sh

    sudo chown -R stack:stack "$git_dir/openstack-dev/devstack"

    sudo su -c "cd $git_dir/openstack-dev/devstack && ./stack.sh" stack
}


function configure_apt_cacher() {
    local apt_proxy_file=/etc/apt/apt.conf.d/01proxy
    local apt_proxy_host=${2:-'172.18.124.203'}

    case $1 in
        enable)
            sudo sh -c "echo 'Acquire::http::proxy \"http://${apt_proxy_host}:3142\";' > $apt_proxy_file"
            sudo apt-get update
        ;;
        disable)
            sudo rm -f $apt_proxy_file
            sudo apt-get update
        ;;
    esac
}


#Starting up:
WORKSPACE=$(cd $WORKSPACE && pwd)

TESTS_DIR="/opt/stack/murano-dashboard"

sudo sh -c "echo '127.0.0.1 $(hostname)' >> /etc/hosts"

configure_apt_cacher enable

cd $WORKSPACE

export DISPLAY=:${DISPLAY_NUM}

fonts_path="/usr/share/fonts/X11/misc/"
if [ $distro_based_on == "redhat" ]; then
    fonts_path="/usr/share/X11/fonts/misc/"
fi

$SCREEN_CMD -dmS display sudo Xvfb -fp ${fonts_path} :${DISPLAY_NUM} -screen 0 1024x768x16

sudo $NTPDATE_CMD -u ru.pool.ntp.org
sudo $FW_CMD -F

get_ip_from_iface eth0

deploy_devstack

sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT

prepare_tests

run_tests

exit 0

