#!/bin/bash

# wget https://raw.githubusercontent.com/dmitry-teselkin/murano-scripts/master/murano-devstack-kickstart.sh -O - | bash

sudo locale-gen en_US en_US.UTF-8 ru_RU ru_RU.UTF-8
sudo dpkg-reconfigure locales

git clone https://github.com/stackforge/murano-deployment
cd murano-deployment/murano-ci/scripts
wget https://raw.githubusercontent.com/dmitry-teselkin/murano-scripts/master/murano-integration-tests-devstack.sh
bash -x murano-integration-tests-devstack.sh

