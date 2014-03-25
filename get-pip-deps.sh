#!/bin/bash

PACKAGE=$1

PIP_BUILD_STACK=/tmp/pip_build_stack

function pip_install_dryrun() {
    local package=$1

    rm -rf "$PIP_BUILD_STACK"
    rm -f $package.requirements.txt

    pip install --no-install --verbose $package \
        | awk '/^Requirement already satisfied/ {print $8}' \
        >> $package.requirements.txt
}

function analize_build_stack() {
    local d

    for d in $(ls -d $PIP_BUILD_STACK/*/); do
        if [[ -f $d/requirements.txt ]]; then
            cat $d/requirements.txt >> $PACKAGE.requirements.txt
        fi
    done
}

function split_dependency_list() {
    sort -u $PACKAGE.requirements.txt \
        | grep -v '^$' > $PACKAGE.requirements.txt.tmp

    cat $PACKAGE.requirements.txt.tmp \
        | perl -pe 's|(.*?)([<>=!].*)|\1\t\2|' \
        | sed 's/,/\t/' \
        > $PACKAGE.requirements.txt
}

pip_install_dryrun $PACKAGE
analize_build_stack
split_dependency_list

