from flask import Flask
from reflection import has_method
from appkernel.repository import Repository, xtract

class Service(object):
    """
    The Flask App is set on this instance, so one can use the context:
    with self.app_context():
        some_varibale = some_context_aware_function()
    """
    @classmethod
    def set_app(cls, app, url_base):
        """
        :param url_base: the url where the service is exposed
        :param app: flask app
        :type app: Flask
        :return:
        """
        cls.app = app
        ep = '{}/{}'.format(url_base, xtract(cls).lower())
        if issubclass(cls, Repository) and 'find_by_id' in dir(cls):
            # generate get by id
            cls.app.add_url_rule('{}/<id>'.format(ep), ep, cls.find_by_id, methods=['GET'])
