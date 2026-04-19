"""
Database Router — Read Replica
Routes read-only queries (analytics, reports, lists) to a replica
and all writes to the primary database.

To activate:
1. Add replica to DATABASES in settings.py:
   DATABASES['replica'] = {
       'ENGINE': 'django.db.backends.postgresql',
       'NAME': os.environ.get('DB_REPLICA_NAME', ''),
       ...
   }
2. Uncomment DATABASE_ROUTERS in settings.py

Apps that always go to primary (writes):
- payments, orders, users, verification, trust

Apps that can use replica (reads):
- analytics, search, recommendations, collections, reviews
"""

# Apps whose reads go to the replica
READ_REPLICA_APPS = {
    'analytics', 'search', 'recommendations',
    'collections', 'reviews', 'i18n', 'seo',
}

# Apps that always hit primary (financial / auth critical)
PRIMARY_ONLY_APPS = {
    'payments', 'orders', 'users', 'verification',
    'trust', 'cart', 'inventory',
}


class ReadReplicaRouter:

    def db_for_read(self, model, **hints):
        """Send reads to replica for safe apps."""
        app = model._meta.app_label
        if app in READ_REPLICA_APPS and 'replica' in self._available_dbs():
            return 'replica'
        return 'default'

    def db_for_write(self, model, **hints):
        """All writes go to primary."""
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between all databases."""
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Only migrate on primary."""
        return db == 'default'

    def _available_dbs(self):
        from django.conf import settings
        return set(settings.DATABASES.keys())
