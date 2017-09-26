__all__ = ['Settings', 'parse_n_jobs', 'MissingSettingException']


from collections import OrderedDict, Mapping
import configparser
import importlib
from io import TextIOWrapper
import json
import logging
from multiprocessing import cpu_count
import os
import pickle
import re
from tempfile import NamedTemporaryFile
from urllib.parse import ParseResult, urlparse
import warnings

from uriutils import uri_open

try: import yaml
except ImportError: pass


logger = logging.getLogger(__name__)


class Settings(Mapping):
    """
    This class manages the lookup and prioritizing of setting variables in multiple different sources.
    Supported sources include:

    * Environment (``env``): The OS environment, i.e., :attr:`os.environ`
    * URI/files: Handles different file types including: JSON, YAML, and INI
    * Python modules: Python modules similar to Django settings module; it can be a ``.py`` file or module path
    * Dictionary-like objects: Objects with the ``items`` attribute
    * Arbitrary objects: All ``__dict__`` entries not starting with ``__`` are used as settings

    If ``settings_uri`` is found in the environment (``SETTINGS_URI``), dictionary, or arbitrary object, it will also load the corresponding settings URI in addition to the object itself.
    This way, it can autoload from ``SETTINGS_URI`` in the environment and :class:`argparse.Namespace`.
    For example,

    .. code-block:: python

        parser = ArgumentParser(description='Hello World!')
        parser.add_argument('settings_uri', type=str, metavar='<config_file>', help='Positional option')
        A = parser.parse_args()

        settings = Settings(A, warn_missing=False)

    The file specified in ``A.settings_uri`` will be loaded.
    """

    def __init__(self, *sources, search_first=['env', 'env_settings_uri'], case_sensitive=False, raise_exception=False, warn_missing=True, env_settings_uri_key='SETTINGS_URI', dict_settings_uri_key='settings_uri', object_settings_uri_key='settings_uri'):
        """
        Initializes the :class:`Settings` object.

        :param list sources: list of sources to search for settings
        :param list search_first: list of sources which will be searched first before any other sources specified in ``sources``.
        :param bool case_sensitive: whether to make case sensitive comparisons for settings key
        :param bool raise_exception: whether to raise a :exc:`MissingSettingException` exception when the setting is not found
        :param bool warn_missing: whether to display a warning when the setting is not found

        :param str env_settings_uri_key: key to find settings URI in the environment
        :param str dict_settings_uri_key: key to find settings URI in a :func:`dict`-like object
        :param str object_settings_uri_key: key to find settings URI in an arbitrary object
        """

        self.case_sensitive = case_sensitive
        self.raise_exception = raise_exception
        self.warn_missing = warn_missing

        self.env_settings_uri_key = env_settings_uri_key
        self.dict_settings_uri_key = dict_settings_uri_key
        self.object_settings_uri_key = object_settings_uri_key

        self._cache = {}
        self._settings = OrderedDict()
        self._union_keys = None

        self.sources = search_first + list(sources)
        for source in self.sources:
            for name, settings in self._load_settings_from_source(source):
                if not settings: continue

                if name in self._settings:
                    warnings.warn('{} appeared more than once in the settings priority list.'.format(name))

                self._settings[name] = settings
            #end for
        #end for
    #end def

    def _load_settings_from_source(self, source):
        """
        Loads the relevant settings from the specified ``source``.

        :returns: a standard :func:`dict` containing the settings from the source
        :rtype: dict
        """

        if source == 'env_settings_uri':
            env_settings_uri = self._search_environ(self.env_settings_uri_key)
            if env_settings_uri:
                logger.debug('Found {} in the environment.'.format(self.env_settings_uri_key))
                yield env_settings_uri, self._load_settings_from_uri(env_settings_uri)
            else:
                yield env_settings_uri, None

        elif source == 'env':
            logger.debug('Loaded {} settings from the environment.'.format(len(os.environ)))
            yield source, dict(os.environ.items())

        elif isinstance(source, ParseResult):
            settings = self._load_settings_from_uri(source)
            yield source, settings

        elif isinstance(source, str):
            try: spec = importlib.util.find_spec(source)
            except (AttributeError, ModuleNotFoundError): spec = None

            settings = self._load_settings_from_spec(spec, name=source)
            if settings is None:
                _, ext = os.path.splitext(source)
                with uri_open(source, 'rb') as f:
                    yield source, self._load_settings_from_file(f, ext=ext)
            else:
                yield source, settings
            #end if

        elif hasattr(source, 'items'):
            source_type = type(source).__name__
            if self.dict_settings_uri_key and self.dict_settings_uri_key in source:
                logger.debug('Found {} in the dict-like object <{}>.'.format(self.dict_settings_uri_key, source_type))
                yield from self._load_settings_from_source(source[self.dict_settings_uri_key])
            #end if

            logger.debug('Loaded {} settings from dict-like object <{}>.'.format(len(source), source_type))
            yield self._get_unique_name(source_type), source

        else:
            source_type = type(source).__name__
            if self.object_settings_uri_key and hasattr(source, self.object_settings_uri_key):
                logger.debug('Found {} in the object <{}>.'.format(self.object_settings_uri_key, source_type))
                yield from self._load_settings_from_source(getattr(source, self.object_settings_uri_key))
            #end if

            settings = dict((k, v) for k, v in source.__dict__.items() if not k.startswith('__'))
            logger.debug('Loaded {} settings from object <{}>.'.format(len(settings), source_type))
            yield self._get_unique_name(source_type), settings
        #end if
    #end def

    def _get_unique_name(self, prefix):
        i = 0
        name = '{}_{}'.format(prefix, i)
        while name in self._settings:
            i += 1
            name = '{}_{}'.format(prefix, i)
        #end while
        return name
    #end def

    def _load_settings_from_spec(self, spec, name=None):
        if spec is None: return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        settings = dict((k, v) for k, v in mod.__dict__.items() if not k.startswith('__'))
        if name: logger.debug('Loaded {} settings from Python module <{}>.'.format(len(settings), name))

        return settings
    #end def

    def _load_settings_from_uri(self, uri):
        _, ext = os.path.splitext(uri)
        with uri_open(uri) as f:
            settings = self._load_settings_from_file(f, ext=ext)

        logger.debug('Loaded {} settings from URI <{}>.'.format(len(settings), uri))
        return settings
    #end def

    def _load_settings_from_file(self, f, ext=None):
        if ext is None or ext == '.gz':
            name = f.name[:-3] if f.name.endswith('.gz') else f.name
            basename, ext = os.path.splitext(name)
        #end if
        ext = ext.lower()
        ext_type = ext[1:].upper()

        if ext in ('.json', '.js'): d = json.load(f)
        elif ext == '.yaml': d = yaml.load(f)
        elif ext in ('.pkl', '.pickle'): d = pickle.load(f)
        elif ext in ['.ini']:
            config = configparser.ConfigParser()
            config.read_file(TextIOWrapper(f))
            d = dict((name, value) for section in config.sections() for name, value in config.items(section))

        elif ext in ['.py']:
            temp_fname = None
            ext_type = 'Python module'
            try:
                with NamedTemporaryFile(mode='wb', suffix='.py', delete=False) as g:
                    g.write(f.read())
                    temp_fname = g.name
                #end with

                d = self._load_settings_from_spec(importlib.util.spec_from_file_location('settings_module', os.path.abspath(temp_fname)))

            finally:
                os.remove(temp_fname)

        else: raise ValueError('Unknown settings file format: {}'.format(ext))

        logger.debug('Loaded {} {} settings from <{}>.'.format(len(d), ext_type, f.name))

        return d
    #end def

    def get(self, key, *, default=None, cast_func=None, case_sensitive=None, raise_exception=None, warn_missing=None):
        """
        Gets the setting specified by ``key``. For efficiency, we cache the retrieval of settings to avoid multiple searches through the sources list.

        :param str key: settings key to retrieve
        :param str default: use this as default value when the setting key is not found
        :param func cast_func: cast the value of the settings using this function
        :param bool case_sensitive: whether to make case sensitive comparisons for settings key
        :param bool raise_exception: whether to raise a :exc:`MissingSettingException` exception when the setting is not found
        :param bool warn_missing: whether to display a warning when the setting is not found

        :returns: the setting value
        :rtype: str
        """

        case_sensitive = self.case_sensitive if case_sensitive is None else case_sensitive
        raise_exception = self.raise_exception if raise_exception is None else raise_exception
        warn_missing = self.warn_missing if warn_missing is None else warn_missing

        if not case_sensitive: key = key.lower()

        if key in self._cache:
            return cast_func(self._cache[key]) if cast_func else self._cache[key]

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
            if raise_exception: raise MissingSettingException('The "{}" setting is missing.'.format(key))
            if warn_missing: warnings.warn('The "{}" setting is missing.'.format(key))

            return default
        #end if

        self._cache[key] = value
        if cast_func: value = cast_func(value)

        return value
    #end def

    def getbool(self, key, **kwargs):
        """
        Gets the setting value as a :func:`bool` by cleverly recognizing true values.

        :rtype: bool
        """

        def _string_to_bool(s):
            if isinstance(s, str):
                if s.strip().lower() in ('true', 't', '1'): return True
                elif s.strip().lower() in ('false', 'f', '0', 'None', 'null', ''): return False

                raise ValueError('Unable to get boolean value of "{}".'.format(s))
            #end if

            return bool(s)
        #end def

        return self.get(key, cast_func=_string_to_bool, **kwargs)
    #end def

    def getint(self, key, **kwargs):
        """
        Gets the setting value as a :obj:`int`.

        :rtype: int
        """

        return self.get(key, cast_func=int, **kwargs)
    #end def

    def getfloat(self, key, **kwargs):
        """
        Gets the setting value as a :obj:`float`.

        :rtype: float
        """

        return self.get(key, cast_func=float, **kwargs)
    #end def

    def getdict(self, key, **kwargs):
        """
        Gets the setting value as a :obj:`dict`.

        :rtype: dict
        """

        return self.getserialized(key, **kwargs)
    #end def

    def getserialized(self, key, decoder_func=None, **kwargs):
        """
        Gets the setting value as a :obj:`dict` or :obj:`list` trying :meth:`json.loads`, followed by :meth:`yaml.load`.

        :rtype: dict, list
        """

        value = self.get(key, cast_func=None, **kwargs)

        if isinstance(value, (dict, list, tuple)) or value is None:
            return value

        if decoder_func: return decoder_func(value)

        try:
            o = json.loads(value)
            return o
        except json.decoder.JSONDecodeError: pass

        try:
            o = yaml.load(value)
            return o
        except yaml.parser.ParserError: pass

        raise ValueError('Unable to parse {} setting using JSON or YAML.'.format(key))
    #end def

    def geturi(self, key, **kwargs):
        """
        Gets the setting value as a :class:`urllib.parse.ParseResult`.

        :rtype: urllib.parse.ParseResult
        """

        return self.get(key, cast_func=urlparse, **kwargs)
    #end def

    def getlist(self, key, delimiter=',', **kwargs):
        """
        Gets the setting value as a :func:`list`; it splits the string using ``delimiter``.

        :param str delimiter: split the value using this delimiter
        :rtype: list
        """

        value = self.get(key, **kwargs)
        if value is None: return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith('[') and value.endswith(']'):
                return self.getserialized(key)

            return [p.strip(' ') for p in value.split(delimiter)]
        #end if

        return list(value)
    #end def

    def getnjobs(self, key, **kwargs):
        """
        Gets the setting value as an integer relative to the number of CPU.
        See :func:`parse_n_jobs` for parsing rules.

        :rtype: int
        """

        return self.get(key, cast_func=parse_n_jobs, **kwargs)
    #end def

    def _search_environ(self, key, default=None):
        key = key.lower()
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


