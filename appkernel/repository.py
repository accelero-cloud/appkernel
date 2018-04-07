from datetime import datetime

import pymongo

from appkernel import AppKernelEngine
from model import Model, Expression, AppKernelException
from pymongo.collection import Collection
from enum import Enum


def xtract(cls):
    """
    Extract class name from class
    :param cls: the class object
    :return: the name of the desired collection
    """
    return '{}s'.format(cls.__name__)


class Query(object):
    """a class representin the query"""

    def __init__(self):
        pass


class SortOrder(Enum):
    ASC = 1
    DESC = 2


class RepositoryException(AppKernelException):
    def __init__(self, value):
        super(AppKernelException, self).__init__('The parameter {} is required.'.format(value))


class Repository(object):

    @classmethod
    def find_by_id(cls, object_id):
        raise NotImplemented('abstract method')

    @classmethod
    def delete_by_id(cls, object_id):
        raise NotImplemented('abstract method')

    @classmethod
    def create_object(cls, document):
        raise NotImplemented('abstract method')

    @classmethod
    def replace_object(cls, object_id, document):
        raise NotImplemented('abstract method')

    @classmethod
    def save_object(cls, document, object_id=None):
        raise NotImplemented('abstract method')

    @classmethod
    def find(cls, *expressions):
        raise NotImplemented('abstract method')

    @classmethod
    def find_by_query(cls, query={}, page=1, page_size=50, sort_by=None, sort_order=SortOrder.ASC):
        raise NotImplemented('abstract method')

    @classmethod
    def create_cursor_by_query(cls, query):
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
        """
        Saves or updates a document in the database
        :return: the id of the inserted or updated document
        """
        raise NotImplemented('abstract method')

    def delete(self):
        raise NotImplemented('abstract method')


class MongoRepository(Repository):

    def collection(self):
        return AppKernelEngine.database[xtract(self.__class__)]

    @classmethod
    def get_collection(cls):
        """
        :return: the collection for this model object
        :rtype: Collection
        """
        if AppKernelEngine.database is not None:
            return AppKernelEngine.database[xtract(cls)]
        else:
            raise AppKernelException('The database engine is not set')

    @classmethod
    def find_by_id(cls, object_id):
        assert object_id, 'the id of the lookup object must be provided'
        document_dict = cls.get_collection().find_one({'_id': object_id})
        return Model.from_dict(document_dict, cls, convert_ids=True) if document_dict else None

    @classmethod
    def delete_by_id(cls, object_id):
        """
        Deletes a document identified by the object id
        :param object_id:
        :return: true if the object was deleted
        """
        delete_result = cls.get_collection().delete_one({'_id': object_id})
        return delete_result.deleted_count

    @staticmethod
    def prepare_document(document, object_id):
        if isinstance(document, Model):
            document_id = document.id
            has_id = document_id is not None
            document = Model.to_dict(document, convert_id=True)
        elif not isinstance(document, dict):
            raise RepositoryException('Only dictionary or Model is accepted.')
        else:
            has_id = object_id or 'id' in document or '_id' in document
            document_id = object_id or document.get('id') or document.get('_id')
        return has_id, document_id, document

    @classmethod
    def save_object(cls, document, object_id=None):
        # type: (object) -> object
        assert document, 'the document must be handed over as a parameter'
        has_id, document_id, document = MongoRepository.prepare_document(document, object_id)
        if has_id:
            update_result = cls.get_collection().update_one({'_id': document_id}, {'$set': document}, upsert=True)
            return update_result.upserted_id or document_id
        else:
            insert_result = cls.get_collection().insert_one(document)
            return insert_result.inserted_id  # pylint: disable=C0103

    @classmethod
    def replace_object(cls, document):
        assert document, 'the document must be provided before replacing'
        has_id, document_id, document = MongoRepository.prepare_document(document, None)
        update_result = cls.get_collection().replace_one({'_id': document_id}, document, upsert=False)
        return update_result.upserted_id or document_id

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
    def find_by_query(cls, query={}, page=1, page_size=50, sort_by=None, sort_order=SortOrder.ASC):
        """
        query using mongo's built-in query language
        :param sort_order:
        :param sort_by:
        :param page_size:
        :param page:
        :param query: the query expression as a dictionary
        :return: a generator with the query results
        """
        cursor = cls.get_collection().find(query).skip((page - 1) * page_size).limit(page_size)
        if sort_by:
            py_direction = pymongo.ASCENDING if sort_order == SortOrder.ASC else pymongo.DESCENDING
            cursor.sort(sort_by, direction=py_direction)
        return [Model.from_dict(result, cls, convert_ids=True) for result in cursor]

    @classmethod
    def create_cursor_by_query(cls, query):
        cursor = cls.get_collection().find(query)
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
    def aggregate(cls, pipeline_dict, allow_disk_use=False, batch_size=100, page=1, page_size=50):
        cursor = cls.get_collection().aggregate(pipeline_dict, allowDiskUse=allow_disk_use, batchSize=batch_size).skip(
            (page - 1) * page_size).limit(page_size)
        return [result for result in cursor]

    def save(self):
        """
        Saves or updates a document in the database
        :return: the id of the inserted or upserted document
        """
        document = Model.to_dict(self, convert_id=True)
        self.id = self.__class__.save_object(document)  # pylint: disable=C0103
        return self.id

    def delete(self):
        return self.collection().delete_one({'_id': self.id}).deleted_count


class AuditableRepository(MongoRepository):

    def __init__(self, **kwargs):
        super(AuditableRepository, self).__init__()

    @classmethod
    def save_object(cls, document, object_id=None):

        has_id, doc_id, document = MongoRepository.prepare_document(document, object_id)
        now = datetime.now()
        document.update(updated=now)

        if has_id:
            # it is an update or a first insert with generated ID
            if 'version' in document:
                del document['version']
            if 'inserted' in document:
                del document['inserted']
            upsert_expression = {
                '$set': document,
                '$setOnInsert': {'inserted': now},
                '$inc': {'version': 1}
            }
            update_result = cls.get_collection().update_one({'_id': doc_id}, upsert_expression, upsert=True)
            return update_result.upserted_id or doc_id
        else:
            # it is an insert for sure, we initialise the audit fields
            document.update(inserted=now, version=1)
            insert_result = cls.get_collection().insert_one(document)
            return insert_result.inserted_id

    def save(self):
        self.id = self.__class__.save_object(Model.to_dict(self, convert_id=True))
        return self.id

# todo:
# build unique index (eg. for username)
