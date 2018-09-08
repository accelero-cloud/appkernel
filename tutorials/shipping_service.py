import uuid
from datetime import datetime

from appkernel import date_now_generator, NotEmpty, Role, create_custom_error
from appkernel.http_client import HttpClientServiceProxy
from appkernel.model import Model, Property, resource
from tutorials.models import Address

client = HttpClientServiceProxy('http://127.0.0.1:5000/')


class Shipping(Model):
    reservation_id = Property(str, required=True, validators=NotEmpty)
    order_date = Property(datetime, required=True, generator=date_now_generator)
    delivery_address = Property(Address, required=True)


class ShippingService(object):

    def ship(self, address, products):
        print(f'request shipping to: {address} | products: {products}')
        return str(uuid.uuid4())

    @resource(method='POST', path='./', require=[Role('user')])
    def shipping_request(self, request: Shipping):
        code, reservation = client.wrap(f'/reservations/{request.reservation_id}/commit').patch()
        if code == 200:
            tracking_id = self.ship(request.delivery_address, reservation.products)
            code, reservation = client.wrap(f'/reservations/{request.reservation_id}/execute').patch(
                {'tracking_id': tracking_id})
            return reservation
        else:
            msg = reservation.get('message') if hasattr(reservation,
                                                        'message') else 'Error while calling reservation service.'
            return create_custom_error(code, msg, upstream_service='ShippingService')
