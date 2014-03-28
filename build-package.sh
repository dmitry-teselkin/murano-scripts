#!/bin/bash -x

PACKAGE=$1

BUILD_DIR='_builddir'


BUILD_DIR="$(pwd)/$BUILD_DIR"

PKG_NAME=
PKG_VERSION=
PKG_VERSION_LONG=


function prepare_sources() {
	local path=$1

	pushd $path

	git clean -fdx

	PKG_NAME=$(python setup.py --name | tail -1)
	PKG_VERSION_LONG=$(python setup.py --version | tail -1)
	PKG_VERSION=$(echo "$PKG_VERSION_LONG" | perl -pe 's|(\d+\.\d+\.[\d\w]+).*|\1|')

	python setup.py sdist

	cp dist/${PKG_NAME}-${PKG_VERSION_LONG}.tar.gz $BUILD_DIR

	popd


	pushd $BUILD_DIR

	tar xzvf ${PKG_NAME}-${PKG_VERSION_LONG}.tar.gz
	rm -f ${PKG_NAME}-${PKG_VERSION_LONG}.tar.gz
	mv ${PKG_NAME}-${PKG_VERSION_LONG} ${PKG_NAME}-${PKG_VERSION}

	tar czvf ${PKG_NAME}_${PKG_VERSION}.orig.tar.gz ${PKG_NAME}-${PKG_VERSION}

	popd
}


function prepare_specs() {
	local path=$1

	pushd $path
	cp -r debian ${BUILD_DIR}/${PKG_NAME}-${PKG_VERSION}
	popd


	pushd ${BUILD_DIR}/${PKG_NAME}-${PKG_VERSION}/debian

	cat << EOF > changelog.new
${PKG_NAME} (${PKG_VERSION}-1) unstable; urgency=low

  * Automated build

 -- root <dteselkin@mirantis.com>  $(date -R)

$(cat changelog)
EOF
	mv changelog.new changelog

	popd
}


function build_package() {
	pushd ${BUILD_DIR}/${PKG_NAME}-${PKG_VERSION}
	dpkg-buildpackage -us -uc
	popd
}


function clean_build_dir() {
	if [[ -n "${BUILD_DIR}" ]]; then
		rm -rf ${BUILD_DIR}/*
	fi
}


function extract_package() {
	pushd ${BUILD_DIR}
	mkdir content
	dpkg -x ${PKG_NAME}_${PKG_VERSION}-1_all.deb content
	popd
}


clean_build_dir
prepare_sources 'murano-api'
prepare_specs 'murano-api-build'
build_package
extract_package

