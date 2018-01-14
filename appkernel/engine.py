#!/usr/bin/python
from flask import Flask
import logging
import sys, os, yaml, re
import getopt
from logging.handlers import RotatingFileHandler


class AppKernelEngine(object):

    def __init__(self,
                 app_id,
                 app=None,
                 root_url='/',
                 log_level=logging.DEBUG):
        """
        Initialising the rest engine with Flask Engine.
        :param app: the Flask App
        :type app: Flask
        :param root_url: the url where the service are exposed to.
        :type root_url: str
        :param log_level: the level of log
        :type log_level: logging
        """
        assert app_id is not None, 'The app_id must be provided'
        assert re.match('[A-Za-z0-9-_]',
                        app_id), 'The app_id must be a single word, no space or special characters except - or _ .'
        assert app is not None, 'The Flask App must be provided as init parameter.'
        try:
            self.app = app
            self.app_id = app_id
            self.root_url = root_url
            self.init_flask_app()
            self.cmd_line_options = self.get_cmdline_options()
            self.cfg_engine = CfgEngine(self.cmd_line_options.get('cfg_dir'))
            self.development = self.cmd_line_options.get('development')
            cwd = self.cmd_line_options.get('cwd')
            self.init_logger(log_folder=cwd, level=log_level)
        except (AppInitialisationError, AssertionError) as init_err:
            # print >> sys.stderr,
            self.app.logger.error(init_err.message)
            sys.exit(-1)

    def run(self):
        self.app.logger.info('===== Starting {} ====='.format(self.app_id))
        self.app.run(debug=self.development)

    def get_cmdline_options(self):
        argv = sys.argv[1:]
        opts, args = getopt.getopt(argv, 'c:dw:', ['config-dir=', 'development', 'working-dir='])
        # -- config directory
        config_dir_provided, config_dir_param = AppKernelEngine.is_option_provided(('-c', '--config-dir'), opts, args)
        cwd = os.path.dirname(os.path.realpath(sys.argv[0]))
        if config_dir_provided:
            cfg_dir = '{}/'.format(str(config_dir_param).rstrip('/'))
            cfg_dir = os.path.expanduser(cfg_dir)
            if not os.path.isdir(cfg_dir) or not os.access(cfg_dir, os.W_OK):
                raise AppInitialisationError('The config directory [{}] is not found/not writable.'.format(cfg_dir))
        else:
            cfg_dir = '{}/../'.format(cwd.rstrip('/'))

        # -- working directory
        working_dir_provided, working_dir_param = AppKernelEngine.is_option_provided(('-w', '--working-dir'), opts,
                                                                                     args)
        if working_dir_provided:
            cwd = os.path.expanduser('{}/'.format(str(config_dir_param).rstrip('/')))
            if not os.path.isdir(cwd) or not os.access(cwd, os.W_OK):
                raise AppInitialisationError('The working directory[{}] is not found/not writable.'.format(cwd))
        else:
            cwd = '{}/../'.format(cwd.rstrip('/'))
        development, param = AppKernelEngine.is_option_provided(('-d', '--development'), opts, args)
        return {
            'cfg_dir': cfg_dir,
            'development': development,
            'cwd': cwd
        }

    @staticmethod
    def is_option_provided(option_dict, opts, args):
        for opt, arg in opts:
            if opt in option_dict:
                return True, arg
        return False, ''

    def init_flask_app(self):
        # app.config.setdefault('SQLITE3_DATABASE', ':memory:')
        # Use the newstyle teardown_appcontext if it's available,
        # otherwise fall back to the request context
        if hasattr(self.app, 'teardown_appcontext'):
            self.app.teardown_appcontext(self.teardown)
        else:
            self.app.teardown_request(self.teardown)

    def init_web_layer(self):
        # app.error_handler_spec[None][404] = self.resource_not_found()
        self.app.register_error_handler(404, self.resource_not_found)
        self.app.register_error_handler(Exception, self.generic_error_handler)

    def init_logger(self, log_folder, level=logging.DEBUG):
        assert log_folder is not None, 'The log folder must be provided.'
        if self.development:
            formatter = logging.Formatter("%(levelname)s - %(message)s")
            handler = logging.StreamHandler()
            handler.setLevel(level)
            self._enable_werkzeug_logger(handler)
        else:
            # self.cfg_engine.get_value_for_section()
            # log_format = ' in %(module)s [%(pathname)s:%(lineno)d]:\n%(message)s'
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s")
            max_bytes = self.cfg_engine.get('appkernel.logging.max_size') or 10485760
            backup_count = self.cfg_engine.get('appkernel.logging.backup_count') or 3
            file_name = self.cfg_engine.get('appkernel.logging.file_name') or '{}.log'.format(self.app_id)
            handler = RotatingFileHandler('{}/{}.log'.format(log_folder, file_name), maxBytes=max_bytes, backupCount=backup_count)
            # handler = TimedRotatingFileHandler('logs/foo.log', when='midnight', interval=1)
            handler.setLevel(level)
        handler.setFormatter(formatter)
        self.app.logger.setLevel(level)
        self.app.logger.addHandler(handler)


    def _enable_werkzeug_logger(self, handler):
        logger = logging.getLogger('werkzeug')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

    def resource_not_found(self):
        return self.app.make_response({'code': 404, 'message': 'Resource not found.'})

    def generic_error_handler(self):
        return {'code': 404, 'message': 'Generic error.'}

    def teardown(self, exception):
        """
        context teardown based deallocation
        :param exception:
        :type exception: Exception
        :return:
        """
        if exception is not None:
            self.app.logger.info(exception.message)

    def register(self, service):
        service.set_app(self.app, self.root_url)


class AppKernelException(Exception):
    def __init__(self, message):
        """
        A base exception class for AppKernel
        :param message: the cause of the failure
        """
        super(AppKernelException, self).__init__(message)


class AppInitialisationError(AppKernelException):

    def __init__(self, message):
        super(AppInitialisationError, self).__init__(message)


class CfgEngine(object):
    """
    Encapsulates application configuration. One can use it for retrieving various section form the configuration.
    """

    def __init__(self, cfg_dir, config_file_name='cfg.yml'):
        """
        :param cfg_dir:
        """
        config_file = '{}/{}'.format(cfg_dir.rstrip('/'), config_file_name)
        if not os.access(config_file, os.R_OK):
            raise AppInitialisationError('The config file {} is missing or not readable. '.format(config_file))

        with open(config_file, 'r') as ymlfile:
            try:
                self.cfg = yaml.load(ymlfile)
            except yaml.scanner.ScannerError as se:
                raise AppInitialisationError('cannot read configuration file due to: {}'.format(config_file))

    def get(self, path_expression):
        """
        :param path_expression: a . (dot) separated path to the configuration value: 'appkernel.backup_count'
        :type path_expression: str
        :return:
        """
        assert path_expression is not None, 'Path expression should be provided.'

        nodes = path_expression.split('.')
        return self.get_value_for_path_list(nodes)

    def get_value_for_path_list(self, config_nodes, section_dict=None):
        """
        :return: a section (or value) under the given array keys
        """
        assert isinstance(config_nodes, list), 'config_nodes should be a string list'
        if section_dict is None:
            section_dict = self.cfg
        if len(config_nodes) == 0:
            return None
        elif len(config_nodes) == 1:
            # final element
            return section_dict.get(config_nodes[0])
        else:
            key = config_nodes.pop(0)
            return self.get_value_for_path_list(config_nodes, section_dict.get(key))
