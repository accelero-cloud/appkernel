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

def read_custom_code(fileobj):
        import ast

        def show_info(function_node):
            print("\nFunction name:", function_node.name)
            print("Args:")
            for arg in function_node.args.args:
                # import pdb; pdb.set_trace()
                print("\tparameter name: {}".format(arg.id))

        node = ast.parse(fileobj.read())
        functions = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        classes = [n for n in node.body if isinstance(n, ast.ClassDef)]

        for fct in functions:
            show_info(fct)

        for class_ in classes:
            print("Class name:", class_.name)
            methods = [n for n in class_.body if isinstance(n, ast.FunctionDef)]
            for method in methods:
                show_info(method)

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
