# coding: utf-8

__version__='0.0.1'


import os

import datetime
import pandas as pd
import yaml

import matcher.matcher as matcher
import matcher.preprocess as preprocess
import matcher.utils as utils
import matcher.ioutils as ioutils

from matcher.logger import logger


from redis import Redis
from rq import Queue 
redis_connection = Redis(host='redis', port=6379)
q = Queue('webapp', connection=redis_connection)


with open('config.yaml') as f:
    CONFIG = yaml.load(f)


def do_match(base_data_directory:str, schema_pk_lookup:dict, upload_id=None):
    # Initializing: let's get started by collecting some job metadata
    metadata = {
        'match_job_start_time': datetime.datetime.now(),
        'match_job_id': utils.unique_match_job_id(),
        'base_data_directory': base_data_directory,
        'config': CONFIG
    }
    logger.info("Matching process started!")

    try:
        # Loading: collect matching data (keys) for all available event types & record which event types were found
        logger.info('Loading data for matching.')
        df, event_types_read = ioutils.load_data_for_matching(
            base_data_directory,
            list(schema_pk_lookup.keys()),
            CONFIG['keys'],
            metadata['match_job_id']
        )
        metadata['event_types_read'] = list(event_types_read)
        metadata['loaded_data_columns'] = list(df.columns.values)
        metadata['loaded_data_shape'] = list(df.shape)
        metadata['data_loaded_time'] = datetime.datetime.now()

        # Preprocessing: enforce data types and split/combine columns for feartures
        logger.info('Doing some preprocessing on the columns')
        df = preprocess.preprocess(df, metadata['match_job_id'], base_data_directory)
        metadata['preprocessed_data_columns'] = list(df.columns.values)
        metadata['preprocessed_data_shape'] = list(df.shape)
        metadata['data_preprocessed_time'] = datetime.datetime.now()

        # Matching: block the data, generate pairs and features, and cluster entities
        logger.info(f"Running matcher")
        match_object = matcher.Matcher(
            base_data_directory=base_data_directory,
            match_job_id=metadata['match_job_id'],
            clustering_rules=CONFIG['clusterer']['args'],
            contrast_rules=CONFIG['contrasts'],
            blocking_rules=CONFIG['blocking_rules']
        )
        matches = match_object.block_and_match(df=df)
        metadata['data_matched_time'] = datetime.datetime.now()
        metadata.update(match_object.metadata)
        logger.debug('Matching done!')

        logger.debug(f"Number of matched pairs: {len(matches)}")

        # Writing: Join the matched ids to the source data for each event & write to S3 and postgres
        logger.info('Writing matched results!')
        matched_results_paths = ioutils.write_matched_data(
            matches=matches,
            base_data_directory=base_data_directory,
            person_keys=CONFIG['keys'],
            schema_pk_lookup={event_type:schema_pk_lookup[event_type] for event_type in event_types_read},
            match_job_id=metadata['match_job_id']
        )
        metadata['data_written_time'] = datetime.datetime.now()
        ioutils.write_dict_to_yaml(metadata, f"{base_data_directory}/match_cache/metadata/{metadata['match_job_id']}")

        logger.info('Finished')
        match_end_time = datetime.datetime.now()
        match_runtime =  match_end_time - metadata['match_job_start_time']

        job = q.enqueue_call(
            func='webapp.match_finished',
            args=(
                matched_results_paths,
                metadata['match_job_id'],
                metadata['match_job_start_time'],
                match_end_time,
                True,
                match_runtime,
                upload_id
            ),
            result_ttl=5000
        )

    except Exception as e:
        logger.error(f'Matcher failed with message "{str(e)}"')
        match_fail_time = datetime.datetime.now()
        match_run_time = match_fail_time - metadata['match_job_start_time']

        job = q.enqueue_call(
            func='webapp.match_finished',
            args=(
                {},
                metadata['match_job_id'],
                metadata['match_job_start_time'],
                match_fail_time,
                False,
                match_runtime,
                upload_id
            ),
            result_ttl=5000
        )

