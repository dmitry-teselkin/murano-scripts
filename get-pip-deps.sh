#!/bin/bash

if [[ $# -eq 1 ]]; then
    install_mode='pip'
    install_from=$1
else
    while [[ -n $1 ]]; do
        case $1 in
            -d|--dir)
                install_mode='dir'
                install_from=$2
                shift 2
            ;;
            -u|--url)
                install_mode='url'
                install_from=$2
                shift 2
            ;;
            -p|--pip)
                install_mode='pip'
                install_from=$2
                shift 2
            ;;
            *)
                echo "Unrecognised parameter '$1'"
            ;;
        esac
        shift
    done
fi

echo "install_mode='$install_mode'"
echo "install_from='$install_from'"

PACKAGE=''
PIP_BUILD_STACK=/tmp/pip_build_stack
DEB_REPO_URL='http://osci-obs.vm.mirantis.net:82/ubuntu-fuel-5.0-testing/ubuntu/'


function die() {
    cat << EOF

SCRIPT FAILED
$@

EOF
exit 1
}


function pip_install_dryrun() {
    local pip_install_opts='--no-install --verbose'

    case $install_mode in
        dir)
            pip_install_opts="$pip_install_opts -e"
            if [[ ! -d $install_from ]]; then
                die "No such folder '$install_from'"
            fi
            PACKAGE=$(cd "$install_from" && (python setup.py --name | tail -1))
        ;;
        pip)
            PACKAGE=$install_from
        ;;
        url)
            die "Installation from URL is not supported yet."
        ;;
        *)
            die "Unrecognized installation mode '$install_mode'"
        ;;
    esac

    if [[ -z "$PACKAGE" ]]; then
        die "Package name is empty."
    fi

    rm -rf /tmp/pip_build_*
    rm -f $PACKAGE.requirements.txt

    local pip_install_log=$(mktemp)
    pip_install_log=./pip_install.log

    rm -f $pip_install_log
    pip install $pip_install_opts $install_from | tee $pip_install_log

    cat $pip_install_log \
        | awk '/^Requirement already satisfied/ {print $8}' \
        >> $PACKAGE.requirements.txt
}


function get_requirements() {
    local d

    for d in $(ls -d $PIP_BUILD_STACK/*/); do
        if [[ -f $d/requirements.txt ]]; then
            cat $d/requirements.txt >> $PACKAGE.requirements.txt
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


function search_deb_packages() {
    local tempdir=$(mktemp -d)
    local name, version

    wget $DEB_REPO_URL/Packages.gz -P $tempdir

    rm $PACKAGE.deb_packages.txt

    while read -r name version; do
        echo "**[$(echo $name $version)]**" >> $PACKAGE.deb_packages.txt
#        echo '' >> $PACKAGE.deb_packages.txt

        zcat $tempdir/Packages.gz \
            | grep-dctrl -F Package $name -s Package,Version \
            >> $PACKAGE.deb_packages.txt

#        echo '' >> $PACKAGE.deb_packages.txt
    done < $PACKAGE.requirements.txt
}


pip_install_dryrun $PACKAGE
get_requirements
parse_requirements
search_deb_packages
