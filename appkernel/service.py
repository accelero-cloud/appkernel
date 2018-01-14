from flask import Flask, jsonify, current_app, request
from model import Model
from appkernel import AppKernelEngine
from appkernel.repository import Repository, xtract
from reflection import *


class Service(object):
    pretty_print = True
    """
    The Flask App is set on this instance, so one can use the context:
    with self.app_context():
        some_varibale = some_context_aware_function()
    """

    @classmethod
    def set_app_engine(cls, app_engine, url_base):
        """
        :param url_base: the url where the service is exposed
        :type url_base: basestring
        :param app_engine: the app kernel engine
        :type app_engine: AppKernelEngine
        :return:
        """
        cls.app = app_engine.app
        cls.app_engine = app_engine
        if not url_base.endswith('/'):
            url_base = '{}/'.format(url_base)
        ep = '{}{}'.format(url_base, xtract(cls).lower())
        if issubclass(cls, Repository) and 'find_by_id' in dir(cls):
            # generate get by id
            cls.app.add_url_rule('{}/<string:object_id>'.format(ep), 'get_by_id_{}'.format(ep), Service.execute(app_engine, cls.find_by_id),
                                 methods=['GET'])
            cls.app.add_url_rule('{}'.format(ep), 'get_{}'.format(ep),
                                 Service.execute(app_engine, cls.find_by_id),
                                 methods=['GET'])
            cls.app.add_url_rule('{}/<object_id>'.format(ep), 'delete_{}'.format(ep), Service.execute(app_engine, cls.delete_by_id),
                                 methods=['DELETE'])

    @classmethod
    def execute(cls, app_engine, provisioner_method):
        """
        :param app_engine: the app engine instance
        :param provisioner_method: the method which will be executed by Flask
        :return:
        """

        def is_basic(obj):
            return is_primitive(obj) or is_noncomplex(obj) or isinstance(obj, (str, basestring))

        def create_executor(**named_args):
            try:
                print '>>> current app name: {}'.format(current_app.name)
                print '{}'.format(current_app._get_current_object())
                print '{}'.format(request.method)
                print '{}'.format()
                na = named_args.update(request.args)
                result = provisioner_method(**na)
                # request.args.get('key', '')
                result_dic_tentative = Service.xvert(result) if result else {}
                if is_basic(result_dic_tentative):
                    result_dic_tentative = {'result': result_dic_tentative}
                return jsonify(result_dic_tentative), 200
            except Exception as exc:
                app_engine.app.logger.error('exception caught while executing service call: {}'.format(str(exc)), exc)
                return app_engine.generic_error_handler(exc)

        return create_executor

    @staticmethod
    def xvert(result_item):
        if isinstance(result_item, Model):
            return Model.to_dict(result_item)
        elif is_dictionary(result_item) or is_dictionary_subclass(result_item):
            return result_item
        elif isinstance(result_item, (list, set, tuple)):
            return [Service.xvert(item) for item in result_item]
        elif is_primitive(result_item) or isinstance(result_item, (str, basestring)) or is_noncomplex(result_item):
            return result_item
