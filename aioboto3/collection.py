from async_generator import async_generator, yield_
import logging

from botocore.utils import merge_dicts
from boto3.resources.collection import CollectionFactory, ResourceCollection, CollectionManager
from boto3.resources.params import create_request_parameters

logger = logging.getLogger(__name__)


class AIOResourceCollection(ResourceCollection):
    # def __iter__(self):
    #     limit = self._params.get('limit', None)
    #
    #     count = 0
    #     for page in self.pages():
    #         for item in page:
    #             yield item
    #
    #             # If the limit is set and has been reached, then
    #             # we stop processing items here.
    #             count += 1
    #             if limit is not None and count >= limit:
    #                 return

    def __aiter__(self):
        # todo return a function thats an async_generator instead of anext
        return self

    async def __anext__(self):
        async for page in self.pages():
            print()
        print()


    @async_generator
    async def pages(self):
        client = self._parent.meta.client
        cleaned_params = self._params.copy()
        limit = cleaned_params.pop('limit', None)
        page_size = cleaned_params.pop('page_size', None)
        params = create_request_parameters(
            self._parent, self._model.request)
        merge_dicts(params, cleaned_params, append_lists=True)

        # Is this a paginated operation? If so, we need to get an
        # iterator for the various pages. If not, then we simply
        # call the operation and return the result as a single
        # page in a list. For non-paginated results, we just ignore
        # the page size parameter.
        if client.can_paginate(self._py_operation_name):
            logger.debug('Calling paginated %s:%s with %r',
                         self._parent.meta.service_name,
                         self._py_operation_name, params)
            paginator = client.get_paginator(self._py_operation_name)
            pages = paginator.paginate(
                PaginationConfig={
                    'MaxItems': limit, 'PageSize': page_size}, **params)
        else:
            @async_generator
            async def _tmp():
                res = await getattr(client, self._py_operation_name)(**params)
                await yield_(res)

            logger.debug('Calling %s:%s with %r',
                         self._parent.meta.service_name,
                         self._py_operation_name, params)
            # pages = [getattr(client, self._py_operation_name)(**params)]
            pages = _tmp()

        # Now that we have a page iterator or single page of results
        # we start processing and yielding individual items.
        count = 0
        async for page in pages:
            page_items = []
            for item in self._handler(self._parent, params, page):
                page_items.append(item)

                # If the limit is set and has been reached, then
                # we stop processing items here.
                count += 1
                if limit is not None and count >= limit:
                    break

            await yield_(page_items)

            # Stop reading pages if we've reached out limit
            if limit is not None and count >= limit:
                break


class AIOCollectionManager(CollectionManager):
    _collection_cls = AIOResourceCollection

    def all(self):
        return self.iterator()


class AIOCollectionFactory(CollectionFactory):
    def load_from_definition(self, resource_name, collection_model,
                             service_context, event_emitter):
        """
        Loads a collection from a model, creating a new
        :py:class:`CollectionManager` subclass
        with the correct properties and methods, named based on the service
        and resource name, e.g. ec2.InstanceCollectionManager. It also
        creates a new :py:class:`ResourceCollection` subclass which is used
        by the new manager class.

        :type resource_name: string
        :param resource_name: Name of the resource to look up. For services,
                              this should match the ``service_name``.

        :type service_context: :py:class:`~boto3.utils.ServiceContext`
        :param service_context: Context about the AWS service

        :type event_emitter: :py:class:`~botocore.hooks.HierarchialEmitter`
        :param event_emitter: An event emitter

        :rtype: Subclass of :py:class:`CollectionManager`
        :return: The collection class.
        """
        attrs = {}
        collection_name = collection_model.name

        # Create the batch actions for a collection
        self._load_batch_actions(
            attrs, resource_name, collection_model,
            service_context.service_model, event_emitter)
        # Add the documentation to the collection class's methods
        self._load_documented_collection_methods(
            attrs=attrs, resource_name=resource_name,
            collection_model=collection_model,
            service_model=service_context.service_model,
            event_emitter=event_emitter,
            base_class=AIOResourceCollection)

        if service_context.service_name == resource_name:
            cls_name = '{0}.{1}Collection'.format(
                service_context.service_name, collection_name)
        else:
            cls_name = '{0}.{1}.{2}Collection'.format(
                service_context.service_name, resource_name, collection_name)

        collection_cls = type(str(cls_name), (AIOResourceCollection,),
                              attrs)

        # Add the documentation to the collection manager's methods
        self._load_documented_collection_methods(
            attrs=attrs, resource_name=resource_name,
            collection_model=collection_model,
            service_model=service_context.service_model,
            event_emitter=event_emitter,
            base_class=AIOCollectionManager)
        attrs['_collection_cls'] = collection_cls
        cls_name += 'Manager'

        return type(str(cls_name), (AIOCollectionManager,), attrs)
