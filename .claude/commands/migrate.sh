#!/bin/bash
# Generate a new Alembic migration
# Usage: /migrate "description of changes"

cd backend
../.venv/Scripts/alembic revision --autogenerate -m "$1"
echo "Migration generated. Review it, then run: alembic upgrade head"
