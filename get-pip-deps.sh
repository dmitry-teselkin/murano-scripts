#!/bin/bash

PACKAGE=${PACKAGE:-''}
PIP_BUILD_DIR=/tmp/pip_build_$(whoami)
FUEL_50_TESTING='http://osci-obs.vm.mirantis.net:82/ubuntu-fuel-5.0-testing/ubuntu/'
FUEL_50_STABLE='http://osci-obs.vm.mirantis.net:82/ubuntu-fuel-5.0-stable/ubuntu/'
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
    local n
    local v

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
            n=$(cd "$install_from" && (python setup.py --name | tail -1))
            v=$(cd "$install_from" && (python setup.py --version | tail -1))

            rm -f $PACKAGE.requirements.txt
            cat $install_from/requirements.txt \
                | grep -v '^#' \
                | xargs -I % printf "%\t#From: $n==$v\n" \
                >> $PACKAGE.requirements.txt
        ;;
        url)
            local tmpdir=$(mktemp -d)
            git clone $install_from $tmpdir

            install_from=$tmpdir
            PACKAGE=$(cd "$install_from" && (python setup.py --name | tail -1))
            n=$(cd "$install_from" && (python setup.py --name | tail -1))
            v=$(cd "$install_from" && (python setup.py --version | tail -1))

            rm -f $PACKAGE.requirements.txt
            cat $install_from/requirements.txt \
                | grep -v '^#' \
                | xargs -I % printf "%\t#From: $n==$v\n" \
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
    pip install $pip_install_opts $install_from >> $pip_install_log

    cat $pip_install_log \
        | grep '^Requirement already satisfied' \
        | perl -pe 's|.*\)\:\s+(.*?)\s+in.*?\(from\s+(.*)\)|\1\t#From: \2|' \
        >> $PACKAGE.requirements.txt

#    rm -f $pip_install_log
}


function get_requirements() {
    local d
    local n
    local v

    for d in $(ls -d $PIP_BUILD_DIR/*/); do
        n=$(cd $d && (python setup.py --name | tail -1))
        v=$(cd $d && (python setup.py --version | tail -1))
        if [[ -f $d/requirements.txt ]]; then
            cat $d/requirements.txt \
                | grep -v '^#' \
                | xargs -I % printf "%\t#From: $n==$v\n" \
                >> $PACKAGE.requirements.txt
        fi
    done
}


function parse_requirements() {
    local f=$PACKAGE.requirements.txt

    sort -u $f \
        | grep -v '^$' \
        > $f.tmp
    mv $f.tmp $f

    cat $f \
        | perl -pe 's|^(.*?)\s*#.*$|\1|' \
        | grep -v '^$' \
        | sed 's/ //g' \
        | sed 's/\xc2\xa0//g' \
        | perl -pe 's|(.*?)([<>=!].*)|\1 \2|' \
        | sed 's/,/ /g' \
        | sort -u \
        > $f.tmp

    rm -f $PACKAGE.requirements_table.txt
    touch $PACKAGE.requirements_table.txt
    while read -r line; do
        parse_constraint_string $line >> $PACKAGE.requirements_table.txt
    done < $f.tmp
}


function parse_constraint_string() {
    local name=$1
    local c_eq=
    local c_ne=
    local c_ge=
    local c_gt=
    local c_le=
    local c_lt=
    shift

    while [[ -n "$1" ]]; do
        case $1 in
            '=='*) c_eq=${1#\=\=} ;;
            '!='*) c_ne=${1#\!\=} ;;
            '>='*) c_gt=${1#\>\=}; c_ge='ge' ;;
            '<='*) c_lt=${1#\<\=}; c_le='le' ;;
            '>'*)  c_gt=${1#\>};   c_ge='gt' ;;
            '<'*)  c_lt=${1#\<};   c_le='lt' ;;
        esac
        shift
    done
    printf "$name:$c_eq:$c_ge:$c_gt:$c_le:$c_lt:$c_ne\n"
}


function build_constraint_string() {
    local t
    local s=''

    IFS=':' read -a t <<< "$1"
    if [[ -n "${t[1]}" ]]; then
        echo -n "==${t[1]}"
        return
    fi
    case ${t[2]} in
        gt) s=">${t[3]} ";;
        ge) s=">=${t[3]} ";;
    esac
    case ${t[4]} in
        lt) s="$s<${t[5]} ";;
        le) s="$s<=${t[5]} ";;
    esac
    if [[ -n ${t[6]} ]]; then
        s="$s !=${t[6]}"
    fi
    echo -n $s
}


function search_in_global_requirements() {
    local package=$1
    local t
    local name
    local version
    local line

    rm -f 'global-requirements.txt'
    wget $GLOBAL_REQUIREMENTS_URL

    rm -f $package.global_requirements.txt

    while read -r line; do
        IFS=':' read -a t <<< "$line"

        name=${t[0]}
        version=$(build_constraint_string $line)

        echo "*** [$(echo $name $version)] ***" >> $package.global_requirements.txt

        grep $name 'global-requirements.txt' >> $package.global_requirements.txt
    done < $package.requirements_table.txt
}


function search_deb_packages() {
    local package=$1
    local tempdir=$(mktemp -d)
    local t
    local name
    local version
    local line

    wget $FUEL_50_TESTING/Packages.gz -O $tempdir/Packages_Testing.gz
    wget $FUEL_50_STABLE/Packages.gz -O $tempdir/Packages_Stable.gz

    rm $package.deb_packages.txt

    while read -r line; do
        IFS=':' read -a t <<< "$line"

        name=${t[0]}
        version=$(build_constraint_string $line)
        echo $name $version

        echo "*** [$(echo $name $version)] ***" >> $package.deb_packages.txt

        echo "--- FUEL 5.0 TESTING ---" >> $package.deb_packages.txt
        zcat $tempdir/Packages_Testing.gz \
            | grep-dctrl -i -F Package -e "(^|-)${name}\$" -s Package,Version \
            | awk '/Package/{p=$2;next} /Version/{print p " " $2}' \
            >> $package.deb_packages.txt

        echo "--- FUEL STABLE ---" >> $package.deb_packages.txt
        zcat $tempdir/Packages_Stable.gz \
            | grep-dctrl -i -F Package -e "(^|-)${name}\$" -s Package,Version \
            | awk '/Package/{p=$2;next} /Version/{print p " " $2}' \
            >> $package.deb_packages.txt

#        echo '' >> $PACKAGE.deb_packages.txt
    done < $package.requirements_table.txt
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
        parse_requirements
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
