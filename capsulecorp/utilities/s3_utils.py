"""
AWS S3 Blob Storage Utility Methods
"""
import io
import logging
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import zipfile
import yaml
import boto3
import numpy as np
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(message)s")
logging.getLogger("py4j").setLevel(logging.ERROR)

# https://stackoverflow.com/questions/51272814
yaml.Dumper.ignore_aliases = lambda *args: True


def parse_url(s3_url):
    """
        This method will parse an s3 url.

        Args:
            s3_url (str): s3 url

        Returns:
            prefix and bucket name
    """
    # Parse proper output url
    parse_result = urlparse(s3_url)
    # Return prefix and bucket name 
    return parse_result.path[1:], parse_result.netloc, 


def read_file(access_key, secret_key, s3_prefix, bucket_name):
    """
        This method will read files from s3 using a boto3 client.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_prefix (str): AWS s3 prefix to file
            bucket_name (str): AWS s3 bucket name

        Returns:
            bytes object
    """
    client = boto3.client(
        's3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    file = client.get_object(Bucket=bucket_name, Key=s3_prefix)

    return file['Body'].read()


def read_df(access_key, secret_key, s3_prefix, bucket_name, **kwargs):
    """
        This method will read in data from s3 into a pandas DataFrame.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_prefix (str): AWS s3 prefix to file
            bucket_name (str): AWS s3 bucket name

        Returns:
            bytes object
    """
    return pd.read_csv(
        io.StringIO(str(read_file(
            access_key, secret_key, s3_prefix, bucket_name), "utf-8")),
        # Pass additional keyword arguments to pandas read_csv method
        **kwargs)


def write_bytes(access_key, secret_key, s3_prefix, bucket_name, bytes_object):
    """
        This method will write a bytes object to s3 provided a prefix.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_prefix (str): AWS s3 prefix to file
            bucket_name (str): AWS s3 bucket name
            bytes_object (bytes): object that will be written

        Returns:
            Success boolean
    """
    # Setup boto3 s3 client
    client = boto3.client(
        's3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    # Write object to s3
    response = client.put_object(
        Body=bytes_object, Bucket=bucket_name, Key=s3_prefix)
    # Return success
    return response["ResponseMetadata"]["HTTPStatusCode"] == 200


def write_pandas_df(
        access_key, secret_key, s3_url, pandas_df, **kwargs):
    """
        This method will save a DataFrame to S3 provided the filename.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_url (str): s3 url where data will be written
            pandas_df (pandas.DataFrame): DataFrame object

        Returns:
            success boolean
    """
    return write_bytes(
        access_key, secret_key,
        # Parse s3 URL for bucket name and s3 key
        *parse_url(s3_url),
        # Encode pandas DataFrame to bytes object
        pandas_df.to_csv(None, index=False, **kwargs).encode())


def write_dict(access_key, secret_key, s3_url, dict_object):
    """
        This method will convert a dict to bytes using YAML and write them to
        a specified s3 location.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_url (str): s3 url where data will be written
            dict_object (dict): python dictionary

        Returns:
            success boolean
    """
    return write_bytes(
        access_key, secret_key,
        # Parse s3 URL for bucket name and s3 key
        *parse_url(s3_url),
        # Encode dictionary
        yaml.dump(dict_object).encode())


def write_zip(access_key, secret_key, s3_url, file_dict):
    """
        This method will zip a dictionary of byte objects and save the file
        on s3.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_url (str): s3 url where data will be written
            file_dict (dict): filenames and their corresponding bytes

        Returns:
            success boolean
    """
    # Write bytes in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(
        zip_buffer, "a", zipfile.ZIP_DEFLATED, allowZip64=True
    ) as zip_file:
        for key, value in file_dict.items():
            zip_file.writestr(key, value)
    # Write bytes buffer to file
    success = write_bytes(
        access_key, secret_key, *parse_url(s3_url), zip_buffer.getvalue())
    # Close buffer
    zip_buffer.close()

    return success


def write_local_file(
        access_key, secret_key, s3_prefix, bucket_name, local_filepath):
    """
        This method will write a local file to s3.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_prefix (str): AWS s3 prefix to file
            bucket_name (str): AWS s3 bucket name
            local_filepath (str): local filepath

        Returns:
            success
    """
    success = False
    with open(local_filepath, "rb") as bytes_object:
        success = write_bytes(
            access_key, secret_key, s3_prefix, bucket_name, bytes_object)

    return success


def check_s3_path(access_key, secret_key, s3_path, bucket_name):
    """
        This method will check whether the provided s3 path is valid.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_path (str): path to s3 file
            bucket_name (str): name of s3 bucket

        Returns:
            boolean for whether the path exists
    """
    s3_client = boto3.client(
        's3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    # --- Setup key ---
    # Remove bucket from path to get prefix if applicable
    if bucket_name in s3_path:
        s3_prefix = s3_path.split(bucket_name)[1][1:]
    else:
        s3_prefix = s3_path
    # Get prefix to the left of the glob character
    if "*" in s3_prefix:
        s3_prefix = s3_prefix.split("*")[0]
    # Get list response
    resp = s3_client.list_objects(
        Bucket=bucket_name, Prefix=s3_prefix, MaxKeys=1)

    return "Contents" in resp


def get_responses(
        access_key, secret_key, s3_prefix, bucket_name):
    """
        This method will get the file information for a given directory on s3.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            s3_prefix (str): directory within s3 bucket
            bucket_name (str): name of s3 bucket

        Returns:
            list of json responses from S3
    """
    client = boto3.session.Session().client(
        "s3", aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    continuation_token = None
    responses = []
    # List objects within the given directory until the response is truncated
    while True:
        list_kwargs = dict(Bucket=bucket_name, Prefix=s3_prefix, MaxKeys=1000)
        # Add continuation token if not None
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token
        response = client.list_objects_v2(**list_kwargs)
        # Add valid reponses and update continuation token
        if 'Contents' in response:
            responses += response['Contents']
        # Exit while loop if at the end of the objects
        if not response.get('IsTruncated'):
            break
        continuation_token = response.get('NextContinuationToken')

    return responses


def get_s3_prefix_size(access_key, secret_key, s3_prefix_list, bucket_name):
    """
        This method will get the size of a list of s3 prefixes.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            prefix_list (list): list of s3 prefixes
            bucket (str): name of s3 bucket

        Returns:
            size (in Gb)
    """
    responses = []
    for s3_prefix in s3_prefix_list:
        responses += get_responses(
            access_key, secret_key, s3_prefix, bucket_name)

    return round(sum([i["Size"] for i in responses]) / np.power(10, 9), 2)


def copy_file(access_key, secret_key, old_prefix, new_prefix, bucket_name):
    """
        This method will copy a file in s3 given a task definition.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            old_prefix (str): old s3 prefix
            new_prefix (str): new s3 prefix
            bucket_name (str): s3 bucket name

        Returns:
            success boolean and exception message
    """
    success = True
    s3_client = boto3.resource(
        's3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
    # Try to copy file
    try:
        s3_client.Object(bucket_name, new_prefix).copy_from(
            CopySource=f"{bucket_name}/" + old_prefix)
    # If the copy fails for any reason set success to False
    except Exception as e:
        success = False

    return success


def copy_s3_files(
        access_key, secret_key, key_map, bucket_name, worker_count=8,
        max_retries=1):
    """
        This method will function as a threaded s3 copy a set of key value
        pairs of old s3 keys and new s3 keys.

        Args:
            access_key (str): AWS s3 Access Key
            secret_key (str): AWS s3 Secret Key
            key_map (dict): map of old to new s3 prefixes
            bucket_name (str): s3 bucket
            worker_count (int): number of workers to spin up for copying
            max_retries (int): maximum number of copy retries for failed tasks

        Returns:
            success boolean
    """
    success = True
    old_keys = list(key_map.keys())
    new_keys = list(key_map.values())
    # Create a thread pood to multiprocess tasks
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # Run initial tasks
        file_count = len(old_keys)
        results = list(executor.map(
            copy_file, [access_key] * file_count, [secret_key] * file_count,
            old_keys, new_keys, [bucket_name] * file_count))
        failed_tasks = [i for i in range(len(results)) if not results[i]]
        # Retry at most the number of max retries
        retries = 0
        while len(failed_tasks) > 0 and retries < max_retries:
            # Resubmit failed tasks
            futures = [i.result() for i in [
                executor.submit(
                    copy_file, access_key, secret_key, old_keys[i],
                    new_keys[i], bucket_name)
                for i in failed_tasks]]
            # Get updated failed tasks
            failed_tasks = [
                i for i in range(len(futures)) if not futures[i]]
            # Iterate retries
            retries += 1
        # If there are still failed tasks log error and reset success
        copies_failed = len(failed_tasks)
        if copies_failed > 0:
            logging.error(
                f"WARNING: {copies_failed} copies failed.")
            success = False

    return success
