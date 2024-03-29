from test.support import run_unittest, unload, check_warnings
import unittest
import sys
import importlib
from importlib.util import spec_from_file_location
import pkgutil
import os
import os.path
import tempfile
import types
import shutil
import zipfile

# Note: pkgutil.walk_packages is currently tested in test_runpy. This is
# a hack to get a major issue resolved for 3.3b2. Longer term, it should
# be moved back here, perhaps by factoring out the helper code for
# creating interesting package layouts to a separate module.
# Issue #15348 declares this is indeed a dodgy hack ;)

class PkgutilTests(unittest.TestCase):

    def setUp(self):
        self.dirname = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dirname)
        sys.path.insert(0, self.dirname)

    def tearDown(self):
        del sys.path[0]

    def test_getdata_filesys(self):
        pkg = 'test_getdata_filesys'

        # Include a LF and a CRLF, to test that binary data is read back
        RESOURCE_DATA = b'Hello, world!\nSecond line\r\nThird line'

        # Make a package with some resources
        package_dir = os.path.join(self.dirname, pkg)
        os.mkdir(package_dir)
        # Empty init.py
        f = open(os.path.join(package_dir, '__init__.py'), "wb")
        f.close()
        # Resource files, res.txt, sub/res.txt
        f = open(os.path.join(package_dir, 'res.txt'), "wb")
        f.write(RESOURCE_DATA)
        f.close()
        os.mkdir(os.path.join(package_dir, 'sub'))
        f = open(os.path.join(package_dir, 'sub', 'res.txt'), "wb")
        f.write(RESOURCE_DATA)
        f.close()

        # Check we can read the resources
        res1 = pkgutil.get_data(pkg, 'res.txt')
        self.assertEqual(res1, RESOURCE_DATA)
        res2 = pkgutil.get_data(pkg, 'sub/res.txt')
        self.assertEqual(res2, RESOURCE_DATA)

        del sys.modules[pkg]

    def test_getdata_zipfile(self):
        zip = 'test_getdata_zipfile.zip'
        pkg = 'test_getdata_zipfile'

        # Include a LF and a CRLF, to test that binary data is read back
        RESOURCE_DATA = b'Hello, world!\nSecond line\r\nThird line'

        # Make a package with some resources
        zip_file = os.path.join(self.dirname, zip)
        z = zipfile.ZipFile(zip_file, 'w')

        # Empty init.py
        z.writestr(pkg + '/__init__.py', "")
        # Resource files, res.txt, sub/res.txt
        z.writestr(pkg + '/res.txt', RESOURCE_DATA)
        z.writestr(pkg + '/sub/res.txt', RESOURCE_DATA)
        z.close()

        # Check we can read the resources
        sys.path.insert(0, zip_file)
        res1 = pkgutil.get_data(pkg, 'res.txt')
        self.assertEqual(res1, RESOURCE_DATA)
        res2 = pkgutil.get_data(pkg, 'sub/res.txt')
        self.assertEqual(res2, RESOURCE_DATA)

        names = []
        for loader, name, ispkg in pkgutil.iter_modules([zip_file]):
            names.append(name)
        self.assertEqual(names, ['test_getdata_zipfile'])

        del sys.path[0]

        del sys.modules[pkg]

    def test_unreadable_dir_on_syspath(self):
        # issue7367 - walk_packages failed if unreadable dir on sys.path
        package_name = "unreadable_package"
        d = os.path.join(self.dirname, package_name)
        # this does not appear to create an unreadable dir on Windows
        #   but the test should not fail anyway
        os.mkdir(d, 0)
        self.addCleanup(os.rmdir, d)
        for t in pkgutil.walk_packages(path=[self.dirname]):
            self.fail("unexpected package found")

class PkgutilPEP302Tests(unittest.TestCase):

    class MyTestLoader(object):
        def exec_module(self, mod):
            # Count how many times the module is reloaded
            mod.__dict__['loads'] = mod.__dict__.get('loads', 0) + 1

        def get_data(self, path):
            return "Hello, world!"

    class MyTestImporter(object):
        def find_spec(self, fullname, path=None, target=None):
            loader = PkgutilPEP302Tests.MyTestLoader()
            return spec_from_file_location(fullname,
                                           '<%s>' % loader.__class__.__name__,
                                           loader=loader,
                                           submodule_search_locations=[])

    def setUp(self):
        sys.meta_path.insert(0, self.MyTestImporter())

    def tearDown(self):
        del sys.meta_path[0]

    def test_getdata_pep302(self):
        # Use a dummy importer/loader
        self.assertEqual(pkgutil.get_data('foo', 'dummy'), "Hello, world!")
        del sys.modules['foo']

    def test_alreadyloaded(self):
        # Ensure that get_data works without reloading - the "loads" module
        # variable in the example loader should count how many times a reload
        # occurs.
        import foo
        self.assertEqual(foo.loads, 1)
        self.assertEqual(pkgutil.get_data('foo', 'dummy'), "Hello, world!")
        self.assertEqual(foo.loads, 1)
        del sys.modules['foo']


