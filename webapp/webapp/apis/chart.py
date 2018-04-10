from flask import render_template, request, jsonify, Blueprint, url_for, send_file, make_response
from flask_security import login_required
from webapp.logger import logger
import pandas as pd
import datetime
import json
import copy
from collections import OrderedDict
import webapp.apis.query
from webapp.apis import query

chart_api = Blueprint('chart_api', __name__, url_prefix='/api/chart')


@chart_api.route('/get_schema', methods=['GET'])
@login_required
def get_records_by_time():
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    jurisdiction = request.args.get('jurisdiction')
    limit = request.args.get('limit', 10)
    offset = request.args.get('offset', 0)
    order_column = request.args.get('orderColumn')
    order = request.args.get('order')
    set_status = request.args.get('setStatus')
    logger.info(f'Pulling data from {start_date} to {end_date}')
    records = query.get_records_by_time(
        start_date,
        end_date,
        jurisdiction,
        limit,
        offset,
        order_column,
        order,
        set_status
    )
    return jsonify(results=records)

@chart_api.route('/download_list', methods=['GET'])
@login_required
def download_list():
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    jurisdiction = request.args.get('jurisdiction')
    limit = 'ALL'
    offset = 0
    order_column = request.args.get('orderColumn')
    order = request.args.get('order')
    set_status = request.args.get('setStatus')
    records = query.get_records_by_time(
        start_date,
        end_date,
        jurisdiction,
        limit,
        offset,
        order_column,
        order,
        set_status
    )
    df = pd.DataFrame(records['filteredData']['tableData'])
    output = make_response(df.to_csv(index=False))
    output.headers["Content-Disposition"] = "attachment; filename=export.csv"
    output.headers["Content-type"] = "text/csv"
    return output
