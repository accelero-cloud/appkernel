#!/usr/bin/python
from contextlib import contextmanager


class Table(object):
    def __init__(self, table_name):
        self.table_name = table_name
        self.fields = {}

    def __getattr__(self, name):
        def func(**kvs):
            self.fields[name] = kvs
        return func

    def execute(self):
        print "Creating table %s with fields %s" % (self.table_name, self.fields)

#Creating table cookies with fields {'kind': {'length': 30, 'type': 'char'}, 'yumminess': {'length': 30, 'type': 'char'}, 'servings': {'type': 'int'}}

@contextmanager
def create_table(table_name):
    table = Table(table_name)
    yield table
    table.execute()


if __name__ == "__main__":
    table = Table('cookies')
    table.kind(type='char', length=30)
    table.yumminess(type='char', length=30)
    table.servings(type='int')
    table.execute()

    # with create_table('cookies') as t:
    #     t.kind(type='char', length=30)
    #     t.yumminess(type='char', length=30)
    #     t.servings(type='int')
