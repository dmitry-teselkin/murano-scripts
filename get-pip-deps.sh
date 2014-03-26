#!/bin/bash

PACKAGE=${PACKAGE:-''}
PIP_BUILD_DIR=/tmp/pip_build_$(whoami)
DEB_REPO_URL='http://osci-obs.vm.mirantis.net:82/ubuntu-fuel-5.0-testing/ubuntu/'
GLOBAL_REQUIREMENTS_URL='https://raw.githubusercontent.com/openstack/requirements/master/global-requirements.txt'

options=','

if [[ $# -eq 1 ]]; then
    install_mode='pip'
    install_from=$1
else
    while [[ -n $1 ]]; do
        case $1 in
            -d|--dir)
                action='install'
                install_mode='dir'
                install_from=$2
                shift 2
            ;;
            -u|--url)
                action='install'
                install_mode='url'
                install_from=$2
                shift 2
            ;;
            -p|--pip)
                action='install'
                install_mode='pip'
                install_from=$2
                shift 2
            ;;
            -s|--search)
                action='search'
                PACKAGE=$2
                shift 2
            ;;
            -S|--stackforge)
                action='install'
                install_mode='stackforge'
                install_from=$2
                shift 2
            ;;
            -r|--recursive)
                options="${options}recursive,"
            ;;
            *)
                echo "Unrecognised parameter '$1'"
            ;;
        esac
        shift
    done
fi


cat << EOF
action='$action'
install_mode='$install_mode'
install_from='$install_from'
PACKAGE='$PACKAGE'
EOF


function die() {
    cat << EOF

SCRIPT FAILED
$@

EOF
exit 1
}


function is_option_set() {
    if [[ $options =~ ,$1, ]]; then
        return 0
    else
        return 1
    fi
}


function pip_install_dryrun() {
    local pip_install_opts='--no-install --verbose'

    rm -rf $PIP_BUILD_DIR

    case $install_mode in
        dir)
            pip_install_opts="$pip_install_opts -e"
            if [[ ! -d $install_from ]]; then
                die "No such folder '$install_from'"
            fi

            PACKAGE=$(cd "$install_from" && (python setup.py --name | tail -1))

            rm -f $PACKAGE.requirements.txt
            cat $install_from/requirements.txt \
                | grep -v '^#' \
                >> $PACKAGE.requirements.txt
        ;;
        pip)
            PACKAGE=$install_from
        ;;
        stackforge)
            local tmpdir=$(mktemp -d)
            git clone https://github.com/stackforge/$install_from $tmpdir

            cp $tmpdir/requirements.txt $tmpdir/requirements.txt.bak
            grep murano $tmpdir/requirements.txt \
                | perl -pe 's|(.*?)([<>=!].*)|\1|' \
                >> packages.to_process

            grep -v murano $tmpdir/requirements.txt > $tmpdir/requirements.txt.tmp
            mv $tmpdir/requirements.txt.tmp $tmpdir/requirements.txt

            install_from=$tmpdir
            PACKAGE=$(cd "$install_from" && (python setup.py --name | tail -1))

            rm -f $PACKAGE.requirements.txt
            cat $install_from/requirements.txt \
                | grep -v '^#' \
                >> $PACKAGE.requirements.txt
        ;;
        url)
            local tmpdir=$(mktemp -d)
            git clone $install_from $tmpdir

            install_from=$tmpdir
            PACKAGE=$(cd "$install_from" && (python setup.py --name | tail -1))

            rm -f $PACKAGE.requirements.txt
            cat $install_from/requirements.txt \
                | grep -v '^#' \
                >> $PACKAGE.requirements.txt
        ;;
        *)
            die "Unrecognized installation mode '$install_mode'"
        ;;
    esac

    if [[ -z "$PACKAGE" ]]; then
        die "Package name is empty."
    fi

    local pip_install_log=$(mktemp)
    pip_install_log=./pip_install.log

    rm -f $pip_install_log
    pip install $pip_install_opts $install_from | tee $pip_install_log

    cat $pip_install_log \
        | awk '/^Requirement already satisfied/ {print $8}' \
        >> $PACKAGE.requirements.txt

#    rm -f $pip_install_log
}


function get_requirements() {
    local d

    for d in $(ls -d $PIP_BUILD_DIR/*/); do
        if [[ -f $d/requirements.txt ]]; then
            cat $d/requirements.txt \
                | grep -v '^#' \
                >> $PACKAGE.requirements.txt
        fi
    done
}


function parse_requirements() {
    sort -u $PACKAGE.requirements.txt \
        | grep -v '^$' > $PACKAGE.requirements.txt.tmp

    cat $PACKAGE.requirements.txt.tmp \
        | perl -pe 's|(.*?)([<>=!].*)|\1 \2|' \
        | sed 's/,/ /' \
        > $PACKAGE.requirements.txt

    rm -f $PACKAGE.requirements.txt.tmp
}


function search_in_global_requirements() {
    local package=$1

    rm -f 'global-requirements.txt'
    wget $GLOBAL_REQUIREMENTS_URL

    rm -f $package.global_requirements.txt

    while read -r name version; do
        echo "**[$(echo $name $version)]**" >> $package.global_requirements.txt

        grep $name 'global-requirements.txt' >> $package.global_requirements.txt
    done < $package.requirements.txt
}


function search_deb_packages() {
    local package=$1
    local tempdir=$(mktemp -d)
    local name, version

    wget $DEB_REPO_URL/Packages.gz -P $tempdir

    rm $package.deb_packages.txt

    while read -r name version; do
        echo "**[$(echo $name $version)]**" >> $package.deb_packages.txt
#        echo '' >> $PACKAGE.deb_packages.txt

        zcat $tempdir/Packages.gz \
            | grep-dctrl -F Package $name -s Package,Version \
            >> $package.deb_packages.txt

#        echo '' >> $PACKAGE.deb_packages.txt
    done < $package.requirements.txt
}


if is_option_set 'recursive'; then
    if [[ $install_mode == 'stackforge' ]]; then
        if [[ -f packages.processed ]]; then
            if [[ -n "$(grep $install_from packages.processed)" ]]; then
                echo "Package '$install_from' was already processed."
                exit
            fi
        fi
    fi
fi


case $action in
    install)
        pip_install_dryrun $PACKAGE
        get_requirements
        parse_requirements
        search_in_global_requirements $PACKAGE
        search_deb_packages $PACKAGE
    ;;
    search)
        search_in_global_requirements $PACKAGE
        search_deb_packages $PACKAGE
    ;;
esac


if is_option_set 'recursive'; then
    echo "$PACKAGE" >> packages.processed
    cat $PACKAGE.requirements.txt >> murano.requirements.txt
    while read -r p; do
        ./get-pip-deps.sh -r -S $p
    done < packages.to_process
fi
