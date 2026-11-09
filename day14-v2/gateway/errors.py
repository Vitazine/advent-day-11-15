"""Errors never carry request or provider text."""
class GatewayError(Exception):
    def __init__(self, code, status=422, categories=()):
        self.code, self.status, self.categories = code, status, tuple(categories)
        super().__init__(code)

    def body(self):
        return {'error': {'code': self.code, 'type': 'gateway_error',
                          'message': 'Запрос не выполнен: '+self.code, 'param': None}}
