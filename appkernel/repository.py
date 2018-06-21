from datetime import datetime
import pymongo
import operator

from bson import ObjectId
from pymongo.errors import CollectionInvalid

from appkernel.configuration import config
from appkernel.util import OBJ_PREFIX
from .model import Model, Expression, AppKernelException, SortOrder, Property, Index, TextIndex, UniqueIndex, \
    CustomProperty
from pymongo.collection import Collection
from functools import reduce


def xtract(cls):
    """
    Extract class name from class
    :param cls: the class object
    :return: the name of the desired collection
    """
    return '{}s'.format(cls.__name__)


class Query(object):
    """a class representing the query"""

    def __init__(self, *expressions):
        self.filter_expr = {}
        self.sorting_expr = {}
        self.__prep_expressions(*expressions)

    def __prep_expressions(self, *expressions):
        if not expressions:
            return
        where = reduce(operator.and_, expressions)
        if isinstance(where, Expression):
            if isinstance(where.lhs, (Property, CustomProperty)):
                if where.lhs.backreference.within_an_array:
                    # this query is part of an array
                    self.filter_expr[str(where.lhs.backreference.array_parameter_name)] = where.ops.lmbda(
                        (where.lhs.backreference.parameter_name, Query.__extract_rhs(where.rhs)))
                else:
                    # its only parameter to parameter comparison
                    self.filter_expr[str(where.lhs.backreference.parameter_name)] = where.ops.lmbda(
                        Query.__extract_rhs(where.rhs))
            elif isinstance(where.lhs, Expression) and isinstance(where.rhs, Expression):
                # two expressions are compared to each other
                expressions = [{where.lhs.lhs.backreference.parameter_name:
                                    where.lhs.ops.lmbda(Query.__extract_rhs(where.lhs.rhs))},
                               {where.rhs.lhs.backreference.parameter_name:
                                    where.rhs.ops.lmbda(Query.__extract_rhs(where.rhs.rhs))}]
                self.filter_expr[str(where.ops)] = [expression for expression in expressions]

    @staticmethod
    def __extract_rhs(right_hand_side):
        if isinstance(right_hand_side, Property):
            return right_hand_side.backreference.parameter_name
        else:
            return right_hand_side

    def sort_by(self, *sorting_tuples):
        """
        Defines sorting criteria (eg. .sort_by(User.name.desc())
        :param sorting_tuples: desc() or asc() on the Model parameter
        :return: self for calling further methods on the class
        :rtype: Query
        """
        self.sorting_expr = list(sorting_tuples)
        return self

    def find(self):
        """
        Creates a cursor based on the filter and sorting criteria and yields the results;
        :return: a generator object which yields found instances of Model class
        """
        raise NotImplemented('abstract method')

    def find_one(self):
        """
        :return: One or none instances of the Model, depending on the query criteria
        """
        raise NotImplemented('abstract method')

    def count(self):
        """
        :return: the number of items in the repository matching the filter expression;
        """
        raise NotImplemented('abstract method')

    def delete(self):
        """
        Delete all elements which fulfill the filter criteria (defined in the where method);
        :return: the deleted item count
        """
        raise NotImplemented('abstract method')

    def get(self, page=0, page_size=100):
        """
        Returns the list of found Model instances;
        :param page: the current page requested
        :param page_size: the size of the page (number of elements requested
        :return: the result of the query as a list of Model instance objects
        """
        raise NotImplemented('abstract method')


class MongoQuery(Query):
    def __init__(self, connection_object, user_class, *expressions):
        super(MongoQuery, self).__init__(*expressions)
        self.connection = connection_object
        self.user_class = user_class

    def find(self, page=0, page_size=100):
        if len(self.sorting_expr) == 0:
            cursor = self.connection.find(self.filter_expr).skip(page * page_size).limit(page_size)
        else:
            cursor = self.connection.find(self.filter_expr).sort(self.sorting_expr).skip(page * page_size).limit(
                page_size)
        if cursor:
            for item in cursor:
                yield Model.from_dict(item, self.user_class, convert_ids=True)

    def get(self, page=0, page_size=100):
        return [item for item in self.find(page=page, page_size=page_size)]

    def find_one(self):
        """
        :return: one instance of the Model or None
        :rtype: Model
        """
        hit = self.connection.find_one(self.filter_expr)
        return Model.from_dict(hit, self.user_class, convert_ids=True) if hit else None

    def delete(self):
        return self.connection.delete_many(self.filter_expr).deleted_count

    def count(self):
        return self.connection.count(self.filter_expr)


