from sqlalchemy.orm import joinedload

from permission_query import PermissionQuery


class ResourcePermission(PermissionQuery):
    """ResourcePermission class

    Query permissions and restrictions for a resource type.
    """

    def permissions(self, resource_type, params, username, session):
        """Query permitted resources for a resource type with optional
        name or parent_id filter.

        Return resources if available and permitted.

        :param str resource_type: Resource type
        :param obj params: Optional request parameters with
                           name=<name filter>&parent_id=<parent filter>
        :param str username: User name
        :param Session session: DB session
        """
        permissions = {}

        name = params.get('name')
        parent_id = params.get('parent_id')

        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        query = self.user_permissions_query(username, session) \
            .join(Permission.resource).filter(Resource.type == resource_type) \
            .order_by(Permission.priority) \
            .distinct(Permission.priority)
        # eager load relations
        query = query.options(joinedload(Permission.resource))

        # optional filters
        if name is not None:
            # filter by resource name
            query = query.filter(Resource.name == name)
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except ValueError:
                parent_id = -1
            # filter by resource parent ID
            query = query.filter(Resource.parent_id == parent_id)

        for permission in query.all():
            resource = permission.resource
            # NOTE: permissions sorted by priority, so permission with
            #       higher priority will override lower priority
            permissions[resource.id] = {
                'id': resource.id,
                'name': resource.name,
                'parent_id': resource.parent_id,
                'writable': permission.write
            }

        return permissions

    def restrictions(self, resource_type, params, username, session):
        """Query restricted resources for a resource type with optional
        name or parent_id filter.

        Return restricted resources.

        :param str resource_type: Resource type
        :param obj params: Optional request parameters with
                           name=<name filter>&parent_id=<parent filter>
        :param str username: User name
        :param Session session: DB session
        """
        restrictions = {}

        name = params.get('name')
        parent_id = params.get('parent_id')

        Resource = self.config_models.model('resources')

        query = self.resource_restrictions_query(
            resource_type, username, session
        )

        # optional filters
        if name is not None:
            # filter by resource name
            query = query.filter(Resource.name == name)
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except ValueError:
                parent_id = -1
            # filter by resource parent ID
            query = query.filter(Resource.parent_id == parent_id)

        for resource in query.all():
            restrictions[resource.id] = {
                'id': resource.id,
                'name': resource.name,
                'parent_id': resource.parent_id
            }

        return restrictions
