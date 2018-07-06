from sqlalchemy import distinct
from sqlalchemy.sql import text as sql_text


class PermissionQuery:
    """PermissionQuery base class

    Query permissions for a QWC resource.
    """

    # name of public iam.role
    PUBLIC_ROLE_NAME = 'public'

    def __init__(self, config_models, logger):
        """Constructor

        :param ConfigModels config_models: Helper for ORM models
        :param Logger logger: Application logger
        """
        self.config_models = config_models
        self.logger = logger

    def permissions(self, params, username, session):
        """Query permissions for a QWC resource and dataset.

        Return resource specific permissions for a dataset.

        :param obj params: Service specific request parameters
        :param str username: User name
        :param Session session: DB session
        """
        raise NotImplementedError

    def resource_permissions(self, resource_type, resource_name, username,
                             session):
        """Query permissions for a QWC resource type and name.

        Return resource permissions sorted by priority.

        :param str resource_type: QWC resource type
        :param str resource_name: QWC resource name
        :param str username: User name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        # base query for all permissions of user
        query = self.user_permissions_query(username, session)

        # filter permissions by QWC resource type and name
        query = query.join(Permission.resource) \
            .filter(Resource.type == resource_type) \
            .filter(Resource.name == resource_name)

        # order by priority
        query = query.order_by(Permission.priority.desc()) \
            .distinct(Permission.priority)

        # execute query and return results
        return query.all()

    def resource_restrictions_query(self, resource_type, username, session):
        """Create query for restrictions for a QWC resource type and user.

        :param str resource_type: QWC resource type
        :param str username: User name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Resource = self.config_models.model('resources')

        # all resource restrictions
        all_restrictions = session.query(Permission). \
            join(Permission.resource). \
            with_entities(Resource.id, Resource.name, Resource.parent_id). \
            filter(Resource.type == resource_type)

        # resource permissions for user
        user_permissions = self.user_permissions_query(username, session). \
            join(Permission.resource). \
            with_entities(Resource.id, Resource.name, Resource.parent_id). \
            filter(Resource.type == resource_type)

        # restrictions without user permissions
        restrictions_query = all_restrictions.except_(user_permissions)

        return restrictions_query

    def user_permissions_query(self, username, session):
        """Create base query for all permissions of a user.

        :param str username: User name
        :param Session session: DB session
        """
        Permission = self.config_models.model('permissions')
        Role = self.config_models.model('roles')
        Group = self.config_models.model('groups')
        User = self.config_models.model('users')

        # create query
        query = session.query(Permission)

        # filter by username
        # NOTE: use nested JOINs to filter early and avoid too many rows
        #       from cartesian product
        # query permissions from roles in user groups
        groups_roles_query = query.join(Permission.role) \
            .join(Role.groups_collection) \
            .join(Group.users_collection) \
            .filter(User.name == username)

        # query permissions from direct user roles
        user_roles_query = query.join(Permission.role) \
            .join(Role.users_collection) \
            .filter(User.name == username)

        # query permissions from public role
        public_roles_query = query.join(Permission.role) \
            .filter(Role.name == self.PUBLIC_ROLE_NAME)

        # combine queries
        query = groups_roles_query.union(user_roles_query) \
            .union(public_roles_query)

        # unique permissions
        query = query.distinct(Permission.id)

        return query
