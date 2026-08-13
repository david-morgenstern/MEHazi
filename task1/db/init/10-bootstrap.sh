#!/bin/sh
# Creates the two databases this stack keeps apart on purpose:
#
#   analytics  the data itself — the backend writes it, Superset reads it
#   superset   Superset's own state: dashboards, charts, users
#
# Keeping them separate means resetting Superset never touches the data, and
# reloading the data never disturbs the dashboards.
#
# Postgres runs this once, on first start with an empty data directory. Every
# statement is still guarded, so running it again by hand is harmless.
set -eu

bootstrap() {
	role=$1
	password=$2
	database=$3

	# \gexec runs the text the query returns, which is how you get an
	# IF NOT EXISTS that CREATE ROLE and CREATE DATABASE do not offer.
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
		-v role="$role" -v password="$password" -v database="$database" <<-'SQL'
		SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role', :'password')
		WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'role');
		\gexec

		SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'role')
		WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'database');
		\gexec
	SQL

	# Since Postgres 15 the public schema belongs to the bootstrap superuser and
	# no longer grants CREATE to everyone, so the owner could not create a table
	# in its own database. Hand the schema over.
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
		-v role="$role" <<-'SQL'
		ALTER SCHEMA public OWNER TO :"role";
	SQL

	echo "bootstrap: database $database owned by $role"
}

bootstrap "$ANALYTICS_USER" "$ANALYTICS_PASSWORD" "$ANALYTICS_DB"
bootstrap "$SUPERSET_DB_USER" "$SUPERSET_DB_PASSWORD" "$SUPERSET_DB"