class MissingSettingException(Exception):
    pass


def parse_n_jobs(s):
    """
    This function parses a "math"-like string as a function of CPU count.
    It is useful for specifying the number of jobs.

    For example, on an 8-core machine::

    .. code-block:: python

        assert parse_n_jobs('0.5 * n') == 4
        assert parse_n_jobs('2n') == 16
        assert parse_n_jobs('n') == 8
        assert parse_n_jobs('4') == 4

    :param str s: string to parse for number of CPUs
    """

    n_jobs = None
    N = cpu_count()

    if isinstance(s, int): n_jobs = s

    elif isinstance(s, float): n_jobs = int(s)

    elif isinstance(s, str):
        m = re.match(r'(\d*(?:\.\d*)?)?(\s*\*?\s*n)?$', s.strip())
        if m is None: raise ValueError('Unable to parse n_jobs="{}"'.format(s))

        k = float(m.group(1)) if m.group(1) else 1
        if m.group(2): n_jobs = k * N
        elif k < 1: n_jobs = k * N
        else: n_jobs = int(k)

    else: raise TypeError('n_jobs argument must be of type str, int, or float.')

    n_jobs = int(n_jobs)
    if n_jobs <= 0:
        warnings.warn('n_jobs={} is invalid. Setting n_jobs=1.'.format(n_jobs))
        n_jobs = 1
    #end if

    return int(n_jobs)
#end def
