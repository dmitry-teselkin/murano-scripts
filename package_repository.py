__author__ = 'dim'

from tempfile import mkdtemp
from sh import grep_dctrl
from sh import wget
from sh import awk
from sh import zcat
import os.path, time


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

    def grep_package(self, name, pattern="(^|-){0}$"):
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
            if name in self.custom_package_set:
                name = self.custom_package_set.deb_package_for(name)
            for p, v in repository.grep_package(name=name):
                yield repository, p, v

