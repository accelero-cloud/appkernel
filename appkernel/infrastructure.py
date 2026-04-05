from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from .core import AppInitialisationError


class CfgEngine:
    """
    Encapsulates application configuration. One can use it for retrieving
    various sections from the configuration.
    """

    def __init__(
        self,
        cfg_dir: str | None,
        config_file_name: str = 'cfg.yml',
        optional: bool = False,
    ) -> None:
        """
        :param cfg_dir: the directory which holds the configuration files;
        :param config_file_name: the file name which contains the configuration
                                 (cfg.yml by default);
        :param optional: if True it will initialise even if config resource is
                         not found (defaults to False);
        """
        self.optional = optional
        self.initialised = False
        config_file: str | None

        if cfg_dir:
            config_file = f'{cfg_dir.rstrip("/")}/{config_file_name}'
        else:
            cwd = Path(sys.argv[0]).resolve().parent
            current = cwd / config_file_name
            if current.exists() and current.is_file():
                config_file = str(current)
            else:
                parent_candidate = cwd.parent / config_file_name
                config_file = str(parent_candidate) if parent_candidate.exists() and parent_candidate.is_file() else None

        if not config_file or not os.access(config_file, os.R_OK):
            if not optional:
                raise AppInitialisationError(
                    f'The config file {config_file} is missing or not readable. '
                )
            else:
                return

        with open(config_file, 'r') as ymlfile:
            try:
                self.cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
                self.initialised = True
            except yaml.scanner.ScannerError as se:
                raise AppInitialisationError(
                    f'cannot read config file {config_file} due to: {se!s}'
                )

    def get(self, path_expression: str, default_value: Any = None) -> Any:
        """
        :param path_expression: a . (dot) separated path to the configuration
                                value: 'appkernel.backup_count'
        :param default_value: the value to be returned in case the required
                              parameter is not found
        :return: the configuration value or default_value
        """
        assert path_expression is not None, 'Path expression should be provided.'
        nodes = path_expression.split('.')
        return self.get_value_for_path_list(nodes, default_value=default_value)

    def get_value_for_path_list(
        self,
        config_nodes: list[str],
        section_dict: dict | None = None,
        default_value: Any = None,
    ) -> Any:
        """
        :return: a section (or value) under the given array keys
        """
        if not self.initialised:
            return default_value
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
