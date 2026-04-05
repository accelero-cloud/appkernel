from __future__ import annotations

import inspect
import operator
import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import reduce
from typing import Any, Generator, TYPE_CHECKING

import pymongo
from bson import ObjectId
from pymongo.collection import Collection, ReturnDocument
from pymongo.errors import CollectionInvalid

from appkernel.configuration import config
from appkernel.util import OBJ_PREFIX
from .model import Model, Expression, AppKernelException, SortOrder, Property, Index, TextIndex, UniqueIndex, \
    CustomProperty


def xtract(clazz_or_instance: Any) -> str:
    """
    Extract class name from class, removing the Service/Controller/Resource ending and adding a plural -s or -ies.
    :param clazz_or_instance: the class object
    :return: the name of the desired collection
    """
    clazz_name = clazz_or_instance.__name__ if inspect.isclass(
        clazz_or_instance) else clazz_or_instance.__class__.__name__
    name = re.split('Service|Controller|Resource', clazz_name)[0]
    if name[-2:] in ['sh', 'ch'] or name[-1:] in ['s', 'x', 'z']:
        name = f'{name}es'
    elif name[-1:] == 'y' and (name[-2:-1] in ["a", "e", "i", "o", "u"] or name[-3:-2] == 'qu'):
        name = f'{name[-1:]}ies'
    else:
        name = f'{name}s'
    return name


class Query:
    """a class representing the query"""

    def __init__(self, *expressions: Expression) -> None:
        self.filter_expr: dict[str, Any] = {}
        self.sorting_expr: list[Any] = {}
        self.__prep_expressions(*expressions)

    def __prep_expressions(self, *expressions: Expression) -> None:
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
                exprs: list[Any] = []
                exprs.extend(self.__xtract_expression(where))
                self.filter_expr[str(where.ops)] = [expression for expression in exprs]

    def __xtract_expression(self, expression: Expression) -> list[dict[str, Any]]:
        ret_val: list[dict[str, Any]] = []
        if isinstance(expression.lhs, Expression):
            ret_val.extend(self.__xtract_expression(expression.lhs))
        if isinstance(expression.rhs, Expression):
            ret_val.extend(self.__xtract_expression(expression.rhs))
        if isinstance(expression.lhs, Property):
            ret_val.append({
                expression.lhs.backreference.parameter_name:
                    expression.ops.lmbda(Query.__extract_rhs(expression.rhs))
            })
        if isinstance(expression.rhs, Property):
            ret_val.append({expression.lhs.backreference.parameter_name:
                                expression.ops.lmbda(Query.__extract_rhs(expression.rhs))})
        return ret_val

    @staticmethod
    def __extract_rhs(right_hand_side: Any) -> Any:
        if isinstance(right_hand_side, Property):
            return right_hand_side.backreference.parameter_name
        elif isinstance(right_hand_side, Enum):
            return right_hand_side.name
        else:
            return right_hand_side

    def sort_by(self, *sorting_tuples: Any) -> Query:
        """
        Defines sorting criteria (eg. .sort_by(User.name.desc())
        :param sorting_tuples: desc() or asc() on the Model parameter
        :return: self for calling further methods on the class
        :rtype: Query
        """
        self.sorting_expr = list(sorting_tuples)
        return self

    def find(self) -> Generator[Model, None, None]:
        """
        Creates a cursor based on the filter and sorting criteria and yields the results;
        :return: a generator object which yields found instances of Model class
        """
        raise NotImplementedError('abstract method')

    def find_one(self) -> Model | None:
        """
        :return: One or none instances of the Model, depending on the query criteria
        """
        raise NotImplementedError('abstract method')

    def count(self) -> int:
        """
        :return: the number of items in the repository matching the filter expression;
        """
        raise NotImplementedError('abstract method')

    def delete(self) -> int:
        """
        Delete all elements which fulfill the filter criteria (defined in the where method);
        :return: the deleted item count
        """
        raise NotImplementedError('abstract method')

    def get(self, page: int = 0, page_size: int = 100) -> list[Model]:
        """
        Returns the list of found Model instances;
        :param page: the current page requested
        :param page_size: the size of the page (number of elements requested
        :return: the result of the query as a list of Model instance objects
        """
        raise NotImplementedError('abstract method')


