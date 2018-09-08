import uuid
from appkernel import Role
from appkernel.model import resource
from tutorials.order_service import AuthorisationRequest


class PaymentService(object):

    @resource(http_method='POST', require=[Role('user')])
    def authorize(self, authorisation: AuthorisationRequest):
        assert authorisation is not None
        return {'auth_id': str(uuid.uuid4())}
