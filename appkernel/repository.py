from __future__ import annotations

import inspect
import operator
import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import reduce
from typing import Any

import pymongo
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
from pymongo.errors import CollectionInvalid

from appkernel.configuration import config
from appkernel.util import OBJ_PREFIX
from .model import Model, Expression, AppKernelException, SortOrder, Property, Index, TextIndex, UniqueIndex, \
    CustomProperty


def xtract(clazz_or_instance: Any) -> str:
    """
    Extract class name from class, removing the Service/Controller/Resource ending and adding a plural -s or -ies.
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
                    self.filter_expr[str(where.lhs.backreference.array_parameter_name)] = where.ops.lmbda(
                        (where.lhs.backreference.parameter_name, Query.__extract_rhs(where.rhs)))
                else:
                    self.filter_expr[str(where.lhs.backreference.parameter_name)] = where.ops.lmbda(
                        Query.__extract_rhs(where.rhs))
            elif isinstance(where.lhs, Expression) and isinstance(where.rhs, Expression):
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
        self.sorting_expr = list(sorting_tuples)
        return self

    async def find(self) -> list[Model]:
        raise NotImplementedError('abstract method')

    async def find_one(self) -> Model | None:
        raise NotImplementedError('abstract method')

    async def count(self) -> int:
        raise NotImplementedError('abstract method')

    async def delete(self) -> int:
        raise NotImplementedError('abstract method')

    async def get(self, page: int = 0, page_size: int = 100) -> list[Model]:
        raise NotImplementedError('abstract method')


def mongo_type_converter_to_dict(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    else:
        return value


def mongo_type_converter_from_dict(value: Any) -> Any:
    return value


class MongoQuery(Query):
    def __init__(self, connection_object: AsyncIOMotorCollection, user_class: type, *expressions: Expression) -> None:
        super().__init__(*expressions)
        self.connection: AsyncIOMotorCollection = connection_object
        self.user_class = user_class

    async def find(self, page: int = 0, page_size: int = 100) -> list[Model]:
        if self.sorting_expr:
            cursor = self.connection.find(self.filter_expr).sort(self.sorting_expr).skip(page * page_size).limit(page_size)
        else:
            cursor = self.connection.find(self.filter_expr).skip(page * page_size).limit(page_size)
        docs = await cursor.to_list(length=page_size or None)
        return [Model.from_dict(item, self.user_class, convert_ids=True,
                                converter_func=mongo_type_converter_from_dict) for item in docs]

    async def get(self, page: int = 0, page_size: int = 100) -> list[Model]:
        return await self.find(page=page, page_size=page_size)

    async def find_one(self) -> Model | None:
        hit = await self.connection.find_one(self.filter_expr)
        return Model.from_dict(hit, self.user_class, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if hit else None

    async def delete(self) -> int:
        result = await self.connection.delete_many(self.filter_expr)
        return result.deleted_count

    async def count(self) -> int:
        return await self.connection.count_documents(self.filter_expr)

    def __get_update_expression(self, **update_expression: Any) -> dict[str, Any]:
        update_dict: dict[str, Any] = dict()
        for key, exp in update_expression.items():
            opname = str(exp.ops)
            op_expr = update_dict.get(opname, {})
            op_expr[key] = exp.ops.lmbda(exp.rhs)
            update_dict[opname] = op_expr
        return update_dict

    async def find_one_and_update(self, **update_expression: Any) -> Model | None:
        upd = self.__get_update_expression(**update_expression)
        hit = await self.connection.find_one_and_update(self.filter_expr, upd, return_document=ReturnDocument.AFTER)
        return Model.from_dict(hit, self.user_class, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if hit else None

    async def update_one(self, **update_expression: Any) -> int:
        upd = self.__get_update_expression(**update_expression)
        update_result = await self.connection.update_one(self.filter_expr, upd, upsert=False)
        return update_result.modified_count

    async def update_many(self, **update_expression: Any) -> int:
        upd = self.__get_update_expression(**update_expression)
        update_result = await self.connection.update_many(self.filter_expr, upd, upsert=False)
        return update_result.modified_count


class RepositoryException(AppKernelException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class Repository:

    @classmethod
    async def find_by_id(cls, object_id: str) -> Model | None:
        raise NotImplementedError('abstract method')

    @classmethod
    async def delete_by_id(cls, object_id: str) -> int:
        raise NotImplementedError('abstract method')

    @classmethod
    async def create_object(cls, document: dict[str, Any] | Model) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    async def replace_object(cls, object_id: str, document: dict[str, Any] | Model) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    async def patch_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    async def save_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        raise NotImplementedError('abstract method')

    @classmethod
    async def find(cls, *expressions: Expression) -> list[Model]:
        raise NotImplementedError('abstract method')

    @classmethod
    async def find_one(cls, *expressions: Expression) -> Model | None:
        raise NotImplementedError('abstract method')

    @classmethod
    def where(cls, *expressions: Expression) -> Query:
        raise NotImplementedError('abstract method')

    @classmethod
    async def find_by_query(
        cls,
        query: dict[str, Any] = {},  # noqa: B006 - default used by supports_query() for runtime type detection
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_order: SortOrder = SortOrder.ASC,
        **kwargs: Any,
    ) -> list[Model]:
        raise NotImplementedError('abstract method')

    @classmethod
    async def create_cursor_by_query(cls, query: dict[str, Any]) -> list[Model]:
        raise NotImplementedError('abstract method')

    @classmethod
    async def update_many(cls, match_query_dict: dict[str, Any], update_expression_dict: dict[str, Any]) -> int:
        raise NotImplementedError('abstract method')

    @classmethod
    async def delete_many(cls, match_query_dict: dict[str, Any]) -> int:
        raise NotImplementedError('abstract method')

    @classmethod
    async def delete_all(cls) -> int:
        raise NotImplementedError('abstract method')

    @classmethod
    async def count(cls, query_filter: dict[str, Any] | None = None) -> int:
        raise NotImplementedError('abstract method')

    async def save(self) -> Any:
        raise NotImplementedError('abstract method')

    async def delete(self) -> None:
        raise NotImplementedError('abstract method')


class MongoRepository(Repository):

    @classmethod
    async def init_indexes(cls) -> None:
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
                        await fct(cls.get_collection(), key,
                                  value.index.sort_order if hasattr(value.index, 'sort_order') else SortOrder.ASC)

    @staticmethod
    async def version_check(required_version_tuple: tuple[int, ...]) -> None:
        server_info = await config.mongo_database.client.server_info()
        current_version = tuple(int(i) for i in server_info['version'].split('.'))
        if current_version < required_version_tuple:
            raise AppKernelException(
                f"This feature requires a min version of: {'.'.join(str(v) for v in required_version_tuple)}")

    @classmethod
    async def add_schema_validation(cls, validation_action: str = 'warn') -> None:
        await MongoRepository.version_check(tuple([3, 6, 0]))
        try:
            await config.mongo_database.create_collection(xtract(cls))
        except CollectionInvalid:
            pass
        await config.mongo_database.command(
            'collMod', xtract(cls),
            validator={'$jsonSchema': cls.get_json_schema(mongo_compatibility=True)},
            validationLevel='moderate',
            validationAction=validation_action
        )

    @staticmethod
    async def create_index(
        collection: AsyncIOMotorCollection,
        field_name: str,
        sort_order: SortOrder,
        unique: bool = False,
    ) -> None:
        existing = await collection.index_information()
        if field_name not in existing:
            if isinstance(sort_order, SortOrder):
                direction = pymongo.ASCENDING if sort_order == SortOrder.ASC else pymongo.DESCENDING
            else:
                direction = sort_order
            await collection.create_index(
                [(field_name, direction)],
                unique=unique, name=f'{field_name}_idx')

    @staticmethod
    async def create_text_index(collection: AsyncIOMotorCollection, field_name: str, *args: Any) -> None:
        await MongoRepository.create_index(collection, field_name, pymongo.TEXT)

    @staticmethod
    async def create_unique_index(collection: AsyncIOMotorCollection, field_name: str, sort_order: SortOrder) -> None:
        await MongoRepository.create_index(collection, field_name, sort_order, unique=True)

    @staticmethod
    async def not_supported(*args: Any) -> None:
        pass

    @classmethod
    def get_collection(cls) -> AsyncIOMotorCollection:
        db = config.mongo_database
        if db is not None:
            return db.get_collection(xtract(cls))
        else:
            raise AppKernelException('The database engine is not set')

    @classmethod
    async def find_by_id(cls, object_id: str) -> Model | None:
        assert object_id, 'the id of the lookup object must be provided'
        if isinstance(object_id, str) and object_id.startswith(OBJ_PREFIX):
            object_id = ObjectId(object_id.split(OBJ_PREFIX)[1])
        document_dict = await cls.get_collection().find_one({'_id': object_id})
        return Model.from_dict(document_dict, cls, convert_ids=True,
                               converter_func=mongo_type_converter_from_dict) if document_dict else None

    @classmethod
    async def delete_by_id(cls, object_id: str) -> int:
        result = await cls.get_collection().delete_one({'_id': object_id})
        return result.deleted_count

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
    async def patch_object(cls, document: dict[str, Any] | Model, object_id: str | None = None) -> Any:
        return await cls.__save_or_update_dict(document, object_id=object_id, insert_if_none_found=False)

    @classmethod
    async def __save_or_update_dict(
        cls,
        document: dict[str, Any] | Model,
        object_id: str | None = None,
        insert_if_none_found: bool = True,
    ) -> Any:
        has_id, document_id, document = MongoRepository.prepare_document(document, object_id)
        if has_id:
            update_result = await cls.get_collection().update_one(
                {'_id': document_id}, {'$set': document}, upsert=insert_if_none_found)
            db_id = update_result.upserted_id or (document_id if update_result.matched_count > 0 else None)
        else:
            insert_result = await cls.get_collection().insert_one(document)
            db_id = insert_result.inserted_id
        return db_id

    @classmethod
    async def save_object(cls, model: Model, object_id: str | None = None, insert_if_none_found: bool = True) -> Any:
        assert model, 'the object must be handed over as a parameter'
        assert isinstance(model, Model), 'the object should be a Model'
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
        model.id = await cls.__save_or_update_dict(document=document, object_id=object_id)
        return model.id

    @classmethod
    async def replace_object(cls, model: Model) -> Any:
        assert model, 'the document must be provided before replacing'
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
        has_id, document_id, document = MongoRepository.prepare_document(document, None)
        update_result = await cls.get_collection().replace_one({'_id': document_id}, document, upsert=False)
        return (update_result.upserted_id or document_id) if update_result.matched_count > 0 else None

    @classmethod
    async def bulk_insert(cls, list_of_model_instances: list[Model]) -> list[Any]:
        result = await cls.get_collection().insert_many(
            [Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
             for model in list_of_model_instances])
        return result.inserted_ids

    @classmethod
    async def find(cls, *expressions: Expression) -> list[Model]:
        return await MongoQuery(cls.get_collection(), cls, *expressions).find()

    @classmethod
    async def find_one(cls, *expressions: Expression) -> Model | None:
        return await MongoQuery(cls.get_collection(), cls, *expressions).find_one()

    @classmethod
    def where(cls, *expressions: Expression) -> MongoQuery:
        return MongoQuery(cls.get_collection(), cls, *expressions)

    @classmethod
    async def find_by_query(
        cls,
        query: dict[str, Any] = {},  # noqa: B006 - default used by supports_query() for runtime type detection
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_order: SortOrder = SortOrder.ASC,
        **kwargs: Any,
    ) -> list[Model]:
        cursor = cls.get_collection().find(query).skip((page - 1) * page_size).limit(page_size)
        if sort_by:
            py_direction = pymongo.ASCENDING if sort_order == SortOrder.ASC else pymongo.DESCENDING
            cursor = cursor.sort(sort_by, direction=py_direction)
        docs = await cursor.to_list(length=page_size)
        return [Model.from_dict(result, cls, convert_ids=True, converter_func=mongo_type_converter_from_dict)
                for result in docs]

    @classmethod
    async def create_cursor_by_query(cls, query: dict[str, Any]) -> list[Model]:
        cursor = cls.get_collection().find(query)
        docs = await cursor.to_list(length=None)
        return [Model.from_dict(result, cls, convert_ids=True, converter_func=mongo_type_converter_from_dict)
                for result in docs]

    @classmethod
    async def update_many(cls, match_query_dict: dict[str, Any], update_expression_dict: dict[str, Any]) -> int:
        result = await cls.get_collection().update_many(match_query_dict, update_expression_dict)
        return result.modified_count

    @classmethod
    async def delete_many(cls, match_query_dict: dict[str, Any]) -> int:
        result = await cls.get_collection().delete_many(match_query_dict)
        return result.deleted_count

    @classmethod
    async def delete_all(cls) -> int:
        result = await cls.get_collection().delete_many({})
        return result.deleted_count

    @classmethod
    async def count(cls, query_filter: dict[str, Any] | None = None) -> int:
        return await cls.get_collection().count_documents(query_filter or {})

    @classmethod
    async def aggregate(
        cls,
        pipe: list[dict[str, Any]] = [],  # noqa: B006 - used by _autobox_parameters() for runtime type detection
        allow_disk_use: bool = True,
        batch_size: int = 100,
    ) -> list[dict[str, Any]]:
        cursor = cls.get_collection().aggregate(pipe, allowDiskUse=allow_disk_use, batchSize=batch_size)
        return await cursor.to_list(length=None)

    async def save(self) -> Any:
        self.id = await self.__class__.save_object(self)  # pylint: disable=C0103
        return self.id

    async def delete(self) -> None:
        assert self.id is not None
        result = await self.get_collection().delete_one({'_id': self.id})
        if result.deleted_count != 1:
            raise RepositoryException("the instance couldn't be deleted")


class AuditableRepository(MongoRepository):

    def __init__(self, **kwargs: Any) -> None:
        super().__init__()

    @classmethod
    async def save_object(cls, model: Model, object_id: str | None = None) -> Any:
        document = Model.to_dict(model, convert_id=True, converter_func=mongo_type_converter_to_dict)
        has_id, doc_id, document = MongoRepository.prepare_document(document, object_id)
        now = datetime.now()
        document.update(updated=now)

        if has_id:
            if 'version' in document:
                del document['version']
            if 'inserted' in document:
                del document['inserted']
            upsert_expression = {
                '$set': document,
                '$setOnInsert': {'inserted': now},
                '$inc': {'version': 1}
            }
            update_result = await cls.get_collection().update_one({'_id': doc_id}, upsert_expression, upsert=True)
            db_id = update_result.upserted_id or doc_id
        else:
            document.update(inserted=now, version=1)
            insert_result = await cls.get_collection().insert_one(document)
            db_id = insert_result.inserted_id
        model.id = db_id
        return model.id

    async def save(self) -> Any:
        await self.__class__.save_object(self)
        return self.id
