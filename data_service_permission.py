from flask import json
from sqlalchemy.sql import text as sql_text

from permission_query import PermissionQuery
from qgs_reader import QGSReader


class DataServicePermission(PermissionQuery):
    """DataServicePermission class

    Query permissions for a data service.
    """

    def __init__(self, db_engine, config_models, logger):
        """Constructor

        :param DatabaseEngine db_engine: Database engine with DB connections
        :param ConfigModels config_models: Helper for ORM models
        :param Logger logger: Application logger
        """
        super(DataServicePermission, self).__init__(config_models, logger)

        self.db_engine = db_engine

    def permissions(self, params, username, session):
        """Query permissions for editing a dataset.

        Return dataset edit permissions if available and permitted.

        Dataset ID can be either '<QGS name>.<Data layer name>' for a specific
        QGIS project or '<Data layer name>' if the data layer name is unique.

        :param obj params: Request parameters with dataset='<Dataset ID>'
        :param str username: User name
        :param Session session: DB session
        """
        permissions = {}

        dataset = params.get('dataset', '')
        parts = dataset.split('.')
        if len(parts) > 1:
            map_name = parts[0]
            layer_name = parts[1]
        else:
            # no map name given
            map_name = None
            layer_name = dataset

        data_permissions = self.data_permissions(
            map_name, layer_name, username, session
        )

        if data_permissions['permitted']:
            # get layer metadata from QGIS project
            qgs_reader = QGSReader(self.logger)
            if qgs_reader.read(data_permissions['map_name']):
                permissions = qgs_reader.layer_metadata(layer_name)

            if permissions:
                permissions.update({
                    'dataset': dataset,
                    'writable': data_permissions['writable']
                })

                self.filter_restricted_attributes(
                    data_permissions['restricted_attributes'],
                    permissions
                )

                self.lookup_attribute_data_types(permissions)

        return permissions

    def data_permissions(self, map_name, layer_name, username, session):
        """Query resource permissions and return whether map and data layer are
        permitted and writable, and any restricted attributes.

        If map_name is None, the data permission with highest priority is used.

        :param str map_name: Map name
        :param str layer_name: Data layer name
        :param str username: User name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        map_id = None
        if map_name is None:
            # find map for data layer name
            data_query = self.user_permissions_query(username, session). \
                join(Permission.resource).filter(Resource.type == 'data'). \
                filter(Resource.name == layer_name). \
                order_by(Permission.priority.desc()). \
                distinct(Permission.priority)
            # use data permission with highest priority
            data_permission = data_query.first()
            if data_permission is not None:
                map_id = data_permission.resource.parent_id
                map_query = session.query(Resource). \
                    filter(Resource.type == 'map'). \
                    filter(Resource.id == map_id)
                map_obj = map_query.first()
                if map_obj is not None:
                    map_name = map_obj.name
                    self.logger.info(
                        "No map name given, using map '%s'" % map_name
                    )
        else:
            # query map permissions
            maps_query = self.user_permissions_query(username, session). \
                join(Permission.resource).filter(Resource.type == 'map'). \
                filter(Resource.name == map_name)
            for map_permission in maps_query.all():
                map_id = map_permission.resource.id

        if map_id is None:
            # map not found or not permitted
            # NOTE: map without resource record cannot have data layers
            return {
                'permitted': False
            }

        # query data permissions
        permitted = False
        writable = False
        restricted_attributes = []
        data_query = self.user_permissions_query(username, session). \
            join(Permission.resource).filter(Resource.type == 'data'). \
            filter(Resource.parent_id == map_id). \
            filter(Resource.name == layer_name). \
            order_by(Permission.priority.desc()). \
            distinct(Permission.priority)
        # use data permission with highest priority
        data_permission = data_query.first()
        if data_permission is not None:
            permitted = True
            writable = data_permission.write

            # query attribute restrictions
            attrs_query = self.resource_restrictions_query(
                'attribute', username, session
            ).filter(Resource.parent_id == data_permission.resource_id)
            for attr in attrs_query.all():
                restricted_attributes.append(attr.name)

        return {
            'map_name': map_name,
            'permitted': permitted,
            'writable': writable,
            'restricted_attributes': restricted_attributes
        }

    def filter_restricted_attributes(self, restricted_attributes, permissions):
        """Filter restricted attributes from Data service permissions.

        :param list[str] restricted_attributes: List of restricted attributes
        :param obj permissions: Data service permissions
        """
        for attr in restricted_attributes:
            if attr in permissions['attributes']:
                permissions['attributes'].remove(attr)

    def lookup_attribute_data_types(self, permissions):
        """Query column data types and add them to Data service permissions.

        :param obj permissions: Data service permissions
        """
        try:
            connection_string = permissions['database']
            schema = permissions['schema']
            table_name = permissions['table_name']

            # connect to GeoDB
            geo_db = self.db_engine.db_engine(connection_string)
            conn = geo_db.connect()

            for attr in permissions['attributes']:
                # build query SQL
                sql = sql_text("""
                    SELECT data_type, character_maximum_length,
                        numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = '{table}'
                        AND column_name = '{column}'
                    ORDER BY ordinal_position;
                """.format(schema=schema, table=table_name, column=attr))

                # execute query
                data_type = None
                constraints = {}
                result = conn.execute(sql)
                for row in result:
                    data_type = row['data_type']

                    # constraints from data type
                    if (data_type in ['character', 'character varying'] and
                            row['character_maximum_length']):
                        constraints = {
                            'maxlength': row['character_maximum_length']
                        }
                    elif data_type in ['double precision', 'real']:
                        # NOTE: use text field with pattern for floats
                        constraints['pattern'] = '[0-9]+([\\.,][0-9]+)?'
                    elif data_type == 'numeric' and row['numeric_precision']:
                        step = pow(10, -row['numeric_scale'])
                        max_value = pow(
                            10, row['numeric_precision'] - row['numeric_scale']
                        ) - step
                        constraints = {
                            'numeric_precision': row['numeric_precision'],
                            'numeric_scale': row['numeric_scale'],
                            'min': -max_value,
                            'max': max_value,
                            'step': step
                        }
                    elif data_type == 'smallint':
                        constraints = {'min': -32768, 'max': 32767}
                    elif data_type == 'integer':
                        constraints = {'min': -2147483648, 'max': 2147483647}
                    elif data_type == 'bigint':
                        constraints = {
                            'min': '-9223372036854775808',
                            'max': '9223372036854775807'
                        }

                if attr not in permissions['fields']:
                    permissions['fields'][attr] = {}

                if data_type:
                    # add data type
                    permissions['fields'][attr]['data_type'] = data_type
                else:
                    self.logger.warn(
                        "Could not find data type of column '%s' "
                        "of table '%s.%s'" % (attr, schema, table_name)
                    )

                if constraints:
                    # add constraints
                    permissions['fields'][attr]['constraints'] = constraints

            # close database connection
            conn.close()

        except Exception as e:
            self.logger.error(
                "Error while querying attribute data types:\n\n%s" % e
            )
            raise
