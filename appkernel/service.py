from flask import Flask
from reflection import has_method
from appkernel.repository import Repository, xtract

class Service(object):
    """
    The Flask App is set on this instance, so one can use the context:
    with self.app_context():
        some_varibale = some_context_aware_function()
    """

    def set_app(self, app, url_base):
        """
        :param url_base: the url where the service is exposed
        :param app: flask app
        :type app: Flask
        :return:
        """
        self.app = app
        ep = '{}/{}'.format(url_base, xtract(self.__class__).lower())
        if issubclass(self, Repository) and has_method(self, 'find_by_id'):
            # generate get by id
            self.app.add_url_rule('{}/<id>'.format(ep), ep, self.__class__.find_by_id, methods=['GET'])
