import json
from multiprocessing import cpu_count
import os
import unittest
import yaml

import ycsettings


class TestYCSettings(unittest.TestCase):
    def setUp(self):
        settings_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.yaml')
        with open(settings_file) as f:
            self.settings = yaml.load(f)
    #end def

    def test_env_setings(self):
        for k, v in self.settings.items():
            if isinstance(v, list): os.environ[k] = ','.join(map(str, v))
            elif isinstance(v, dict): os.environ[k] = json.dumps(v)
            else: os.environ[k] = str(v)
        #end for

        self._assert_settings_object(search_first=['env'], string_list=True, string_dict_keys=True)

        for k in self.settings.keys():
            del os.environ[k]
    #end def

    def test_env_settings_uri(self):
        os.environ['SETTINGS_URI'] = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.yaml')
        self._assert_settings_object(search_first=['env_settings_uri'])
        del os.environ['SETTINGS_URI']
    #end def

    def test_settings_yaml(self):
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.yaml'), search_first=[])

    def test_settings_json(self):
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.json'), search_first=[], string_dict_keys=True)

    def test_settings_gz(self):
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.json.gz'), search_first=[], string_dict_keys=True)

    def test_settings_ini(self):
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.ini'), search_first=[], string_list=True)

    def test_settings_pkl(self):
        # import pickle
        # with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.pkl'), 'wb') as f:
        #     pickle.dump(self.settings, f)
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.pkl'), search_first=[])

    def test_settings_py(self):
        self._assert_settings_object(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets', 'settings.py'), search_first=[])

    def test_settings_module(self):
        self._assert_settings_object('tests.assets.settings', search_first=[])

    def test_settings_dict(self):
        self._assert_settings_object(self.settings, search_first=[])

    def test_settings_object(self):
        class ObjectLike(object):
            pass

        obj = ObjectLike()
        obj.__dict__.update(self.settings)
        self._assert_settings_object(obj, search_first=[])
    #end def

    def _assert_settings_object(self, *args, string_list=False, string_dict_keys=False, **kwargs):
        settings = ycsettings.Settings(*args, case_sensitive=False, raise_exception=False, **kwargs)
        self.assertEqual(settings.get('ycsettings_string'), 'string')
        self.assertEqual(settings.getint('ycsettings_int'), 1)
        self.assertEqual(settings.getfloat('ycsettings_float'), 1.5)
        self.assertEqual(settings.getbool('ycsettings_bool'), True)
        self.assertEqual(settings.getbool('ycsettings_false'), False)
        if string_list: self.assertEqual(settings.getlist('ycsettings_list'), ['1', '2', '3', 'a', 'b', 'c'])
        else: self.assertEqual(settings.getlist('ycsettings_list'), [1, 2, 3, 'a', 'b', 'c'])
        self.assertEqual(settings.getlist('ycsettings_csv'), ['apples', 'oranges', 'pears'])
        if string_dict_keys: self.assertEqual(settings.getdict('ycsettings_dict'), {'a': 1, 'b': 2, 'c': 3, '1': 'a', '2': 'b', '3': 'c'})
        else: self.assertEqual(settings.getdict('ycsettings_dict'), {'a': 1, 'b': 2, 'c': 3, 1: 'a', 2: 'b', 3: 'c'})
        self.assertEqual(settings.getnjobs('ycsettings_njobs'), 2 * cpu_count())

        self.assertEqual(settings.getint('YCSETTINGS_INT'), 1)
        self.assertEqual(settings.getfloat('YCSETTINGS_FLOAT'), 1.5)
        self.assertEqual(settings.getbool('YCSETTINGS_BOOL'), True)
        self.assertEqual(settings.getbool('YCSETTINGS_FALSE'), False)
        if string_list: self.assertEqual(settings.getlist('YCSETTINGS_LIST'), ['1', '2', '3', 'a', 'b', 'c'])
        else: self.assertEqual(settings.getlist('YCSETTINGS_LIST'), [1, 2, 3, 'a', 'b', 'c'])
        if string_dict_keys: self.assertEqual(settings.getdict('YCSETTINGS_DICT'), {'a': 1, 'b': 2, 'c': 3, '1': 'a', '2': 'b', '3': 'c'})
        else: self.assertEqual(settings.getdict('YCSETTINGS_DICT'), {'a': 1, 'b': 2, 'c': 3, 1: 'a', 2: 'b', 3: 'c'})
        self.assertEqual(settings.getnjobs('YCSETTINGS_NJOBS'), 2 * cpu_count())

        settings = ycsettings.Settings(*args, case_sensitive=True, warn_missing=True, **kwargs)
        with self.assertWarns(UserWarning):
            self.assertIsNone(settings.getint('YCSETTINGS_INT'))
            self.assertIsNone(settings.getfloat('YCSETTINGS_FLOAT'))
            self.assertIsNone(settings.getbool('YCSETTINGS_BOOL'))
            self.assertIsNone(settings.getbool('YCSETTINGS_FALSE'))
            self.assertIsNone(settings.getlist('YCSETTINGS_LIST'))
            self.assertIsNone(settings.getdict('YCSETTINGS_DICT'))
            self.assertIsNone(settings.getnjobs('YCSETTINGS_NJOBS'))
        #end with

        settings = ycsettings.Settings(*args, case_sensitive=True, raise_exception=True, **kwargs)
        with self.assertRaises(ycsettings.MissingSettingException):
            self.assertIsNone(settings.getint('YCSETTINGS_INT'))
            self.assertIsNone(settings.getfloat('YCSETTINGS_FLOAT'))
            self.assertIsNone(settings.getbool('YCSETTINGS_BOOL'))
            self.assertIsNone(settings.getbool('YCSETTINGS_FALSE'))
            self.assertIsNone(settings.getlist('YCSETTINGS_LIST'))
            self.assertIsNone(settings.getdict('YCSETTINGS_DICT'))
            self.assertIsNone(settings.getnjobs('YCSETTINGS_NJOBS'))
        #end with
    #end def
#end class
