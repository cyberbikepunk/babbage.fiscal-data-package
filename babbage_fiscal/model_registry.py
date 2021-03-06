import os
import logging
from collections import namedtuple

import elasticsearch
from elasticsearch import Elasticsearch, NotFoundError
from .db_utils import model_name

OS_ELASTICSEARCH_ADDRESS = os.environ.get('OS_ELASTICSEARCH_ADDRESS')
PACKAGE_FIELDS = ['id', 'model', 'package', 'origin_url']
Model = namedtuple('Model', PACKAGE_FIELDS)


class ModelRegistry(object):

    BATCH_SIZE = 100

    def __init__(self, es=None):
        if es is None:
            logging.info('Attempting to connect to ES: {0}'.format(OS_ELASTICSEARCH_ADDRESS))
            self.es = Elasticsearch(hosts=[OS_ELASTICSEARCH_ADDRESS])
            logging.info('Successful connection to ES')
        else:
            self.es = es

    @staticmethod
    def table_name_for_package(datapackage_owner, datapackage_name):
        return model_name(datapackage_owner, datapackage_name)

    def save_model(self, name, datapackage_url, datapackage, model, dataset_name, author):
        """
        Save a model in the registry
        :param name: name for the model
        :param datapackage_url: origin URL for the datapackage which is the source for this model
        :param datapackage: datapackage object from which this model was derived
        :param model: model to save
        """
        document = {
            # Fields used by babbage API
            'id': name,
            'model': model,
            'package': datapackage,
            'origin_url': datapackage_url,

            # Extra fields available in search
            'dataset': dataset_name,
            'author': author
        }
        self.es.index(index='packages', doc_type='package', body=document, id=name)
        # Make sure that the data is saved
        self.es.indices.flush('packages')

    def list_models(self):
        """
        List all available models in the DB
        :return: A generator yielding strings (one per model)
        """
        try:
            count = self.es.count(index='packages', doc_type='package', q='*')['count']
            from_ = 0
            while from_ < count:
                ret = self.es.search(index='packages', doc_type='package', q='*',
                                     size=self.BATCH_SIZE, from_=from_, _source=PACKAGE_FIELDS)
                for hit in ret.get('hits',{}).get('hits',[]):
                    yield hit['_source']['id']
                from_ += self.BATCH_SIZE
        except NotFoundError:
            return

    def has_model(self, name):
        """
        Check if a model exists in the registry
        :param name: model name to test
        :return: True if yes
        """
        return self.es.exists(index='packages', doc_type='package', id=name)

    def get_model(self, name):
        """
        Return the model associated with a specific name.
        Raises KeyError in case the model doesn't exist.
        :param name: model name to fetch
        :return: Python object representing the model
        """
        try:
            ret = self.es.get(index='packages', doc_type='package', id=name, _source=PACKAGE_FIELDS)
            if ret['found']:
                return ret['_source']['model']
            raise KeyError(name)
        except NotFoundError:
            raise KeyError(name)

    def get_package(self, name):
        """
        Return the original package contents associated with a specific name.
        Raises KeyError in case the model doesn't exist.
        :param name: model name to fetch
        :return: Python object representing the package
        """
        try:
            rec = self.es.get(index='packages', doc_type='package', id=name, _source=PACKAGE_FIELDS)
            if rec['found']:
                ret = rec['_source']['package']
                ret['__origin_url'] = rec['_source']['origin_url']
                return ret
            raise KeyError(name)
        except NotFoundError:
            raise KeyError(name)
