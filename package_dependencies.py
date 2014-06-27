#!/usr/bin/env python2

import urllib2
import re
import os
from pushd import pushd
from getpass import getuser


from sh import python
from sh import tail
from sh import pip
from sh import rm
from sh import git


from tempfile import mkdtemp
from sh import grep_dctrl
from sh import wget
from sh import awk
from sh import zcat
import os.path, time

import argparse

# package_repository classes
#===========================

class PackageRepository():
    def __init__(self, name):
        self.name = name
        self.base_url = ''
        self.packages_gz_url = ''
        self.local_packages_gz = ''
        self.cache_threshold_sec = 60 * 60
        self.broken = False
        print("")
        print("New repository '{0}'".format(name))

    def grep_package(self, name, pattern=None):
        pattern = pattern if pattern else "(^|-){0}$"
        try:
            return [
                line.rstrip().split(' ', 1)
                for line in awk(
                    grep_dctrl(
                        zcat(self.local_packages_gz),
                            '-F', 'Package',
                            '-e', pattern.format(name),
                            '-s', 'Package,Version'
                        ),
                    '/Package/{p=$2;next} /Version/{print p " " $2}'
                )
            ]
        except:
            return []

    def test_cache(self):
        if self.local_packages_gz:
            if os.path.exists(self.local_packages_gz):
                file_age = time.time() - os.path.getctime(self.local_packages_gz)
                if file_age > self.cache_threshold_sec:
                    print("File '{0}' too old.".format(self.local_packages_gz))
                    return False
            else:
                print("No such file '{0}'".format(self.local_packages_gz))
                return False
        else:
            print("Local Packages.gz isn't defined yet.")
            return False
        print("Cached file is up-to-date (updated {0} sec ago).".format(file_age))
        return True

    def update_cache(self):
        if not self.test_cache():
            print("Downloading file ...")
            self.local_packages_gz = mkdtemp() + "/Packages.gz"
            try:
                wget(self.packages_gz_url, '-O', self.local_packages_gz)
            except:
                self.broken = True

    def __str__(self):
        return "Remote URL: {0}, Cached file: {1}".format(
            self.packages_gz_url,
            self.local_packages_gz
        )


class MirantisOSCIRepository(PackageRepository):
    def __init__(self, name='Mirantis OSCI Repository', dist_name='ubuntu',
                 dist_release='precise', fuel_release='5.0', fuel_type='stable'):
        PackageRepository.__init__(self, name=name)
        #self.base_url = 'http://osci-obs.vm.mirantis.net:82'
        self.base_url = 'http://fuel-repository.mirantis.com/osci'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type
        self.packages_gz_url = "{0}/{1}-fuel-{2}-{3}/{1}/Packages.gz".format(
            self.base_url, self.dist_name, self.fuel_release, self.fuel_type)


class MirantisPublicRepository(PackageRepository):
    def __init__(self, name='Mirantis Public Repository', dist_name='ubuntu',
                 dist_release='precise', fuel_release='5.0', fuel_type='stable'):
        PackageRepository.__init__(self, name=name)
        self.base_url = 'http://fuel-repository.mirantis.com/fwm'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type
        self.packages_gz_url = "{0}/{1}/{2}/dists/{3}/main/binary-amd64/Packages.gz".format(
            self.base_url, fuel_release, dist_name, dist_release)


class UbuntuPublicRepository(PackageRepository):
    def __init__(self, name='Ubuntu Public Repository', dist_name='ubuntu',
                 dist_release='precise', fuel_release='5.0', fuel_type='stable'):
        PackageRepository.__init__(self, name=name)
        self.base_url = 'http://ru.archive.ubuntu.com'
        self.dist_name = dist_name
        self.dist_release = dist_release
        self.fuel_release = fuel_release
        self.fuel_type = fuel_type
        self.packages_gz_url = "{0}/{1}/dists/{2}/main/binary-amd64/Packages.gz".format(
            self.base_url, dist_name, dist_release)


class PackageRepositorySet():
    def __init__(self):
        self.repository_list = []
        self.custom_package_set = None

    def add(self, repository):
        repository.update_cache()
        if repository.broken:
            print("Repository '{0}' is broken.".format(repository.name))
            return

        print("Adding repository '{0}' ({1})".format(repository.name, repository.packages_gz_url))
        self.repository_list.append(repository)

    def add_custom_packages(self, custom_package_set=None):
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
            print("Calculating package requirements ...")
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
            {
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

    def validation_report(self, validation_result):
        print("")
        print("Report for package '{0}':".format(self.package_name))

        self.print_report_block(validation_result=validation_result,
                                compatible=True, direct=True)
        self.print_report_block(validation_result=validation_result,
                                compatible=True, direct=False)
        self.print_report_block(validation_result=validation_result,
                                compatible=False, direct=True)
        self.print_report_block(validation_result=validation_result,
                                compatible=False, direct=False)


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

parser.add_argument('--greq-branch', dest='greq_branch', default='master',
                    help='Global Requirements branch.')

parser.add_argument('--git-dir', dest='git_dir', default='/home/dim/Temp/glance',
                    help='Local GIT repository path.')

parser.add_argument('--fuel-release', dest='fuel_release', default='5.0.1',
                    help='Current FUEL release.')

args = parser.parse_args()

#===============================================================================

greq_branch = {
    'icehouse': 'stable/icehouse'
}.get(args.greq_branch, args.greq_branch)

greq_url="https://raw.githubusercontent.com/openstack/requirements/{0}/global-requirements.txt".format(greq_branch)

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
report.validation_report(validation_result=validation_result)

print("")

repo_set = PackageRepositorySet()
repo_set.add_custom_packages(custom_package_set=custom_python_packages)
repo_set.add(MirantisOSCIRepository(fuel_release=args.fuel_release))
repo_set.add(MirantisPublicRepository(fuel_release=args.fuel_release))
repo_set.add(UbuntuPublicRepository(fuel_release=args.fuel_release))

print("")
print("Searching packages for direct dependencies:")
print("===========================================")
for key in sorted(validation_result.keys()):
    item = validation_result[key]
    if item['is_direct_dependency']:
        print("")
        print("*** {0} ({1}):".format(item['orig_package'], item['greq_package']))
        for r, p, v in repo_set.grep_package(item['orig_package'].name):
            print("{0}: '{1} {2}'".format(r.name, p, v))

print("")
print("Searching packages for indirect dependencies:")
print("=============================================")
for key in sorted(validation_result.keys()):
    item = validation_result[key]
    if not item['is_direct_dependency']:
        print("")
        print("*** {0} ({1}):".format(item['orig_package'], item['greq_package']))
        for r, p, v in repo_set.grep_package(item['orig_package'].name):
            print("{0}: '{1} {2}'".format(r.name, p, v))

print("")

# Example of produced output:
# http://paste.openstack.org/show/85047/