# These tests, especially the setup and cleanup, are hideous. They
# need to be cleaned up once issue 14715 is addressed.
class ExtendPathTests(unittest.TestCase):
    def create_init(self, pkgname):
        dirname = tempfile.mkdtemp()
        sys.path.insert(0, dirname)

        pkgdir = os.path.join(dirname, pkgname)
        os.mkdir(pkgdir)
        with open(os.path.join(pkgdir, '__init__.py'), 'w') as fl:
            fl.write('from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n')

        return dirname

    def create_submodule(self, dirname, pkgname, submodule_name, value):
        module_name = os.path.join(dirname, pkgname, submodule_name + '.py')
        with open(module_name, 'w') as fl:
            print('value={}'.format(value), file=fl)

    def test_simple(self):
        pkgname = 'foo'
        dirname_0 = self.create_init(pkgname)
        dirname_1 = self.create_init(pkgname)
        self.create_submodule(dirname_0, pkgname, 'bar', 0)
        self.create_submodule(dirname_1, pkgname, 'baz', 1)
        import foo.bar
        import foo.baz
        # Ensure we read the expected values
        self.assertEqual(foo.bar.value, 0)
        self.assertEqual(foo.baz.value, 1)

        # Ensure the path is set up correctly
        self.assertEqual(sorted(foo.__path__),
                         sorted([os.path.join(dirname_0, pkgname),
                                 os.path.join(dirname_1, pkgname)]))

        # Cleanup
        shutil.rmtree(dirname_0)
        shutil.rmtree(dirname_1)
        del sys.path[0]
        del sys.path[0]
        del sys.modules['foo']
        del sys.modules['foo.bar']
        del sys.modules['foo.baz']


    # Another awful testing hack to be cleaned up once the test_runpy
    # helpers are factored out to a common location
    def test_iter_importers(self):
        iter_importers = pkgutil.iter_importers
        get_importer = pkgutil.get_importer

        pkgname = 'spam'
        modname = 'eggs'
        dirname = self.create_init(pkgname)
        pathitem = os.path.join(dirname, pkgname)
        fullname = '{}.{}'.format(pkgname, modname)
        sys.modules.pop(fullname, None)
        sys.modules.pop(pkgname, None)
        try:
            self.create_submodule(dirname, pkgname, modname, 0)

            importlib.import_module(fullname)

            importers = list(iter_importers(fullname))
            expected_importer = get_importer(pathitem)
            for finder in importers:
                spec = pkgutil._get_spec(finder, fullname)
                loader = spec.loader
                try:
                    loader = loader.loader
                except AttributeError:
                    # For now we still allow raw loaders from
                    # find_module().
                    pass
                self.assertIsInstance(finder, importlib.machinery.FileFinder)
                self.assertEqual(finder, expected_importer)
                self.assertIsInstance(loader,
                                      importlib.machinery.SourceFileLoader)
                self.assertIsNone(pkgutil._get_spec(finder, pkgname))

            with self.assertRaises(ImportError):
                list(iter_importers('invalid.module'))

            with self.assertRaises(ImportError):
                list(iter_importers('.spam'))
        finally:
            shutil.rmtree(dirname)
            del sys.path[0]
            try:
                del sys.modules['spam']
                del sys.modules['spam.eggs']
            except KeyError:
                pass


    def test_mixed_namespace(self):
        pkgname = 'foo'
        dirname_0 = self.create_init(pkgname)
        dirname_1 = self.create_init(pkgname)
        self.create_submodule(dirname_0, pkgname, 'bar', 0)
        # Turn this into a PEP 420 namespace package
        os.unlink(os.path.join(dirname_0, pkgname, '__init__.py'))
        self.create_submodule(dirname_1, pkgname, 'baz', 1)
        import foo.bar
        import foo.baz
        # Ensure we read the expected values
        self.assertEqual(foo.bar.value, 0)
        self.assertEqual(foo.baz.value, 1)

        # Ensure the path is set up correctly
        self.assertEqual(sorted(foo.__path__),
                         sorted([os.path.join(dirname_0, pkgname),
                                 os.path.join(dirname_1, pkgname)]))

        # Cleanup
        shutil.rmtree(dirname_0)
        shutil.rmtree(dirname_1)
        del sys.path[0]
        del sys.path[0]
        del sys.modules['foo']
        del sys.modules['foo.bar']
        del sys.modules['foo.baz']

    # XXX: test .pkg files


