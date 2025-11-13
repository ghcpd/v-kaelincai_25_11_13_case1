from src.service_pre import SettleRequest


def test_create_settle_request():
    r = SettleRequest(orderId='O1', amount=1000, paymentMethod='card')
    assert r.orderId == 'O1'
    assert r.amount == 1000
    assert r.paymentMethod == 'card'
