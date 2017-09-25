__all__ = ['Settings']

from collections import OrderedDict, Mapping
import configparser
import importlib
import json
import logging
import os
import pickle
from tempfile import NamedTemporaryFile
from urllib.parse import ParseResult
import warnings

from uriutils import uri_open

try: import yaml
except ImportError: pass


logger = logging.getLogger(__name__)


class Settings(Mapping):
    """
    This class holds all the settings variables for a single environment.
    """

    def __init__(self, priority=['env', 'env_settings_uri'], case_sensitive=False, raise_exception=False, warn_missing=True, additional_priority=[], title=None):
        """
        :param list priority: Sets the priority list of resolving setting entries; sources earlier in the list has higher priority.
        """

        self.case_sensitive = case_sensitive
        self.raise_exception = raise_exception
        self.warn_missing = warn_missing
        self.title = title

        self._cache = {}
        self._settings = OrderedDict()
        self._union_keys = None

        self.priority = priority + additional_priority
        for source in priority:
            name, settings = self._load_settings_from_source(source)
            if settings:
                if name in self._settings:
                    warnings.warn('{} appeared more than once in the settings priority list.'.format(name))

                self._settings[name] = settings
            #end if
        #end for
    #end def

    def _load_settings_from_source(self, source):
        if source == 'env_settings_uri':
            env_settings_uri = self._search_environ('settings_uri')
            if env_settings_uri:
                return source, self._load_settings_from_uri(env_settings_uri)
            else:
                return source, {}

        elif source == 'env':
            return source, os.environ

        elif isinstance(source, ParseResult):
            return source, self._load_settings_from_uri(source)

        elif isinstance(source, str):
            spec = importlib.util.find_spec(source)
            if spec is None:
                return source, self._load_settings_from_uri(source)

            mod = importlib.util.module_from_spec(spec)
            return source, dict((k, v) for k, v in mod.__dict__ if not k.startswith('__'))

        elif hasattr(source, 'items'):
            i = 0
            source_type = type(source).__name__
            name = '{}_{}'.format(source_type, i)
            while name not in self._settings:
                i += 1
                name = '{}_{}'.format(source_type, i)
            #end while
            return name, source

        else:
            i = 0
            source_type = type(source).__name__
            name = '{}_{}'.format(source_type, i)
            while name not in self._settings:
                i += 1
                name = '{}_{}'.format(source_type, i)
            #end while

            return name, dict((k, v) for k, v in source.__dict__ if not k.startswith('__'))
        #end if

        raise Exception('{} is an unknown source type.'.format(type(source).__name__))
    #end def

    def _load_settings_from_uri(self, settings_uri):
        _, ext = os.path.splitext(settings_uri)
        with uri_open(settings_uri, 'rb') as f:
            return self._load_settings_from_file(f, ext=ext)
    #end def

    def _load_settings_from_file(self, f, ext=None):
        if ext is None:
            _, ext = os.path.spiltext(f.name)
        ext = ext.lower()

        if ext == '.json': d = json.load(f)
        elif ext == '.yaml': d = yaml.load(f)
        elif ext in ('.pkl', '.pickle'): d = pickle.load(f)
        elif ext in ['.ini']:
            config = configparser.ConfigParser()
            config.read_file(f)
            d = {}
            for section in config.sections():
                d[section] = {}
                for name, value in config.items(section):
                    d[section][name] = value
            #end for

        elif ext in ['.py']:
            fname = None
            try:
                with NamedTemporaryFile(mode='wb', delete=False) as g:
                    g.write(f.read())
                    fname = g.name
                #end with

                spec = importlib.util.spec_from_file_location('settings_module', fname)
                mod = importlib.util.module_from_spec(spec)

                return dict((k, v) for k, v in mod.__dict__ if not k.startswith('__'))

            finally:
                os.remove(fname)

            # name = "package." + name
            # mod = __import__(name, fromlist=[''])
            # mod.doSomething()

        else: raise ValueError('Unknown settings file format: {}'.format(ext))

        logger.info('Loaded {} settings from <{}>.'.format(self.title if self.title else ext[1:].upper(), f.name))

        return d
    #end def

    def get(self, key, default=None, case_sensitive=None, raise_exception=None, warn_missing=None):
        case_sensitive = self.case_sensitive if case_sensitive is None else case_sensitive
        raise_exception = self.raise_exception if raise_exception is None else raise_exception
        warn_missing = self.warn_missing if warn_missing is None else warn_missing

        if not case_sensitive: key = key.lower()

        if key in self._cache:
            return self._cache[key]

        found, value = False, None

        for source, settings in self._settings.items():
            if case_sensitive:
                if key in settings:
                    found = True
                    value = settings[key]
                else: continue

            else:
                possible_keys = [k for k in settings.keys() if k.lower() == key]
                if not possible_keys: continue
                else:
                    if len(possible_keys) > 1:
                        warnings.warn('There are more than one possible value for "{}" in <{}> settings due to case insensitivity.'.format(key, source))

                    found = True
                    value = settings[possible_keys[0]]
                #end if
            #end if

            if found: break
        #end for

        if not found:
            if raise_exception: raise MissingSetting('The "{}" setting is missing.'.format(key))
            if warn_missing: warnings.warn('The "{}" setting is missing.'.format(key))

            return default
        #end if

        self._cache[key] = value

        return value
    #end def

    def _search_environ(self, key, default=None):
        for k, v in os.environ.items():
            if k.lower() == key:
                return v

        return default
    #end def

    def __getitem__(self, key):
        return self.get(key)

    def __iter__(self):
        if self._union_keys is None:
            keys = set()
            self._union_keys = []
            for source, settings in self._settings.items():
                for k, v in settings.items():
                    k = k if self.case_sensitive else k.lower()
                    if k in keys: continue

                    keys.add(k)
                    self._union_keys.append(k)
                    yield k
                #end for
            #end for
        else:
            yield from self._union_keys
        #end if
    #end def

    def __len__(self):
        if self._union_keys is None:
            [k for k in self.__iter__()]  # just to run through the whole thing and build _union_keys

        return len(self._union_keys)
    #end def
#end class


class MissingSetting(Exception):
    pass


def main():
    settings = Settings(additional_priority=[])

    print(settings.get('n_jobs'))
#end def


if __name__ == '__main__': main()
