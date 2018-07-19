class HttpClientServiceProxyFactory(object):

    @staticmethod
    def get(root_url: str):
        return HttpClientServiceProxy()


class HttpClientServiceProxy(object):

    def __init__(self, root_url: str):
        self.root_url = root_url

    def __getattr__(self, item):
        print(item)