def mongo_type_converter_to_dict(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    else:
        return value


def mongo_type_converter_from_dict(value: Any) -> Any:
    return value


class MongoQuery(Query):
    def __init__(self, connection_object: Collection, user_class: type, *expressions: Expression) -> None:
        super().__init__(*expressions)
        self.connection: Collection = connection_object
        self.user_class = user_class

    def find(self, page: int = 0, page_size: int = 100) -> Generator[Model, None, None]:
        """
        Returns a generator for the number of pages
        :param page: current page
        :param page_size: number of elements
        :return: a generator which can be used in an iteration
        """
        if len(self.sorting_expr) == 0:
            cursor = self.connection.find(self.filter_expr).skip(page * page_size).limit(page_size)
        else:
            cursor = self.connection.find(self.filter_expr).sort(self.sorting_expr).skip(page * page_size).limit(
                page_size)
        if cursor:
            for item in cursor:
                yield Model.from_dict(item, self.user_class, convert_ids=True,
                                      converter_func=mongo_type_converter_from_dict)

    def get(self, page: int = 0, page_size: int = 100) -> list[Model]:
        """
        Return the complete list of all items corresponding to the query
        :param page: current page
        :param page_size: the number of elements
        :return: a list of all items corresponding the query
        """
        return [item for item in self.find(page=page, page_size=page_size)]

    def find_one(self) -> Model | None:
        """
        :return: one instance of the Model or None
        :rtype: Model
        """
        hit = self.connection.find_one(self.filter_expr)
        return Model.from_dict(hit, self.user_class, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if hit else None

    def delete(self) -> int:
        """
        :return: the delete count
        """
        return self.connection.delete_many(self.filter_expr).deleted_count

    def count(self) -> int:
        return self.connection.count_documents(self.filter_expr)

    def __get_update_expression(self, **update_expression: Any) -> dict[str, Any]:
        update_dict: dict[str, Any] = dict()
        for key, exp in update_expression.items():
            opname = str(exp.ops)
            op_expr = update_dict.get(opname, {})
            op_expr[key] = exp.ops.lmbda(exp.rhs)
            update_dict[opname] = op_expr
        return update_dict

    def find_one_and_update(self, **update_expression: Any) -> Model | None:
        upd = self.__get_update_expression(**update_expression)
        hit = self.connection.find_one_and_update(self.filter_expr, upd, return_document=ReturnDocument.AFTER)
        return Model.from_dict(hit, self.user_class, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if hit else None

    def update_one(self, **update_expression: Any) -> int:
        upd = self.__get_update_expression(**update_expression)
        update_result = self.connection.update_one(self.filter_expr, upd, upsert=False)
        return update_result.modified_count

    def update_many(self, **update_expression: Any) -> int:
        upd = self.__get_update_expression(**update_expression)
        update_result = self.connection.update_many(self.filter_expr, upd, upsert=False)
        return update_result.modified_count


class RepositoryException(AppKernelException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class Repository:

    @classmethod
    def find_by_id(cls, object_id: str) -> Model | None:
        """
        Find an object identified by the unique database id
        :param object_id: the database id
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def delete_by_id(cls, object_id: str) -> int:
        """
        Delete the object identified by ID
        :param object_id: the unique object ID
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def create_object(cls, document: dict[str, Any] | Model) -> Any:
        """
        Insert a new object in the database
        :param document:
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def replace_object(cls, object_id: str, document: dict[str, Any] | Model) -> Any:
        """
        Replace the object in the database.
        :param object_id:
        :param document:
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def patch_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    def save_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    def find(cls, *expressions: Expression) -> Generator[Model, None, None]:
        """

        :param expressions:
        :type expressions: Expression
        :return: a Model Generator
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def find_one(cls, *expressions: Expression) -> Model | None:
        """
        Returns one single instance of the Model.
        :param expressions:
        :type expressions: Expression
        :return: one Model object
        :rtype: Model
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def where(cls, *expressions: Expression) -> Query:
        """
        Creates and returns a query object, used for further chaining functions like sorting and pagination;
        :param expressions: the query filter expressions used to narrow the result-set
        :return: a query object preconfigured with the
        :rtype: Query
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def find_by_query(
        cls,
        query: dict[str, Any] = {},  # noqa: B006 - default used by supports_query() for runtime type detection
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_order: SortOrder = SortOrder.ASC,
        **kwargs: Any,
    ) -> list[Model]:
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
        raise NotImplementedError('abstract method')

    @classmethod
    def create_cursor_by_query(cls, query: dict[str, Any]) -> Generator[Model, None, None]:
        raise NotImplementedError('abstract method')

    @classmethod
    def update_many(cls, match_query_dict: dict[str, Any], update_expression_dict: dict[str, Any]) -> int:
        """

        :param match_query_dict:
        :param update_expression_dict:
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def delete_many(cls, match_query_dict: dict[str, Any]) -> int:
        """

        :param match_query_dict:
        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def delete_all(cls) -> int:
        """

        :return:
        """
        raise NotImplementedError('abstract method')

    @classmethod
    def count(cls, query_filter: dict[str, Any] | None = None) -> int:
        """
        Return the number of items matching the query filter
        :param query_filter: the raw query type as a dict (using the mongo syntax)
        :type query_filter: dict
        :return:
        """
        raise NotImplementedError('abstract method')

    def save(self) -> Any:
        """
        Saves or updates a model instance in the database
        :return: the id of the inserted or updated document
        """
        raise NotImplementedError('abstract method')

    def delete(self) -> None:
        """
        Delete the current instance.
        :raises RepositoryException: in case the instance was not deleted.
        """
        raise NotImplementedError('abstract method')


class MongoRepository(Repository):

    @classmethod
    def init_indexes(cls) -> None:
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
    def version_check(required_version_tuple: tuple[int, ...]) -> None:
        server_info = config.mongo_database.client.server_info()
        current_version = tuple(int(i) for i in server_info['version'].split('.'))
        if current_version < required_version_tuple:
            raise AppKernelException(
                f"This feature requires a min version of: {'.'.join(str(v) for v in required_version_tuple)}")

    @classmethod
    def add_schema_validation(cls, validation_action: str = 'warn') -> None:
        """
        :param validation_action: warn or error (MongoDB logs any violations but allows the insertion or update to proceed)
        :return:
        """
        MongoRepository.version_check(tuple([3, 6, 0]))
        try:
            config.mongo_database.create_collection(xtract(cls))
        except CollectionInvalid:
            # schema not found
            pass

        config.mongo_database.command(
            'collMod', xtract(cls),
            validator={'$jsonSchema': cls.get_json_schema(mongo_compatibility=True)},
            validationLevel='moderate',
            validationAction=validation_action
        )

    @staticmethod
    def create_index(
        collection: Collection,
        field_name: str,
        sort_order: SortOrder,
        unique: bool = False,
    ) -> None:
        """
        Args:
            collection(Collection): the collection to which the index is applied to
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
                unique=unique, background=True, name=f'{field_name}_idx')

    @staticmethod
    def create_text_index(collection: Collection, field_name: str, *args: Any) -> None:
        MongoRepository.create_index(collection, field_name, pymongo.TEXT)

    @staticmethod
    def create_unique_index(collection: Collection, field_name: str, sort_order: SortOrder) -> None:
        MongoRepository.create_index(collection, field_name, sort_order, unique=True)

    @staticmethod
    def not_supported(*args: Any) -> None:
        pass

    @classmethod
    def get_collection(cls) -> Collection:
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
    def find_by_id(cls, object_id: str) -> Model | None:
        assert object_id, 'the id of the lookup object must be provided'
        if isinstance(object_id, str) and object_id.startswith(OBJ_PREFIX):
            object_id = ObjectId(object_id.split(OBJ_PREFIX)[1])
        document_dict = cls.get_collection().find_one({'_id': object_id})
        return Model.from_dict(document_dict, cls, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if document_dict else None

    @classmethod
    def delete_by_id(cls, object_id: str) -> int:
        """
        Deletes a document identified by the object id
        :param object_id:
        :return: true if the object was deleted
        """
        delete_result = cls.get_collection().delete_one({'_id': object_id})
        return delete_result.deleted_count

    @staticmethod
    def prepare_document(
        document: dict[str, Any] | Model,
        object_id: str | None = None,
    ) -> tuple[bool, Any, dict[str, Any]]:
        if isinstance(document, Model):
            document_id = document.id
            has_id = document_id is not None
            document = Model.to_dict(document, convert_id=True, converter_func=mongo_type_converter_to_dict)
        elif not isinstance(document, dict):
            raise RepositoryException('Only dictionary or Model is accepted.')
        else:
            document_id = object_id or document.get('id') or document.get('_id')
            has_id = document_id is not None
        return has_id, document_id, document

    @classmethod
    def patch_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        return cls.__save_or_update_dict(document, object_id=object_id, insert_if_none_found=False)

    @classmethod
    def __save_or_update_dict(
        cls,
        document: dict[str, Any] | Model,
        object_id: str | None = None,
        insert_if_none_found: bool = True,
    ) -> Any:
        has_id, document_id, document = MongoRepository.prepare_document(document, object_id)
        if has_id:
            update_result = cls.get_collection().update_one({'_id': document_id}, {'$set': document},
                                                            upsert=insert_if_none_found)
            db_id = update_result.upserted_id or (document_id if update_result.matched_count > 0 else None)
        else:
            insert_result = cls.get_collection().insert_one(document)
            db_id = insert_result.inserted_id  # pylint: disable=C0103
        return db_id

    @classmethod
    def save_object(cls, model: Model, object_id: str | None = None, insert_if_none_found: bool = True) -> Any:
        assert model, 'the object must be handed over as a parameter'
        assert isinstance(model, Model), 'the object should be a Model'
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
        model.id = cls.__save_or_update_dict(document=document, object_id=object_id)
        return model.id

    @classmethod
    def replace_object(cls, model: Model) -> Any:
        assert model, 'the document must be provided before replacing'
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
        has_id, document_id, document = MongoRepository.prepare_document(document, None)
        update_result = cls.get_collection().replace_one({'_id': document_id}, document, upsert=False)
        return (update_result.upserted_id or document_id) if update_result.matched_count > 0 else None

    @classmethod
    def bulk_insert(cls, list_of_model_instances: list[Model]) -> list[Any]:
        return cls.get_collection().insert_many(
            [Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict) for model in
             list_of_model_instances]).inserted_ids

    @classmethod
    def find(cls, *expressions: Expression) -> Generator[Model, None, None]:
        return MongoQuery(cls.get_collection(), cls, *expressions).find()

    @classmethod
    def find_one(cls, *expressions: Expression) -> Model | None:
        return MongoQuery(cls.get_collection(), cls, *expressions).find_one()

    @classmethod
    def where(cls, *expressions: Expression) -> MongoQuery:
        """
        Creates and returns a query object, used for further chaining functions like sorting and pagination;
        :param expressions: the query filter expressions used to narrow the result-set
        :return: a query object precofigured with the
        :rtype: MongoQuery
        """
        return MongoQuery(cls.get_collection(), cls, *expressions)

    @classmethod
    def find_by_query(
        cls,
        query: dict[str, Any] = {},  # noqa: B006 - default used by supports_query() for runtime type detection
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_order: SortOrder = SortOrder.ASC,
        **kwargs: Any,
    ) -> list[Model]:
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
        return [Model.from_dict(result, cls, convert_ids=True, converter_func=mongo_type_converter_from_dict) for result
                in cursor]

    @classmethod
    def create_cursor_by_query(cls, query: dict[str, Any]) -> Generator[Model, None, None]:
        cursor = cls.get_collection().find(query)
        return (Model.from_dict(result, cls, convert_ids=True, converter_func=mongo_type_converter_from_dict) for result
                in cursor)

    @classmethod
    def update_many(cls, match_query_dict: dict[str, Any], update_expression_dict: dict[str, Any]) -> int:
        """
        updates multiple documents in the database
        :param match_query_dict: the query expression to match the documents to be updated
        :param update_expression_dict:
        :return: the number of modified documents
        """
        update_result = cls.get_collection().update_many(match_query_dict, update_expression_dict)
        return update_result.modified_count

    @classmethod
    def delete_many(cls, match_query_dict: dict[str, Any]) -> int:
        return cls.get_collection().delete_many(match_query_dict).deleted_count

    @classmethod
    def delete_all(cls) -> int:
        """
        deletes all documents from the collection
        :return: the count of deleted documents
        """
        return cls.get_collection().delete_many({}).deleted_count

    @classmethod
    def count(cls, query_filter: dict[str, Any] | None = None) -> int:
        query_filter = query_filter or {}
        return cls.get_collection().count_documents(query_filter)

    @classmethod
    def aggregate(
        cls,
        pipe: list[dict[str, Any]] = [],  # noqa: B006 - used by _autobox_parameters() for runtime type detection
        allow_disk_use: bool = True,
        batch_size: int = 100,
    ) -> list[dict[str, Any]]:
        cursor = cls.get_collection().aggregate(pipe, allowDiskUse=allow_disk_use, batchSize=batch_size)
        return [result for result in cursor]

    def save(self) -> Any:
        self.id = self.__class__.save_object(self)  # pylint: disable=C0103
        return self.id

    def delete(self) -> None:
        assert self.id is not None
        deleted_count = self.get_collection().delete_one({'_id': self.id}).deleted_count
        if deleted_count != 1:
            raise RepositoryException("the instance couldn't be deleted")


class AuditableRepository(MongoRepository):

    def __init__(self, **kwargs: Any) -> None:
        super().__init__()

    @classmethod
    def save_object(cls, model: Model, object_id: str | None = None) -> Any:
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
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
            db_id = update_result.upserted_id or doc_id
        else:
            # it is an insert for sure, we initialise the audit fields
            document.update(inserted=now, version=1)
            insert_result = cls.get_collection().insert_one(document)
            db_id = insert_result.inserted_id
        model.id = db_id
        return model.id

    def save(self) -> Any:
        self.__class__.save_object(self)
        return self.id
