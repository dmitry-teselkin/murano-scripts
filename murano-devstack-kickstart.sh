#!/bin/bash

# wget https://raw.githubusercontent.com/dmitry-teselkin/murano-scripts/master/murano-devstack-kickstart.sh -O - | bash

git clone https://github.com/stackforge/murano-deployment
cd murano-deployment/murano-ci/scripts
wget https://raw.githubusercontent.com/dmitry-teselkin/murano-scripts/master/murano-devstack.sh
bash murano-devstack.sh

