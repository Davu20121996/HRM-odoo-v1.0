#!/usr/bin/env python3
import argparse
import configparser
import os
import sys
import time

try:
    import psycopg2
except ImportError:
    # fallback: psycopg2 có sẵn trong image odoo (dep python3-psycopg2)
    raise


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('--db_host')
    arg_parser.add_argument('--db_port')
    arg_parser.add_argument('--db_user')
    arg_parser.add_argument('--db_password')
    arg_parser.add_argument('--timeout', type=int, default=5)

    args = arg_parser.parse_args()

    config_options = {}
    rc_file_path = os.environ.get('ODOO_RC')
    if rc_file_path:
        config = configparser.RawConfigParser()
        config.read(rc_file_path)
        config_options = {k: v for k, v in config.items('options')} if config.has_section('options') else {}

    db_host = config_options.get('db_host') or args.db_host or os.environ.get('PGHOST')
    db_port = config_options.get('db_port') or args.db_port or os.environ.get('PGPORT')
    db_user = config_options.get('db_user') or args.db_user or os.environ.get('PGUSER')
    db_password = config_options.get('db_password') or args.db_password or os.environ.get('PGPASSWORD')

    params = {'db_host': db_host, 'db_port': db_port, 'db_user': db_user, 'db_password': db_password}
    missing_params = [k for k, v in params.items() if v is None]
    if missing_params:
        print(f"Missing required database parameters: {', '.join(missing_params)}", file=sys.stderr)
        sys.exit(1)

    start_time = time.time()
    error = None
    while (time.time() - start_time) < args.timeout:
        try:
            conn = psycopg2.connect(user=db_user, host=db_host, port=db_port, password=db_password, dbname='postgres')
            error = ''
            conn.close()
            break
        except Exception as e:
            error = e
        time.sleep(1)

    if error:
        print("Database connection failure: %s" % error, file=sys.stderr)
        sys.exit(1)
