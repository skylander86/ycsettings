ycsettings
==========

.. image:: https://img.shields.io/pypi/v/ycsettings.svg
        :target: https://pypi.python.org/pypi/ycsettings
.. image:: https://readthedocs.org/projects/ycsettings/badge/?version=latest
        :target: http://ycsettings.readthedocs.io/en/latest/?badge=latest

ycsettings is a utility module for handling app settings.
It simplifies the searching of multiple sources (i.e., environment, files, etc) for settings and configuration variables.

Example
-------

.. code-block:: python

    parser = ArgumentParser(description='Hello World!')
    parser.add_argument('settings_uri', type=str, metavar='<config_file>', help='Positional option')
    A = parser.parse_args()

    settings_dict = {'A': 5}

    settings = Settings(A, settings_dict, 's3://example/settings.yaml', search_first=['env', 'env_settings_uri'], warn_missing=False)

    print(settings.getint('A', default=5, raise_exception=True))