class RepositoryException(AppKernelException):
    def __init__(self, value):
        super(AppKernelException, self).__init__('The parameter {} is required.'.format(value))


class Repository(object):

    @classmethod
    def find_by_id(cls, object_id):
        """
        Find an object identified by the unique database id
        :param object_id: the database id
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def delete_by_id(cls, object_id):
        """
        Delete the object identified by ID
        :param object_id: the unique object ID
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def create_object(cls, document):
        """
        Insert a new object in the database
        :param document:
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def replace_object(cls, object_id, document):
        """
        Replace the object in the database.
        :param object_id:
        :param document:
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def patch_object(cls, document, object_id=None):
        raise NotImplemented('abstract method')

    @classmethod
    def save_object(cls, document, object_id=None):
        raise NotImplemented('abstract method')

    @classmethod
    def find(cls, *expressions):
        """

        :param expressions:
        :type expressions: Expression
        :return: a Model Generator
        """
        raise NotImplemented('abstract method')

    @classmethod
    def find_one(cls, *expressions):
        """
        Returns one single instance of the Model.
        :param expressions:
        :type expressions: Expression
        :return: one Model object
        :rtype: Model
        """
        raise NotImplemented('abstract method')

    @classmethod
    def where(cls, *expressions):
        """
        Creates and returns a query object, used for further chaining functions like sorting and pagination;
        :param expressions: the query filter expressions used to narrow the result-set
        :return: a query object preconfigured with the
        :rtype: Query
        """
        raise NotImplemented('abstract method')

    @classmethod
    def find_by_query(cls, query={}, page=1, page_size=50, sort_by=None, sort_order=SortOrder.ASC):
        """

        :param query:
        :type query: dict
        :param page:
        :type page: int
        :param page_size:
        :type page_size: int
        :param sort_by:
        :param sort_order:
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def create_cursor_by_query(cls, query):
        raise NotImplemented('abstract method')

    @classmethod
    def update_many(cls, match_query_dict, update_expression_dict):
        """

        :param match_query_dict:
        :param update_expression_dict:
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def delete_many(cls, match_query_dict):
        """

        :param match_query_dict:
        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def delete_all(cls):
        """

        :return:
        """
        raise NotImplemented('abstract method')

    @classmethod
    def count(cls, query_filter={}):
        """
        Return the number of items matching the query filter
        :param query_filter: the raw query type as a dict (using the mongo syntax)
        :type query_filter: dict
        :return:
        """
        raise NotImplemented('abstract method')

    def save(self):
        """
        Saves or updates a model instance in the database
        :return: the id of the inserted or updated document
        """
        raise NotImplemented('abstract method')

    def delete(self):
        """
        Delete the current instance.
        :return:
        """
        raise NotImplemented('abstract method')


class MongoRepository(Repository):

    @classmethod
    def init_indexes(cls):
        if issubclass(cls, Model):
            index_factories = {
                Index: MongoRepository.create_index,
                TextIndex: MongoRepository.create_text_index,
                UniqueIndex: MongoRepository.create_unique_index
            }

            for key, value in cls.__dict__.items():
                if isinstance(value, Property):
                    if value.index:
                        fct = index_factories.get(value.index, MongoRepository.not_supported)
                        fct(cls.get_collection(), key,
                            value.index.sort_order if hasattr(value.index, 'sort_order') else SortOrder.ASC)

    @staticmethod
    def version_check(required_version_tuple):
        server_info = config.mongo_database.client.server_info()
        current_version = tuple(int(i) for i in server_info['version'].split('.'))
        if current_version < required_version_tuple:
            raise AppKernelException(
                'This feature requires a min version of: {}'.format('.'.join(required_version_tuple)))

    @classmethod
    def add_schema_validation(cls, validation_action='warn'):
        """
        :param validation_action: warn or error (MongoDB logs any violations but allows the insertion or update to proceed)
        :return:
        """
        MongoRepository.version_check(tuple([3, 6, 0]))
        try:
            config.mongo_database.create_collection(xtract(cls))
        except CollectionInvalid as cix:
            pass

        config.mongo_database.command(
            'collMod', xtract(cls),
            validator={'$jsonSchema': cls.get_json_schema(mongo_compatibility=True)},
            validationLevel='moderate',
            validationAction=validation_action
        )

    @staticmethod
    def create_index(collection, field_name, sort_order, unique=False):
        # type: (pymongo.collection.Collection, str, SortOrder, bool) -> ()

        """
        Args:
            collection(pymongo.collection.Collection): the collection to which the index is applied to
            field_name(str): the name of the document field which is being indexed
            sort_order(SortOrder): the sort order
            unique(bool): if true (false by default) it will create a unique index
        """
        if field_name not in collection.index_information():
            if isinstance(sort_order, SortOrder):
                direction = pymongo.ASCENDING if sort_order == SortOrder.ASC else pymongo.DESCENDING
            else:
                direction = sort_order
            collection.create_index(
                [(field_name, direction)],
                unique=unique, background=True, name='{}_idx'.format(field_name))

    @staticmethod
    def create_text_index(collection, field_name, *args):
        # type: (pymongo.collection.Collection, str, SortOrder, bool) -> ()
        MongoRepository.create_index(collection, field_name, pymongo.TEXT)

    @staticmethod
    def create_unique_index(collection, field_name, sort_order):
        MongoRepository.create_index(collection, field_name, sort_order, unique=True)

    @staticmethod
    def not_supported(*args):
        pass

    @classmethod
    def get_collection(cls):
        # type: () -> pymongo.collection.Collection
        """
        :return: the collection for this model object
        :rtype: Collection
        """
        db = config.mongo_database
        if db is not None:
            return db.get_collection(xtract(cls))
        else:
            raise AppKernelException('The database engine is not set')

    @classmethod
    def find_by_id(cls, object_id):
        assert object_id, 'the id of the lookup object must be provided'
        if isinstance(object_id, str) and object_id.startswith(OBJ_PREFIX):
            object_id = ObjectId(object_id.split(OBJ_PREFIX)[1])
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
    def prepare_document(document, object_id=None):
        if isinstance(document, Model):
            document_id = document.id
            has_id = document_id is not None
            document = Model.to_dict(document, convert_id=True)
        elif not isinstance(document, dict):
            raise RepositoryException('Only dictionary or Model is accepted.')
        else:
            document_id = object_id or document.get('id') or document.get('_id')
            has_id = document_id is not None
        return has_id, document_id, document

    @classmethod
    def patch_object(cls, document, object_id=None):
        return cls.save_object(document, object_id=object_id, insert_if_none_found=False)

    @classmethod
    def save_object(cls, document, object_id=None, insert_if_none_found=True):
        # type: (object) -> object
        assert document, 'the document must be handed over as a parameter'
        has_id, document_id, document = MongoRepository.prepare_document(document, object_id)
        if has_id:
            update_result = cls.get_collection().update_one({'_id': document_id}, {'$set': document},
                                                            upsert=insert_if_none_found)
            return update_result.upserted_id or (document_id if update_result.matched_count > 0 else None)
        else:
            insert_result = cls.get_collection().insert_one(document)
            return insert_result.inserted_id  # pylint: disable=C0103

    @classmethod
    def replace_object(cls, document):
        assert document, 'the document must be provided before replacing'
        has_id, document_id, document = MongoRepository.prepare_document(document, None)
        update_result = cls.get_collection().replace_one({'_id': document_id}, document, upsert=False)
        return (update_result.upserted_id or document_id) if update_result.matched_count > 0 else None

    @classmethod
    def bulk_insert(cls, list_of_model_instances):
        return cls.get_collection().insert_many(
            [Model.to_dict(model, convert_id=True) for model in list_of_model_instances]).inserted_ids

    @classmethod
    def find(cls, *expressions):
        return MongoQuery(cls.get_collection(), cls, *expressions).find()

    @classmethod
    def find_one(cls, *expressions):
        return MongoQuery(cls.get_collection(), cls, *expressions).find_one()

    @classmethod
    def where(cls, *expressions):
        """
        Creates and returns a query object, used for further chaining functions like sorting and pagination;
        :param expressions: the query filter expressions used to narrow the result-set
        :return: a query object precofigured with the
        :rtype: MongoQuery
        """
        return MongoQuery(cls.get_collection(), cls, *expressions)

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
    def aggregate(cls, pipe=[], allow_disk_use=True, batch_size=100):
        cursor = cls.get_collection().aggregate(pipe, allowDiskUse=allow_disk_use, batchSize=batch_size)
        return [result for result in cursor]

    def save(self):
        document = Model.to_dict(self, convert_id=True)
        self.id = self.__class__.save_object(document)  # pylint: disable=C0103
        return self.id

    def delete(self):
        return self.get_collection().delete_one({'_id': self.id}).deleted_count


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
