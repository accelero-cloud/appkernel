from flask import Flask

from appkernel import Model, Service, Property, NotEmpty, content_hasher, AppKernelEngine
from appkernel.repository import MongoRepository, AuditableRepository
from appkernel.validators import Email
from tutorials.server import uuid_generator


class User(Model, AuditableRepository, Service):
    id = Property(str, required=True, generator=uuid_generator('U'))
    name = Property(str, required=True, validators=[NotEmpty])
    email = Property(str, required=True, validators=[Email, NotEmpty])
    password = Property(str, required=True, validators=[NotEmpty],
                        converter=content_hasher(rounds=10), omit=True)
    roles = Property(list, sub_type=str, default_value=['Login'])


application_id = 'task_management_app'
app = Flask(__name__)
kernel = AppKernelEngine(application_id, app=app)

if __name__ == '__main__':
    kernel.register(User)
    user = User(name='Test User', email='test@accelero.cloud', password='some pass')
    user.save()
    kernel.run()
