from pymongo import MongoClient
from datetime import datetime

from appkernel import AppKernelEngine
from model import Model, Expression


def xtract(cls):
    """
    :param cls: the class object
    :return: the name of the desired collection
    """
    return '{}s'.format(cls.__name__)


class Query(object):
    """a class representin the query"""

    def __init__(self):
        pass


class Repository(object):

    @classmethod
    def find_by_id(cls, object_id):
        raise NotImplemented('abstract method')

    @classmethod
    def find_by_id(cls, object_id):
        raise NotImplemented('abstract method')

    @classmethod
    def find(cls, *expressions):
        raise NotImplemented('abstract method')

    @classmethod
    def find_by_query(cls, query_dict={}, page=1, page_size=50):
        raise NotImplemented('abstract method')

    @classmethod
    def create_cursor_by_query(cls, query_dict):
        raise NotImplemented('abstract method')

    @classmethod
    def update_many(cls, match_query_dict, update_expression_dict):
        raise NotImplemented('abstract method')

    @classmethod
    def delete_many(cls, match_query_dict):
        raise NotImplemented('abstract method')

    @classmethod
    def delete_all(cls):
        raise NotImplemented('abstract method')

    @classmethod
    def count(cls, query_filter={}):
        raise NotImplemented('abstract method')

    def save(self):
        raise NotImplemented('abstract method')

    def delete(self):
        raise NotImplemented('abstract method')


class MongoRepository(Repository):

    def collection(self):
        return AppKernelEngine.database[xtract(self.__class__)]

    @classmethod
    def get_collection(cls):
        return AppKernelEngine.database[xtract(cls)]

    @classmethod
    def find_by_id(cls, object_id):
        assert object_id, 'the id of the lookup object must be provided'
        document_dict = cls.get_collection().find_one({'_id': object_id})
        return Model.from_dict(document_dict, cls, convert_ids=True) if document_dict else None

    @classmethod
    def find(cls, *expressions):
        cls.get_collection().find()

    @classmethod
    def _parse_expressions(cls, expressions):
        raise NotImplemented
        # assert isinstance(expressions, list), 'The converter lists only'
        # if len(expressions) < 2:
        # for expr in expressions:
        #     assert isinstance(expr, Expression), 'Queries can only be built using {}.'.format(Expression.__class__.__name__)

    @classmethod
    def find_by_query(cls, query_dict={}, page=1, page_size=50):
        """
        query using mongo's built-in query language
        :param page_size:
        :param page:
        :param query_dict: the query expression as a dictionary
        :return: a generator with the query results
        """
        cursor = cls.get_collection().find(query_dict).skip((page - 1) * page_size).limit(page_size)
        return [Model.from_dict(result, cls, convert_ids=True) for result in cursor]

    @classmethod
    def create_cursor_by_query(cls, query_dict):
        cursor = cls.get_collection().find(query_dict)
        return (Model.from_dict(result, cls, convert_ids=True) for result in cursor)

    @classmethod
    def update_many(cls, match_query_dict, update_expression_dict):
        """
        updates multiple documents in the database
        :param match_query_dict: the query expression to match the documents to be updated
        :param update_expression_dict:
        :return: the number of modified documents
        """
        update_result = cls.get_collection().update_many(match_query_dict, update_expression_dict)
        return update_result.modified_count

    @classmethod
    def delete_many(cls, match_query_dict):
        return cls.get_collection().delete_many(match_query_dict).deleted_count

    @classmethod
    def delete_all(cls):
        """
        deletes all documents from the collection
        :return: the count of deleted documents
        """
        return cls.get_collection().delete_many({}).deleted_count

    @classmethod
    def count(cls, query_filter={}):
        return cls.get_collection().count(query_filter)

    @classmethod
    def aggregate(cls, pipeline_dict, allow_disk_use=False, batch_size=100):
        return cls.get_collection().aggregate(pipeline_dict, allowDiskUse=allow_disk_use, batchSize=batch_size)

    def save(self):
        """
        Saves or updates a document in the database
        :return: the id of the inserted or upserted document
        """
        document = Model.to_dict(self, convert_id=True)
        if hasattr(self, 'id'):
            update_result = self.collection().update_one({'_id': self.id}, {'$set': document}, upsert=True)
            return update_result.upserted_id or self.id
        else:
            insert_result = self.collection().insert_one(document)
            self.id = insert_result.inserted_id
            return self.id

    def delete(self):
        return self.collection().delete_one({'_id': self.id}).deleted_count


class AuditableRepository(MongoRepository):

    def __init__(self, **kwargs):
        super(AuditableRepository, self).__init__()

    def save(self):
        now = datetime.now()
        document = Model.to_dict(self, convert_id=True)
        document.update(updated=now)

        if hasattr(self, 'id'):
            # it is an update or a first insert with generated ID
            if 'version' in document:
                del document['version']
            upsert_expression = {
                '$set': document,
                '$setOnInsert': {'inserted': now},
                '$inc': {'version': 1}
            }
            update_result = self.collection().update_one({'_id': self.id}, upsert_expression, upsert=True)
            return update_result.upserted_id or self.id
        else:
            # it is an insert for sure, we initialise the audit fields
            document.update(inserted=now, version=1)
            insert_result = self.collection().insert_one(document)
            return insert_result.inserted_id

# todo:
# build unique index (eg. for username)