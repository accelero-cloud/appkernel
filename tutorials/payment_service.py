from appkernel import Controller, Role
from appkernel.model import resource
from tutorials.order_service import AuthorisationRequest


class PaymentService(Controller):

    @resource(http_method='POST', require=[Role('user')])
    def authorize(self, authorisation: AuthorisationRequest):
        assert authorisation is not None
        return True