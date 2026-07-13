"""Postgres connection setup. See db/init.sql for schema, DESIGN.md for the contract."""

import os

import psycopg
from pgvector.psycopg import register_vector


def connect() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn
