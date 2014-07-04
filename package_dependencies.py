#!/usr/bin/env python2

import urllib2
import re
import os
from pushd import pushd
from getpass import getuser

from sh import python
from sh import tail
from sh import pip
from sh import rm, mkdir
from sh import git
from uuid import uuid4

from tempfile import mkdtemp
from sh import grep_dctrl
from sh import repoquery
from sh import wget
from sh import awk
from sh import zcat
import os.path, time
from lxml import etree

import argparse

# package_repository classes
#===========================

class PackageRepository():
    def __init__(self, name):
        self.name = name
        self.base_url = ''
        self.repo_url = ''
        self.index_file = ''
        self.cache_dir = mkdtemp()
        self.cache_uuid = uuid4()
        self.cache_threshold_sec = 60 * 60
        self.broken = False
        print("")
        print("Caching data for repository '{0}'".format(name))

    def grep_package(self, name, pattern=None):
        pass

    def test_cache(self):
        index_file_path = os.path.join(self.cache_dir, self.index_file)
        if os.path.exists(index_file_path):
            file_age = time.time() - os.path.getctime(index_file_path)
            if file_age > self.cache_threshold_sec:
                print("File '{0}' too old.".format(index_file_path))
                return False
        else:
            print("No such file '{0}'".format(index_file_path))
            return False

        print("Cache is up-to-date (index file updated {0} sec ago).".format(file_age))
        return True

    def update_cache(self):
        pass

    def __str__(self):
        index_file_url = '/'.join([self.repo_url, self.index_file])
        index_file_path = os.path.join(self.cache_dir, self.index_file)

        return "Remote URL: {0}, Cached file: {1}".format(
            index_file_url,
            index_file_path
        )


class PackageRepositoryDeb(PackageRepository):
    def __init__(self, name):
        PackageRepository.__init__(self, name=name)
        self.index_file = 'Packages.gz'

    def grep_package(self, name, pattern=None):
        pattern = pattern if pattern else "(^|-){0}$"
        try:
            return [
                line.rstrip().split(' ', 1)
                for line in awk(
                    grep_dctrl(
                        zcat(os.path.join(self.cache_dir, self.index_file)),
                        '-F', 'Package',
                        '-e', pattern.format(name),
                        '-s', 'Package,Version'
                    ),
                    '/Package/{p=$2;next} /Version/{print p " " $2}'
                )
            ]
        except:
            return []

    def update_cache(self):
        if not self.test_cache():
            rm(self.cache_dir, '-rf')
            self.cache_dir = mkdtemp()

            index_file_url = '/'.join([self.repo_url, self.index_file])
            index_file_path = os.path.join(self.cache_dir, self.index_file)

            try:
                print("Downloading index file '{0}' --> '{1}' ...".format(
                    index_file_url, index_file_path
                ))
                wget(index_file_url, '-O', index_file_path)
            except:
                self.broken = True


class PackageRepositoryRpm(PackageRepository):
    def __init__(self, name):
        PackageRepository.__init__(self, name=name)
        self.index_file = 'repodata/repomd.xml'

    def grep_package(self, name, pattern=None):
        try:
            package_list = []
            found_items = [
                line.rstrip()
                for line in repoquery(
                    "--repofrompath={0},{1}".format(self.cache_uuid, self.cache_dir),
                    '--search', name)
            ]

            for item in found_items:
                item_info = [
                    line.rstrip()
                    for line in repoquery(
                        "--repofrompath={0},{1}".format(self.cache_uuid, self.cache_dir),
                        '--info', item)
                ]

                pkg_info = {}
                for record in item_info:
                    try:
                        key, value = record.rstrip().split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        if key == 'Description':
                            break
                        pkg_info[key] = value
                    except:
                        continue
                package_list.append([pkg_info['Name'], pkg_info['Version']])

            return package_list
        except:
            return []

    def update_cache(self):
        if not self.test_cache():
            rm(self.cache_dir, '-rf')
            self.cache_dir = mkdtemp()
            self.cache_uuid = uuid4()
            mkdir(os.path.join(self.cache_dir, 'repodata'))

            index_file_url = '/'.join([self.repo_url, self.index_file])
            index_file_path = os.path.join(self.cache_dir, self.index_file)

            try:
                print("Downloading index file '{0}' --> '{1}' ...".format(
                    index_file_url, index_file_path
                ))
                wget(index_file_url, '-O', index_file_path)
            except:
                self.broken = True
                return

            try:
                xmlroot = etree.parse(index_file_path).getroot()
                xmlns = xmlroot.nsmap[None]
                for item in xmlroot.findall("{{{0}}}data".format(xmlns)):
                    for subitem in item.findall("{{{0}}}location".format(xmlns)):
                        location = subitem.get('href')
                        url = '/'.join([self.repo_url, location])
                        path = '/'.join([self.cache_dir, location])
                        print("Downloading file '{0}' --> '{1}' ...".format(
                            url, path
                        ))
                        wget(url, '-O', path)
            except:
                self.broken = True


class MirantisInternalRepositoryDeb(PackageRepositoryDeb):
    def __init__(self, name='Mirantis Internal DEB Repository', repo_type='product',
                 dist_name='ubuntu', dist_release='precise',
                 fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryDeb.__init__(self, name="{0} ({1})".format(name, repo_type))
        self.base_url = 'http://osci-obs.vm.mirantis.net:82'
        self.base_url_suffix = 'osci'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type

        if repo_type == 'master':
            build_suffix = "{0}-fuel-master".format(self.dist_name)
        else:
            build_suffix = "{0}-fuel-{1}-{2}".format(self.dist_name, self.fuel_release, self.fuel_type)

        self.repo_url = "{0}/{1}/{2}".format(
            self.base_url, build_suffix, self.dist_name)


class MirantisPublicRepositoryDeb(PackageRepositoryDeb):
    def __init__(self, name='Mirantis Public DEB Repo', repo_type='product',
                 dist_name='ubuntu', dist_release='precise',
                 fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryDeb.__init__(self, name="{0} ({1})".format(name, repo_type))
        self.base_url = 'http://fuel-repository.mirantis.com'
        self.base_url_suffix = 'fwm'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type

        if repo_type == 'osci':
            self.base_url_suffix = 'osci'
            build_suffix = "{0}-fuel-{1}-{2}/{0}".format(
                self.dist_name, self.fuel_release, self.fuel_type)
        else:
            self.base_url_suffix = 'fwm'
            build_suffix = "{0}/{1}/dists/{2}/main/binary-amd64".format(
                self.fuel_release, self.dist_name, dist_release)

        self.repo_url = "{0}/{1}/{2}".format(
            self.base_url, self.base_url_suffix, build_suffix)


class MirantisInternalRepositoryRpm(PackageRepositoryRpm):
    def __init__(self, name='Mirantis Internal RPM Repo', repo_type='product',
                 dist_name='centos', dist_release='',
                 fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryRpm.__init__(self, name="{0} ({1})".format(name, repo_type))
        self.base_url = 'http://osci-obs.vm.mirantis.net:82'
        self.base_url_suffix = 'osci'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type

        if repo_type == 'master':
            build_suffix = "{0}-fuel-master".format(self.dist_name)
        else:
            build_suffix = "{0}-fuel-{1}-{2}".format(self.dist_name, self.fuel_release, self.fuel_type)

        self.repo_url = "{0}/{1}/{2}".format(
            self.base_url, build_suffix, self.dist_name)


class MirantisPublicRepositoryRpm(PackageRepositoryRpm):
    def __init__(self, name='Mirantis Public RPM Repo', repo_type='product',
                 dist_name='centos', dist_release='',
                 fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryRpm.__init__(self, name="{0} ({1})".format(name, repo_type))

        self.base_url = 'http://fuel-repository.mirantis.com'
        self.base_url_suffix = 'fwm'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type

        if repo_type == 'osci':
            self.base_url_suffix = 'osci'
            build_suffix = "{0}-fuel-{1}-{2}/{0}".format(
                self.dist_name, self.fuel_release, self.fuel_type)
        elif repo_type == 'master':
            self.base_url_suffix = 'repos'
            build_suffix = "{0}-fuel-master/{0}".format(self.dist_name)
        else:
            # Use product configuration by default
            self.base_url_suffix = 'fwm'
            build_suffix = "{0}/{1}/os/x86_64".format(
                self.fuel_release, self.dist_name)

        self.repo_url = "{0}/{1}/{2}".format(
            self.base_url, self.base_url_suffix, build_suffix)


class UpstreamPublicRepositoryRpm(PackageRepositoryRpm):
    def __init__(self, name='Upstream Public Rpm Repo',
                 dist_name='centos', dist_release='6.5',
                 fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryRpm.__init__(self, name=name)
        self.base_url = 'http://mirror.yandex.ru'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type
        self.repo_url = "{0}/{1}/{2}/os/x86_64".format(
            self.base_url, dist_name, dist_release, dist_name)


class UpstreamPublicRepositoryDeb(PackageRepositoryDeb):
    def __init__(self, name='Ubuntu Public Repository', dist_name='ubuntu',
                 dist_release='precise', fuel_release='5.0', fuel_type='stable'):
        PackageRepositoryDeb.__init__(self, name=name)
        self.base_url = 'http://mirror.yandex.ru'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type
        self.repo_url = "{0}/{1}/dists/{2}/main/binary-amd64".format(
            self.base_url, dist_name, dist_release)


class PackageRepositorySet():
    def __init__(self):
        self.repository_list = []
        self.custom_package_set = []

    def add(self, repository):
        repository.update_cache()
        if repository.broken:
            print("Repository '{0}' is broken.".format(repository.name))
            return

        print("Registering repository '{0}' ({1})".format(repository.name, repository.repo_url))
        self.repository_list.append(repository)

    def add_custom_packages(self, custom_package_set=None):
        if custom_package_set:
            self.custom_package_set = custom_package_set

    def grep_package(self, name):
        for repository in self.repository_list:
            pattern = None
            if name in self.custom_package_set:
                name = self.custom_package_set.deb_package_for(name)
                pattern = "{0}"
            for p, v in repository.grep_package(name=name, pattern=pattern):
                yield repository, p, v


#===========================


# Package alias classes
#======================

class PackageAlias():
    def __init__(self, name=''):
        self.name = name

        self.deb_package = {}
        self.rpm_package = {}

    def deb(self, name='', repo=''):
        self.deb_package = {
            'name': name,
            'repo': repo
        }
        return self

    def rpm(self, name='', repo=''):
        self.rpm_package = {
            'name': name,
            'repo': repo
        }
        return self

    def __str__(self):
        return "Package '{0}' // DEB: '{1}' from '{2}' // RPM: '{3}' from '{4}'".format(
            self.name,
            self.deb_package['name'],
            self.deb_package['repo'],
            self.rpm_package['name'],
            self.rpm_package['repo']
        )


class CustomPackageSet():
    def __init__(self):
        self.items = {}

    def add(self, item):
        self.items[item.name] = item

    def __contains__(self, item):
        return item in self.items.keys()

    def deb_package_for(self, name):
        item = self.items.get(name, None)
        if item:
            return item.deb_package['name']
        else:
            return None

    def rpm_package_for(self, name):
        item = self.items.get(name, None)
        if item:
            return item.rpm_package['name']
        else:
            return None


#======================


class PythonPackage():
    def __init__(self, string, from_package=None):
        self._raw_string = string.split('#')[0].rstrip()
        self._from_package = from_package
        self.name = ""
        self.constraints = []
        self.parents = []

        if self._raw_string:
            self.looks_good = True
        else:
            self.looks_good = False
            return

        match = re.search('^(.*?)([<>!=].*)$', self._raw_string)
        if match:
            self.name = match.group(1)
            constraint = match.group(2).split(',')
        else:
            self.name = self._raw_string
            constraint = []

        for c in constraint:
            match = re.search('^([<>!=]=?)(.*?)$', c)
            self.constraints.append(
                [
                    {
                        '>': 'gt',
                        '<': 'lt',
                        '>=': 'ge',
                        '<=': 'le',
                        '==': 'eq',
                        '!=': 'ne'
                    }.get(match.group(1), ''),
                    match.group(2)
                ]
            )

        if self._from_package:
            for string in self._from_package.split('->'):
                package = PythonPackage(string)
                if package.looks_good:
                    self.parents.append(package)

    def __repr__(self):
        return "(Name: '{0}', Constraints: [{1}], Parents: [{2}])".format(
            self.name,
            ' , '.join([':'.join(c) for c in self.constraints]),
            ' -> '.join([repr(p) for p in self.parents])
        )

    def __str__(self):
        return "{0}{1}".format(self.name, self.str_constraint())

    def equals(self, package, strict=False):
        if self.name != package.name:
            return False

        if len(self.constraints) != len(package.constraints):
            return False

        for c in self.constraints:
            if not c in package.constraints:
                return False

        return True

    def str_constraint(self):
        return ','.join(
            [
                "{0}{1}".format(
                    {
                        'gt': '>',
                        'lt': '<',
                        'ge': '>=',
                        'le': '<=',
                        'eq': '==',
                        'ne': '!='
                    }.get(c[0]), c[1]
                )
                for c in self.constraints
            ]
        )


class GlobalRequirements():
    def __init__(self, url):
        self.entries = []
        print("")
        print("Loading Global Requirements ...")
        resp = urllib2.urlopen(url)
        for line in resp.readlines():
            req_entry = PythonPackage(line)
            if req_entry.looks_good:
                self.entries.append(req_entry)
        resp.close()
        print("Done. {0} records loaded.".format(len(self.entries)))

    def get_package(self, name):
        for package in self.entries:
            if package.name == name:
                return package

    def validate(self, package):
        names = [n.name for n in self.entries]
        if package.name in names:
            greq_package = self.get_package(package.name)
            if greq_package.equals(package):
                return [True, greq_package]
            else:
                return [False, greq_package]
        else:
            return [False, None]


class RequirementsResolver():
    def __init__(self):
        self._pip_install_opts = ['--no-install', '--verbose']
        self.package_name = ""
        self.entries = []
        pass

    def _add_pip_package(self, string, from_package=None):
        package = PythonPackage(string, from_package=from_package)
        if package.looks_good:
            self.entries.append(package)

    def resolve_from_dir(self, path):
        self._pip_install_opts.append('-e')
        if not os.path.exists(path):
            raise Exception("Path not found '{0}'".format(path))

        rm('-r', '-f', "/tmp/pip_build_{0}".format(getuser()))

        with pushd(path):
            print("")
            print("'git status' in '{0}':".format(path))
            print("------------")
            print(git('status'))
            print("------------")

            self.package_name = tail(python("setup.py", "--name"), "-1").rstrip()

            print("")
            print("Gathering package requirements ...")
            for line in pip('install', self._pip_install_opts, '.'):
                string = line.rstrip()
                match = re.search(
                    'Downloading/unpacking (.*?) \(from (.*?)\)',
                    string
                )
                if match:
                    self._add_pip_package(match.group(1), from_package=match.group(2))
                    continue

                match = re.search(
                    'Requirement already satisfied.*?: (.*?) in .*?\(from (.*?)\)',
                    string
                )
                if match:
                    self._add_pip_package(match.group(1), from_package=match.group(2))
                    continue
            print("Done. {0} records found.".format(len(self.entries)))

    def resolve_from_stackforge(self, url):
        pass

    def resolve_from_git(self, url):
        pass

    def validate(self, global_requirements):
        """
        Returns a dict of dicts:
            <package name>: {
                'orig_package': <package found in component's requirements>,
                'greq_package': <package found in global requirements>,
                'status': <if package complies with global requirements>,
                'is_direct_dependency': <if package is a direct dependency for the component>
            }
        """
        result = {}
        for package in self.entries:
            status, greq_package = global_requirements.validate(package)
            result[package.name] = {
                'orig_package': package,
                'greq_package': greq_package,
                'status': status,
                'is_direct_dependency': self.package_name == package.parents[0].name
            }
        return result


class ReportGenerator():
    def __init__(self, package_name):
        self.package_name = package_name
        self.header = ''

    def _top_block_delimiter(self, header):
        self.header = header
        print("")
        print(self.header)
        print("=" * len(self.header))

    def _bottom_block_delimiter(self):
        print("=" * len(self.header))

    def print_report_block(self, validation_result, compatible=False, direct=False):
        str_direct = 'direct' if direct else 'indirect'
        str_compatible = 'compatible' if compatible else 'incompatible'

        self._top_block_delimiter("{0} dependencies {1} with global requirements:".format(
            str_direct.capitalize(), str_compatible
        ))
        count = 0
        for key in sorted(validation_result.keys()):
            item = validation_result[key]
            if item['status'] == compatible and item['is_direct_dependency'] == direct:
                count += 1
                if item['greq_package']:
                    greq_status = "Global Requirements: {0}".format(item['greq_package'])
                else:
                    greq_status = "Not found in Global Requirements"

                if direct:
                    str_parents = "  "
                else:
                    str_parents = "(From: {0})".format(
                        " -> ".join([str(p) for p in item['orig_package'].parents])
                    )

                print("{0} {1} # {2}".format(item['orig_package'], str_parents, greq_status))
        self._bottom_block_delimiter()

        print("Total: {0}".format(count))

    def print_machine_friendly_report_block(self, validation_result, compatible=False, direct=False):
        str_direct = 'direct' if direct else 'indirect'
        str_compatible = 'compatible' if compatible else 'incompatible'
        delimiter = ";"

        print("#")
        for key in sorted(validation_result.keys()):
            item = validation_result[key]
            if item['status'] == compatible and item['is_direct_dependency'] == direct:
                str_parents = " -> ".join([str(p) for p in item['orig_package'].parents])

                print("{1:35}{0}{2:15}{0}{3:10}{0}{4:35}{0}{5}".format(
                    delimiter,
                    item['greq_package'],
                    str_compatible,
                    str_direct,
                    item['orig_package'],
                    str_parents
                ))

    def package_matching_report_block(self, validation_result=None, repository_set=None, direct=True):
        str_direct = 'direct' if direct else 'indirect'

        for key in sorted(validation_result.keys()):
            item = validation_result[key]
            if item['is_direct_dependency'] == direct:
                str_orig_package = str(item['orig_package'].name)
                str_greq_package = str(item['greq_package'])
                print("# {0}".format(item['orig_package']))
                for r, p, v in repository_set.grep_package(item['orig_package'].name):
                    print("{1:25}{0}{2:10}{0}{3:35}{0}{4:40}{0}{5}".format(
                        ';',
                        str_orig_package,
                        str_direct,
                        str_greq_package,
                        ' '.join([p, v]),
                        r.name
                    ))

    def global_requirements_validation(self, validation_result):
        print("")
        print("Report for package '{0}':".format(self.package_name))

        self.print_report_block(validation_result=validation_result,
                                compatible=True, direct=True)
        self.print_report_block(validation_result=validation_result,
                                compatible=False, direct=True)
        self.print_report_block(validation_result=validation_result,
                                compatible=True, direct=False)
        self.print_report_block(validation_result=validation_result,
                                compatible=False, direct=False)

    def machine_friendly_report(self, validation_result):
        print("")
        print("#{1:35}{0}{2:15}{0}{3:10}{0}{4:35}{0}{5}".format(
            ';',
            'Global Requirements',
            'Is Compatible',
            'Is Direct Dependency',
            'Component Requirements',
            'Required By'
        ))
        self.print_machine_friendly_report_block(validation_result=validation_result,
                                                 compatible=True, direct=True)
        self.print_machine_friendly_report_block(validation_result=validation_result,
                                                 compatible=False, direct=True)
        self.print_machine_friendly_report_block(validation_result=validation_result,
                                                 compatible=True, direct=False)
        self.print_machine_friendly_report_block(validation_result=validation_result,
                                                 compatible=False, direct=False)
        print("")

    def package_matching(self, validation_result=None, repository_set=None):
        print("")
        print("Looking for packages matching:")
        self.package_matching_report_block(validation_result=validation_result,
                                             repository_set=repository_set, direct=True)
        self.package_matching_report_block(validation_result=validation_result,
                                             repository_set=repository_set, direct=False)
        print("")

#===============================================================================

custom_python_packages = CustomPackageSet()

custom_python_packages.add(PackageAlias(name='SQLAlchemy').deb(name='python-sqlalchemy'))
custom_python_packages.add(PackageAlias(name='PasteDeploy').deb(name='python-pastedeploy'))
custom_python_packages.add(PackageAlias(name='Routes').deb(name='python-routes'))
custom_python_packages.add(PackageAlias(name='sqlalchemy-migrate').deb(name='python-migrate'))
custom_python_packages.add(PackageAlias(name='pycrypto').deb(name='python-crypto'))
custom_python_packages.add(PackageAlias(name='Paste').deb(name='python-paste'))
custom_python_packages.add(PackageAlias(name='pyOpenSSL').deb(name='python-openssl'))
custom_python_packages.add(PackageAlias(name='repoze.lru').deb(name='repoze'))
custom_python_packages.add(PackageAlias(name='Tempita').deb(name='python-tempita'))
custom_python_packages.add(PackageAlias(name='Babel').deb(name='python-babel'))
custom_python_packages.add(PackageAlias(name='PyYAML').deb(name='python-yaml'))
custom_python_packages.add(PackageAlias(name='PrettyTable').deb(name='python-prettytable'))
custom_python_packages.add(PackageAlias(name='pytz').deb(name='python-tz'))
custom_python_packages.add(PackageAlias(name='WebOb').deb(name='python-webob'))

#===============================================================================

parser = argparse.ArgumentParser(description="Resolve package dependencies")

parser.add_argument('--git-dir', dest='git_dir', default='/home/dim/Temp/glance',
                    help='Local GIT repository path.')

parser.add_argument('--greq-branch', dest='greq_branch', default='master',
                    help='Global Requirements branch.')

parser.add_argument('--fuel-release', dest='fuel_release', default='5.0.1',
                    help='Current FUEL release.')

parser.add_argument('--rpm', dest='check_rpm_packages', action='store_true',
                    help='Search for RPM packages matching the requirements.')
parser.add_argument('--rpm-os-version', dest='rpm_os_version', default='centos',
                    help='Specify OS name for RPM package repository.')
parser.add_argument('--rpm-os-release', dest='rpm_os_release', default='6.5',
                    help='Specify OS release name for RPM package repository.')

parser.add_argument('--deb', dest='check_deb_packages', action='store_true',
                    help='Search for DEB packages matching the requirements.')
parser.add_argument('--deb-os-version', dest='deb_os_version', default='ubuntu',
                    help='Specify OS name for DEB package repository.')
parser.add_argument('--deb-os-release', dest='deb_os_release', default='precise',
                    help='Specify OS release name for DEB package repository.')

parser.add_argument('--repo-type', dest='mirantis_repo_type', default='product',
                    help='Mirantis repository for package search.')

parser.add_argument('--internal', dest='use_internal_mirantis_repo', action='store_true',
                    help='Use internal Mirantis repository for package search.')
parser.add_argument('--public', dest='use_public_mirantis_repo', action='store_true',
                    help='Use public Mirantis repository for package search.')
parser.add_argument('--upstream', dest='use_upstream_public_repo', action='store_true',
                    help='Use upstream (DEB or RPM) repository for package search.')

args = parser.parse_args()

#===============================================================================

greq_branch = {
    'icehouse': 'stable/icehouse'
}.get(args.greq_branch, args.greq_branch)

greq_url = "https://raw.githubusercontent.com/openstack/requirements/{0}/global-requirements.txt".format(greq_branch)

print("""
SUMMARY:
--------
Resolving dependencies for python component located in local GIT repository '{0}'
Global Requirements are from '{1}' branch, fetched from URL '{2}'
Target FUEL release: {3}
--------""".format(
    args.git_dir,
    args.greq_branch,
    greq_url,
    args.fuel_release
))

greq = GlobalRequirements(greq_url)

reqs = RequirementsResolver()
reqs.resolve_from_dir(args.git_dir)

validation_result = reqs.validate(greq)

report = ReportGenerator(package_name=reqs.package_name)
report.machine_friendly_report(validation_result=validation_result)

repo_set = PackageRepositorySet()
repo_set.add_custom_packages(custom_package_set=custom_python_packages)

validate_packages = False
if args.check_rpm_packages:
    validate_packages = True
    if args.use_internal_mirantis_repo:
        repo_set.add(MirantisInternalRepositoryRpm(
            repo_type=args.mirantis_repo_type, fuel_release=args.fuel_release))
    if args.use_public_mirantis_repo:
        repo_set.add(MirantisPublicRepositoryRpm(
            repo_type=args.mirantis_repo_type, fuel_release=args.fuel_release))
    if args.use_upstream_public_repo:
        repo_set.add(UpstreamPublicRepositoryRpm(fuel_release=args.fuel_release))

if args.check_deb_packages:
    validate_packages = True
    if args.use_internal_mirantis_repo:
        repo_set.add(MirantisInternalRepositoryDeb(
            repo_type=args.mirantis_repo_type, fuel_release=args.fuel_release))
    if args.use_public_mirantis_repo:
        repo_set.add(MirantisPublicRepositoryDeb(
            repo_type=args.mirantis_repo_type, fuel_release=args.fuel_release))
    if args.use_upstream_public_repo:
        repo_set.add(UpstreamPublicRepositoryDeb(fuel_release=args.fuel_release))

if validate_packages:
    report.package_matching(validation_result=validation_result,
                            repository_set=repo_set)


# Example of produced output:
# http://paste.openstack.org/show/85047/