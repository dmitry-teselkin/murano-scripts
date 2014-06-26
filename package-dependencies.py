__author__ = 'dim'

import urllib2
import re
import os
from pushd import pushd
from getpass import getuser


from sh import python
from sh import tail
from sh import pip
from sh import rm


class PipPackage():
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
                package = PipPackage(string)
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
            req_entry = PipPackage(line)
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

class PipPackageRequirements():
    def __init__(self):
        self._pip_install_opts = ['--no-install', '--verbose']
        self.package_name = ""
        self.entries = []
        pass

    def _add_pip_package(self, string, from_package=None):
        package = PipPackage(string, from_package=from_package)
        if package.looks_good:
            self.entries.append(package)

    def install_from_dir(self, path):
        self._pip_install_opts.append('-e')
        if not os.path.exists(path):
            raise Exception("Path not found '{0}'".format(path))

        rm('-r', '-f', "/tmp/pip_build_{0}".format(getuser()))

        with pushd(path):
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

    def install_from_stackforge(self, url):
        pass

    def install_from_git(self, url):
        pass

    def validate(self, global_requirements):
        result = []
        for package in self.entries:
            status, greq_package = global_requirements.validate(package)
            result.append(
                {
                    'orig_package': package,
                    'greq_package': greq_package,
                    'status': status,
                    'is_direct_dependency': self.package_name == package.parents[0].name
                }
            )
        return result

    def print_report_block(self, validation_result, compatible=False, direct=False):
        str_direct = 'direct' if direct else 'indirect'
        str_compatible = 'compatible' if compatible else 'incompatible'
        str_header = "{0} dependencies {1} with global requirements:".format(
            str_direct.capitalize(), str_compatible
        )

        print("")
        print(str_header)
        print("=" * len(str_header))
        count = 0
        for result in validation_result:
            if result['status'] == compatible and result['is_direct_dependency'] == direct:
                count += 1
                if result['greq_package']:
                    greq_status = "Global Requirements: {0}".format(result['greq_package'])
                else:
                    greq_status = "Not found in Global Requirements"

                if direct:
                    str_parents = "  "
                else:
                    str_parents = "(From: {0})".format(
                        " -> ".join([str(p) for p in result['orig_package'].parents])
                    )

                print("{0} {1} # {2}".format(result['orig_package'], str_parents, greq_status))

        print("=" * len(str_header))
        print("Total: {0}".format(count))

    def print_report(self, validation_result):
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

greq_branch='stable/icehouse'
greq_url="https://raw.githubusercontent.com/openstack/requirements/{0}/global-requirements.txt".format(greq_branch)
print(greq_url)

greq = GlobalRequirements(greq_url)

pip_dry_run = PipPackageRequirements()
pip_dry_run.install_from_dir('/home/dim/Temp/glance')

validation_result = pip_dry_run.validate(greq)
pip_dry_run.print_report(validation_result=validation_result)
