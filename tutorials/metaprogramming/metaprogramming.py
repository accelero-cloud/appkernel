from flask import Flask
from passlib.handlers.pbkdf2 import pbkdf2_sha256
from flask_babel import _
from appkernel import Property, Model, MongoRepository, Service, UniqueIndex, Email, NotEmpty, password_hasher, \
    AppKernelEngine, Regexp, CurrentSubject, ServiceException, Anonymous, Role
from appkernel.service import link


class User(Model, MongoRepository, Service):
    id = Property(str)
    name = Property(str, required=True, index=UniqueIndex)
    email = Property(str, validators=[Email], index=UniqueIndex)
    password = Property(str, validators=[Regexp('(?=.{8,})')],
                        value_converter=password_hasher(), omit=True)
    roles = Property(list, sub_type=str, default_value=['Login'])

    @link(rel='change_password', http_method='POST', require=[CurrentSubject(), Role('admin')])
    def change_p(self, current_password, new_password):
        if not pbkdf2_sha256.verify(current_password, self.password):
            raise ServiceException(403, _('Current password is not correct'))
        else:
            self.password = new_password
            self.save()
        return _('Password changed')

    @link(require=Anonymous())
    def get_description(self):
        return self.description

app = Flask('demo')
kernel = AppKernelEngine('demo', app=app, enable_defaults=True)
kernel.register(User)
# let's create a sample user
user = User(name='Test User', email='test@accelero.cloud', password='some pass')
user.save()
kernel.run()