__author__ = 'dim'


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


custom_python_packages = CustomPackageSet()

custom_python_packages.add(PackageAlias(name='SQLAlchemy').deb(name='python-sqlalchemy'))
custom_python_packages.add(PackageAlias(name='PasteDeploy').deb(name='python-paste-deploy'))
custom_python_packages.add(PackageAlias(name='Routes').deb(name='python-routes'))
custom_python_packages.add(PackageAlias(name='sqlalchemy-migrate').deb(name='python-migrate'))
custom_python_packages.add(PackageAlias(name='pycrypto').deb(name='python-crypto'))
custom_python_packages.add(PackageAlias(name='Paste').deb(name='python-paste'))
custom_python_packages.add(PackageAlias(name='pyOpenSSL').deb(name='python-pyopenssl'))
custom_python_packages.add(PackageAlias(name='repoze.lru').deb(name='python-repoze-lru'))
custom_python_packages.add(PackageAlias(name='Tempita').deb(name='python-tempita'))
custom_python_packages.add(PackageAlias(name='Babel').deb(name='python-babel'))
custom_python_packages.add(PackageAlias(name='PyYAML').deb(name='python-yaml'))
custom_python_packages.add(PackageAlias(name='PrettyTable').deb(name='python-prettytable'))
custom_python_packages.add(PackageAlias(name='pytz').deb(name='python-pytz'))

