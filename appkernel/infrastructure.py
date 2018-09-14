import os
import sys

import yaml

from .core import AppInitialisationError


class CfgEngine(object):
    """
    Encapsulates application configuration. One can use it for retrieving various section form the configuration.
    """

    def __init__(self, cfg_dir, config_file_name='cfg.yml', optional=False):
        """
        :param cfg_dir: the directory which holds the configuration files;
        :param config_file_name: the file name which contains the configuration (cfg.yml by default);
        :param optional: if True it will initialise even if config resource is not found (defaults to False);
        """
        self.optional = optional
        self.initialised = False
        if cfg_dir:
            config_file = f'{cfg_dir.rstrip("/")}/{config_file_name}'
        else:
            cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
            current = os.path.expanduser(f'/{cwd.lstrip("/")}/{config_file_name}')
            if os.path.exists(current) and os.path.isfile(current):
                config_file = str(current)
            else:
                current = os.path.expanduser(f'/{cwd.lstrip("/")}/../{config_file_name}')
                config_file = str(current) if os.path.exists(current) and os.path.isfile(current) else None
        if not config_file or not os.access(config_file, os.R_OK):
            if not optional:
                raise AppInitialisationError(f'The config file {config_file} is missing or not readable. ')
            else:
                return

        with open(config_file, 'r') as ymlfile:
            try:
                self.cfg = yaml.load(ymlfile)
                self.initialised = True
            except yaml.scanner.ScannerError as se:
                raise AppInitialisationError('cannot read configuration file due to: {}'.format(config_file))

    def get(self, path_expression, default_value=None):
        """
        :param default_value: the value to be returned in case the required parameter is not found
        :param path_expression: a . (dot) separated path to the configuration value: 'appkernel.backup_count'
        :type path_expression: str
        :return:
        """
        assert path_expression is not None, 'Path expression should be provided.'

        nodes = path_expression.split('.')
        return self.get_value_for_path_list(nodes, default_value=default_value)

    def get_value_for_path_list(self, config_nodes, section_dict=None, default_value=None):
        """
        :return: a section (or value) under the given array keys
        """
        if not self.initialised:
            default_value
        assert isinstance(config_nodes, list), 'config_nodes should be a string list'
        if section_dict is None:
            section_dict = self.cfg if hasattr(self, 'cfg') else None
        if len(config_nodes) == 0:
            return default_value
        elif len(config_nodes) == 1:
            # final element
            return section_dict.get(config_nodes[0], default_value)
        elif section_dict:
            key = config_nodes.pop(0)
            return self.get_value_for_path_list(config_nodes, section_dict.get(key), default_value=default_value)
        else:
            return default_value
