from flask import Flask

from appkernel import Model, Service, Parameter, NotEmpty, password_hasher, AppKernelEngine
from appkernel.repository import MongoRepository, AuditableRepository
from appkernel.validators import Email
from tutorials.server import uuid_generator


class User(Model, AuditableRepository, Service):
    id = Parameter(str, required=True, generator=uuid_generator('U'))
    name = Parameter(str, required=True, validators=[NotEmpty])
    email = Parameter(str, required=True, validators=[Email, NotEmpty])
    password = Parameter(str, required=True, validators=[NotEmpty],
                         value_converter=password_hasher(rounds=10), omit=True)
    roles = Parameter(list, sub_type=str, default_value=['Login'])


application_id = 'task_management_app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)

if __name__ == '__main__':
    kernel.register(User)
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()
    kernel.run()
