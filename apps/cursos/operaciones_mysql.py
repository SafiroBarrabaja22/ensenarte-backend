"""
Operacion de migracion para SQL exclusivo de MySQL.

Los procedimientos y triggers (migraciones 0011 y 0012) usan sintaxis de
MySQL. Las pruebas locales corren en SQLite y la CI en PostgreSQL: alli estas
migraciones se marcan como aplicadas sin ejecutar nada, y las pruebas de
reglas de base de datos se saltan (tests/test_reglas_mysql.py).
"""

from django.db import migrations


class RunSQLSoloMySQL(migrations.RunSQL):
    """RunSQL que solo se ejecuta si la base es MySQL."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "mysql":
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "mysql":
            super().database_backwards(app_label, schema_editor, from_state, to_state)

    def describe(self):
        return "SQL exclusivo de MySQL (procedimientos/triggers)"