class NestedNamespacePackageTest(unittest.TestCase):

    def setUp(self):
        self.basedir = tempfile.mkdtemp()
        self.old_path = sys.path[:]

    def tearDown(self):
        sys.path[:] = self.old_path
        shutil.rmtree(self.basedir)

    def create_module(self, name, contents):
        base, final = name.rsplit('.', 1)
        base_path = os.path.join(self.basedir, base.replace('.', os.path.sep))
        os.makedirs(base_path, exist_ok=True)
        with open(os.path.join(base_path, final + ".py"), 'w') as f:
            f.write(contents)

    def test_nested(self):
        pkgutil_boilerplate = (
            'import pkgutil; '
            '__path__ = pkgutil.extend_path(__path__, __name__)')
        self.create_module('a.pkg.__init__', pkgutil_boilerplate)
        self.create_module('b.pkg.__init__', pkgutil_boilerplate)
        self.create_module('a.pkg.subpkg.__init__', pkgutil_boilerplate)
        self.create_module('b.pkg.subpkg.__init__', pkgutil_boilerplate)
        self.create_module('a.pkg.subpkg.c', 'c = 1')
        self.create_module('b.pkg.subpkg.d', 'd = 2')
        sys.path.insert(0, os.path.join(self.basedir, 'a'))
        sys.path.insert(0, os.path.join(self.basedir, 'b'))
        import pkg
        self.addCleanup(unload, 'pkg')
        self.assertEqual(len(pkg.__path__), 2)
        import pkg.subpkg
        self.addCleanup(unload, 'pkg.subpkg')
        self.assertEqual(len(pkg.subpkg.__path__), 2)
        from pkg.subpkg.c import c
        from pkg.subpkg.d import d
        self.assertEqual(c, 1)
        self.assertEqual(d, 2)


class ImportlibMigrationTests(unittest.TestCase):
    # With full PEP 302 support in the standard import machinery, the
    # PEP 302 emulation in this module is in the process of being
    # deprecated in favour of importlib proper

    def check_deprecated(self):
        return check_warnings(
            ("This emulation is deprecated, use 'importlib' instead",
             DeprecationWarning))

    def test_importer_deprecated(self):
        with self.check_deprecated():
            x = pkgutil.ImpImporter("")

    def test_loader_deprecated(self):
        with self.check_deprecated():
            x = pkgutil.ImpLoader("", "", "", "")

    def test_get_loader_avoids_emulation(self):
        with check_warnings() as w:
            self.assertIsNotNone(pkgutil.get_loader("sys"))
            self.assertIsNotNone(pkgutil.get_loader("os"))
            self.assertIsNotNone(pkgutil.get_loader("test.support"))
            self.assertEqual(len(w.warnings), 0)

    def test_get_loader_handles_missing_loader_attribute(self):
        global __loader__
        this_loader = __loader__
        del __loader__
        try:
            with check_warnings() as w:
                self.assertIsNotNone(pkgutil.get_loader(__name__))
                self.assertEqual(len(w.warnings), 0)
        finally:
            __loader__ = this_loader


    def test_find_loader_avoids_emulation(self):
        with check_warnings() as w:
            self.assertIsNotNone(pkgutil.find_loader("sys"))
            self.assertIsNotNone(pkgutil.find_loader("os"))
            self.assertIsNotNone(pkgutil.find_loader("test.support"))
            self.assertEqual(len(w.warnings), 0)

    def test_get_importer_avoids_emulation(self):
        # We use an illegal path so *none* of the path hooks should fire
        with check_warnings() as w:
            self.assertIsNone(pkgutil.get_importer("*??"))
            self.assertEqual(len(w.warnings), 0)

    def test_iter_importers_avoids_emulation(self):
        with check_warnings() as w:
            for importer in pkgutil.iter_importers(): pass
            self.assertEqual(len(w.warnings), 0)


def test_main():
    run_unittest(PkgutilTests, PkgutilPEP302Tests, ExtendPathTests,
                 NestedNamespacePackageTest, ImportlibMigrationTests)


if __name__ == '__main__':
    test_main()
